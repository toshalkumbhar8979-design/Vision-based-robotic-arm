/* ==========================================================================
   DEMONSTRATION DATASET MANAGEMENT & TRAJECTORY REPLAY (JS)
   ==========================================================================
   Project:  Vision-Based Autonomous Robotic Arm
   File:     dataset_panel.js
   Location: dashboard/frontend/js/

   PURPOSE:
     Handles Phase C demonstration recording, trajectory sampling at 30Hz,
     live 6-joint angle telemetry streaming, auto-homing on stop, persistent
     local/backend episode storage, smooth trajectory replay with process status,
     and episode deletion.
   ========================================================================== */

const DatasetPanel = {
  isRecording: false,
  isPlaying: false,
  recordTimer: null,
  playTimer: null,
  currentTrajectory: [],
  episodes: [],
  sampleIntervalMs: 33, // 30Hz sampling rate

  init() {
    this.cacheDOM();
    this.bindEvents();
    this.loadEpisodes();
  },

  cacheDOM() {
    this.btnRecord = document.getElementById('btnRecordDataset');
    this.recordPill = document.getElementById('lblRecordStatusPill');
    this.frameCountSpan = document.getElementById('lblFrameCount');
    this.episodesList = document.getElementById('datasetEpisodesList');
    this.liveAnglesBox = document.getElementById('lblLiveAnglesBox');
    this.anglesValSpan = document.getElementById('lblAnglesVal');
  },

  bindEvents() {
    if (this.btnRecord) {
      this.btnRecord.addEventListener('click', () => this.toggleRecording());
    }
  },

  toggleRecording() {
    if (this.isRecording) {
      this.stopRecording();
    } else {
      this.startRecording();
    }
  },

  formatAnglesText(angles, gripperState) {
    if (!Array.isArray(angles) || angles.length < 5) return '';
    const stateStr = (gripperState === 1 || angles[5] <= 110) ? 'CLOSED (1)' : 'OPEN (0)';
    return `Base: ${angles[0]}° | Shoulder: ${angles[1]}° | Elbow: ${angles[2]}° | Wrist Pitch: ${angles[3]}° | Wrist Roll: ${angles[4]}° | Gripper: ${stateStr}`;
  },

  getCurrentJointAngles() {
    if (window.TeleopPanel && Array.isArray(window.TeleopPanel.smoothedAngles) && window.TeleopPanel.smoothedAngles.length === 6) {
      return [...window.TeleopPanel.smoothedAngles];
    }
    if (window.ServoPanel && typeof window.ServoPanel.getAnglesFromSliders === 'function') {
      return window.ServoPanel.getAnglesFromSliders();
    }
    if (window.ServoPanel && Array.isArray(window.ServoPanel.currentAngles)) {
      return [...window.ServoPanel.currentAngles];
    }
    return [90, 90, 90, 90, 90, 145];
  },

  async startRecording() {
    if (this.isPlaying) {
      alert('Cannot start recording while a trajectory replay is active.');
      return;
    }

    this.isRecording = true;
    this.currentTrajectory = [];
    this.currentBlockPose = null;

    // Fetch initial block pose from vision status
    try {
      const vres = await fetch('/api/vision/status');
      if (vres.ok) {
        const vdata = await vres.json();
        if (vdata.latest_block_pose && vdata.latest_block_pose.valid) {
          this.currentBlockPose = { ...vdata.latest_block_pose };
        }
      }
    } catch (e) {}

    if (this.btnRecord) {
      this.btnRecord.textContent = 'Stop Recording Demonstration';
      this.btnRecord.style.backgroundColor = '#E53935';
      this.btnRecord.style.borderColor = '#E53935';
    }

    if (this.recordPill) {
      this.recordPill.style.display = 'inline-flex';
    }

    if (this.liveAnglesBox) {
      this.liveAnglesBox.style.display = 'block';
    }

    if (this.frameCountSpan) {
      this.frameCountSpan.textContent = '0';
    }

    if (window.App && App.log) {
      const poseInfo = this.currentBlockPose 
        ? `[Block Pose: X=${this.currentBlockPose.x_cm}cm, Y=${this.currentBlockPose.y_cm}cm, θ=${this.currentBlockPose.theta_deg}°]` 
        : '[No block pose detected yet]';
      App.log(`STARTED DEMONSTRATION RECORDING (30Hz Trajectory Sampler Active) ${poseInfo}...`);
    }

    // 30Hz sampling loop
    const startTime = Date.now();
    this.recordTimer = setInterval(() => {
      const angles = this.getCurrentJointAngles();
      const gripperState = (window.TeleopPanel && window.TeleopPanel.gripperState !== undefined)
                            ? window.TeleopPanel.gripperState
                            : (angles[5] <= 110 ? 1 : 0);
      const elapsedMs = Date.now() - startTime;
      // Store 5 primary joint angles + binary gripper_state (0 = OPEN, 1 = CLOSED)
      this.currentTrajectory.push({
        t: elapsedMs,
        joints: angles.slice(0, 5),
        gripper_state: gripperState
      });

      if (this.frameCountSpan) {
        this.frameCountSpan.textContent = this.currentTrajectory.length;
      }

      if (this.anglesValSpan) {
        this.anglesValSpan.textContent = this.formatAnglesText(angles.slice(0, 5), gripperState);
      }
    }, this.sampleIntervalMs);
  },

  stopRecording() {
    if (!this.isRecording) return;

    this.isRecording = false;
    if (this.recordTimer) clearInterval(this.recordTimer);

    if (this.btnRecord) {
      this.btnRecord.textContent = 'Start Recording Demonstration';
      this.btnRecord.style.backgroundColor = 'var(--accent-primary)';
      this.btnRecord.style.borderColor = 'var(--accent-primary)';
    }

    if (this.recordPill) {
      this.recordPill.style.display = 'none';
    }

    if (this.liveAnglesBox) {
      this.liveAnglesBox.style.display = 'none';
    }

    const frameCount = this.currentTrajectory.length;
    const durationSec = (frameCount * (this.sampleIntervalMs / 1000)).toFixed(1);

    if (window.App && App.log) {
      App.log(`STOPPED DEMONSTRATION RECORDING (${frameCount} frames captured, ~${durationSec}s). Auto-homing arm...`);
    }

    // Auto-home the arm smoothly per user spec
    if (window.App && App.sendWS) {
      App.sendWS('home');
      if (window.TeleopPanel) {
        window.TeleopPanel.integratedAngles = [90, 90, 90, 90, 90, 145];
        window.TeleopPanel.smoothedAngles = [90, 90, 90, 90, 90, 145];
      }
    }

    if (frameCount === 0) return;

    const d = new Date();
    const dateStr = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }) + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const episodeId = `ep-${Date.now()}`;
    const newEpisode = {
      id: episodeId,
      number: this.episodes.length + 1,
      date: dateStr,
      frameCount,
      durationSec,
      initial_block_pose: this.currentBlockPose || null,
      trajectory: this.currentTrajectory
    };

    // Unshift so the latest episode is at the TOP
    this.episodes.unshift(newEpisode);
    this.saveEpisodes();
    this.renderEpisodes();
  },

  async loadEpisodes() {
    const saved = localStorage.getItem('robotic_arm_dataset_episodes');
    if (saved) {
      try {
        this.episodes = JSON.parse(saved);
      } catch (e) {}
    }

    try {
      const res = await fetch('/api/dataset');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          this.episodes = data;
          localStorage.setItem('robotic_arm_dataset_episodes', JSON.stringify(data));
        }
      }
    } catch (e) {}

    this.renderEpisodes();
  },

  async saveEpisodes() {
    try {
      localStorage.setItem('robotic_arm_dataset_episodes', JSON.stringify(this.episodes));
    } catch (e) {}

    try {
      await fetch('/api/dataset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ episodes: this.episodes })
      });
    } catch (e) {}
  },

  smoothTransitionToAngles(startAngles, targetAngles, durationMs, onUpdate, onComplete) {
    const steps = Math.max(10, Math.round(durationMs / this.sampleIntervalMs));
    let stepCount = 0;
    const timer = setInterval(() => {
      stepCount++;
      const progress = stepCount / steps;
      // Cosine S-curve smooth zero-jerk interpolation (Prime Directive Policy)
      const easeProgress = (1 - Math.cos(Math.PI * progress)) / 2;

      const current = startAngles.map((startVal, i) => {
        const targetVal = targetAngles[i];
        return Math.round(startVal + (targetVal - startVal) * easeProgress);
      });

      if (window.ServoPanel && ServoPanel.setAngles) {
        ServoPanel.setAngles(current);
      }
      if (onUpdate) onUpdate(current, Math.round(progress * 100));

      if (stepCount >= steps) {
        clearInterval(timer);
        if (onComplete) onComplete();
      }
    }, this.sampleIntervalMs);
  },

  playEpisode(episodeId) {
    if (this.isRecording) {
      alert('Cannot play trajectory while recording is active.');
      return;
    }

    if (this.isPlaying) {
      alert('A trajectory replay is already in progress.');
      return;
    }

    const ep = this.episodes.find(e => e.id === episodeId);
    if (!ep || !ep.trajectory || ep.trajectory.length === 0) return;

    this.isPlaying = true;

    // Find Play button element for this specific episode
    const playBtn = document.getElementById(`btnPlay-${episodeId}`);
    const statusSpan = document.getElementById(`lblStatus-${episodeId}`);

    if (playBtn) {
      playBtn.disabled = true;
      playBtn.textContent = 'Aligning to Start Pose...';
      playBtn.style.opacity = '0.7';
    }

    if (this.liveAnglesBox) {
      this.liveAnglesBox.style.display = 'block';
    }

    if (window.App && App.log) {
      App.log(`PREPARING REPLAY: Smoothly aligning arm to Episode #${ep.number} start pose...`);
    }

    const currentLiveAngles = this.getCurrentJointAngles();
    const openAngle = parseInt(document.getElementById('angleGripperOpen')?.value || document.getElementById('inputGripperOpenCard')?.value || 140, 10);
    const closeAngle = parseInt(document.getElementById('angleGripperClosed')?.value || document.getElementById('inputGripperClosedCard')?.value || 85, 10);
    const firstFrame = ep.trajectory[0];
    const firstState = (firstFrame.gripper_state !== undefined) ? firstFrame.gripper_state : ((firstFrame.angles && firstFrame.angles[5] <= 110) ? 1 : 0);
    const startPose = firstFrame.joints ? [...firstFrame.joints, (firstState === 1 ? closeAngle : openAngle)] : firstFrame.angles;

    // Phase 1: Smooth 1-second S-Curve transition from current pose to start pose
    this.smoothTransitionToAngles(
      currentLiveAngles,
      startPose,
      1000, // 1000ms transition time
      (angles) => {
        if (statusSpan) {
          statusSpan.textContent = 'Aligning to Start Pose...';
          statusSpan.style.color = 'var(--accent-primary)';
        }
        if (this.anglesValSpan) {
          this.anglesValSpan.textContent = this.formatAnglesText(angles);
        }
      },
      () => {
        // Phase 2: Play actual recorded trajectory
        if (playBtn) playBtn.textContent = 'Replaying Trajectory...';
        if (window.App && App.log) {
          App.log(`PLAYING TRAJECTORY: Episode #${ep.number} (${ep.frameCount} frames, ~${ep.durationSec}s)...`);
        }

        let frameIndex = 0;
        this.playTimer = setInterval(() => {
          if (frameIndex >= ep.trajectory.length) {
            clearInterval(this.playTimer);

            // Phase 3: Smooth 1-second transition back to Home Position
            if (window.App && App.log) App.log(`Episode #${ep.number} Trajectory Complete. Smoothly returning to Home Position...`);
            const endPose = ep.trajectory[ep.trajectory.length - 1].angles;
            const homePose = [90, 90, 90, 90, 90, 145];

            this.smoothTransitionToAngles(
              endPose,
              homePose,
              1000,
              (angles) => {
                if (statusSpan) {
                  statusSpan.textContent = 'Returning Home...';
                  statusSpan.style.color = '#2E7D32';
                }
                if (this.anglesValSpan) {
                  this.anglesValSpan.textContent = this.formatAnglesText(angles);
                }
              },
              () => {
                this.isPlaying = false;
                if (playBtn) {
                  playBtn.disabled = false;
                  playBtn.textContent = 'Play Trajectory';
                  playBtn.style.opacity = '1';
                }

                if (statusSpan) {
                  statusSpan.textContent = 'Replay Complete';
                  statusSpan.style.color = '#2E7D32';
                }

                if (this.liveAnglesBox) {
                  this.liveAnglesBox.style.display = 'none';
                }
              }
            );

            return;
          }

          const frame = ep.trajectory[frameIndex];
          const primaryJoints = frame.joints || (frame.angles ? frame.angles.slice(0, 5) : [90, 90, 90, 90, 90]);
          const state = (frame.gripper_state !== undefined) ? frame.gripper_state : ((frame.angles && frame.angles[5] <= 110) ? 1 : 0);
          const openAngle = parseInt(document.getElementById('angleGripperOpen')?.value || document.getElementById('inputGripperOpenCard')?.value || 140, 10);
          const closeAngle = parseInt(document.getElementById('angleGripperClosed')?.value || document.getElementById('inputGripperClosedCard')?.value || 85, 10);
          const gripperAngle = (state === 1) ? closeAngle : openAngle;
          const fullAngles = [...primaryJoints, gripperAngle];

          if (window.ServoPanel && ServoPanel.setAngles) {
            ServoPanel.setAngles(fullAngles);
          }

          if (this.anglesValSpan) {
            this.anglesValSpan.textContent = this.formatAnglesText(primaryJoints, state);
          }

          if (statusSpan) {
            statusSpan.textContent = `Replaying Frame ${frameIndex + 1} / ${ep.trajectory.length}...`;
            statusSpan.style.color = 'var(--accent-primary)';
          }

          frameIndex++;
        }, this.sampleIntervalMs);
      }
    );
  },

  async deleteEpisode(episodeId) {
    const ep = this.episodes.find(e => e.id === episodeId);
    const epName = ep ? `Episode #${ep.number}` : 'this episode';

    if (confirm(`Are you sure you want to delete ${epName}?`)) {
      this.episodes = this.episodes.filter(e => e.id !== episodeId);
      await this.saveEpisodes();
      this.renderEpisodes();
      if (window.App && App.log) App.log(`Deleted ${epName} from dataset.`);
    }
  },

  renderEpisodes() {
    if (!this.episodesList) return;

    if (this.episodes.length === 0) {
      this.episodesList.innerHTML = `
        <div style="text-align: center; padding: 32px 16px; color: var(--text-muted); font-family: var(--font-mono); font-size: 0.85rem; border: 2px dashed var(--border-subtle); border-radius: 12px; margin-top: 16px;">
          No demonstration episodes recorded yet.
        </div>
      `;
      return;
    }

    this.episodesList.innerHTML = this.episodes.map(ep => `
      <div class="card" style="margin-top: 16px; border-left: 4px solid var(--accent-primary);">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
          <div>
            <h4 style="font-family: var(--font-heading); font-size: 1.1rem; color: var(--text-main); margin-bottom: 4px;">
              Episode #${ep.number}
            </h4>
            <div style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--text-muted);">
              ${ep.date} • ${ep.frameCount} frames (~${ep.durationSec}s)
              <span id="lblStatus-${ep.id}" style="margin-left: 8px; font-weight: 600;"></span>
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: 10px;">
            <button class="btn btn-primary" id="btnPlay-${ep.id}" onclick="DatasetPanel.playEpisode('${ep.id}')" style="padding: 8px 16px; font-size: 0.82rem; font-weight: 600;">
              Play Trajectory
            </button>
            <button class="btn btn-secondary" onclick="DatasetPanel.deleteEpisode('${ep.id}')" style="padding: 8px 14px; font-size: 0.82rem; color: #E53935; border-color: rgba(229, 57, 53, 0.3);">
              🗑️ Delete
            </button>
          </div>
        </div>
      </div>
    `).join('');
  }
};

window.DatasetPanel = DatasetPanel;

document.addEventListener('DOMContentLoaded', () => {
  DatasetPanel.init();
});
