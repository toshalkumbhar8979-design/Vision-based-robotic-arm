/* ==========================================================================
   ONNX AUTONOMOUS POLICY PANEL (JS)
   ==========================================================================
   Project:  Vision-Based Autonomous Robotic Arm
   File:     onnx_panel.js
   Location: dashboard/frontend/js/

   PURPOSE:
     Dashboard page for the ONNX Behaviour Cloning policy:
       - Lists / loads trained .onnx policies (Dataset_30/models via backend)
       - Starts / stops the 30Hz autonomous closed-loop pick-and-place
       - Streams live policy telemetry via the WebSocket 'onnx_status' messages

   MODE GUARANTEE:
     The arm only uses the model while autonomous mode is RUNNING. When
     stopped (or before it is ever started), all other panels behave exactly
     as before — sliders, PS5 teleop, IK and dataset replay are untouched.
   ========================================================================== */

const OnnxPanel = {
  init() {
    this.cacheDOM();
    this.bindEvents();
    this.refreshModels();
    this.loadModelInfo();
    this.fetchStatus();
  },

  cacheDOM() {
    this.modelSelect = document.getElementById('onnxModelSelect');
    this.modelDir = document.getElementById('onnxModelDir');
    this.statusPill = document.getElementById('onnxStatusPill');
    this.statusText = document.getElementById('onnxStatusText');
    this.btnLoad = document.getElementById('btnOnnxLoad');
    this.btnRefresh = document.getElementById('btnOnnxRefresh');
    this.btnStart = document.getElementById('btnOnnxStart');
    this.btnStop = document.getElementById('btnOnnxStop');
    this.btnOverride = document.getElementById('btnOnnxOverride');
    this.infoName = document.getElementById('onnxInfoName');
    this.infoArch = document.getElementById('onnxInfoArch');
    this.infoDataset = document.getElementById('onnxInfoDataset');
    this.infoMetrics = document.getElementById('onnxInfoMetrics');
    this.infoContract = document.getElementById('onnxInfoContract');
    this.infoFile = document.getElementById('onnxInfoFile');
    this.holdBanner = document.getElementById('onnxHoldBanner');
    this.errorBanner = document.getElementById('onnxErrorBanner');
    this.hz = document.getElementById('onnxHz');
    this.frames = document.getElementById('onnxFrames');
    this.runtime = document.getElementById('onnxRuntime');
    this.gripProb = document.getElementById('onnxGripProb');
    this.blockPose = document.getElementById('onnxBlockPose');
    this.blockValid = document.getElementById('onnxBlockValid');
    this.smoothedJoints = document.getElementById('onnxSmoothedJoints');
    this.predictedJoints = document.getElementById('onnxPredictedJoints');
  },

  bindEvents() {
    if (this.btnLoad) this.btnLoad.addEventListener('click', () => this.loadSelectedModel());
    if (this.btnRefresh) this.btnRefresh.addEventListener('click', () => this.refreshModels());
    if (this.btnStart) this.btnStart.addEventListener('click', () => this.startAutonomous());
    if (this.btnStop) this.btnStop.addEventListener('click', () => this.stopAutonomous());
    if (this.btnOverride) this.btnOverride.addEventListener('click', () => this.manualOverride());
  },

  /* MANUAL OVERRIDE: instant take-control against erratic/AWOL policy behaviour */
  async manualOverride() {
    try {
      App.log('ONNX: MANUAL OVERRIDE pressed — halting model instantly...');
      const res = await fetch('/api/onnx/override', { method: 'POST' });
      const data = await res.json();
      App.log(`ONNX: ${data.message || 'Override engaged.'}`);
      this.showError(null);
      this.fetchStatus();
    } catch (e) {
      App.log(`ONNX override error: ${e.message}`);
    }
  },

  /* Model Card: pull architecture / dataset / metrics / contract */
  async loadModelInfo() {
    try {
      const res = await fetch('/api/onnx/info');
      if (!res.ok) return;
      const info = await res.json();
      if (this.infoName) this.infoName.textContent = info.model_name || '(no model loaded)';
      if (this.infoArch) this.infoArch.textContent = info.architecture || '—';
      if (this.infoDataset) {
        this.infoDataset.textContent =
          `${info.dataset || '—'} | ${info.transitions || ''} | ${info.epochs || '?'} epochs`;
      }
      if (this.infoMetrics) {
        this.infoMetrics.textContent =
          `Joint MAE ${info.val_joint_mae_deg ?? '—'}° | Gripper acc ${info.gripper_accuracy || '—'}`;
      }
      if (this.infoContract) {
        this.infoContract.innerHTML =
          `IN: ${info.obs_contract || '—'}<br>OUT: ${info.act_contract || '—'}`;
      }
      if (this.infoFile) {
        this.infoFile.textContent =
          `${info.model_name} | ${info.file_size_kb ?? '?'} KB | exported ${info.exported || '—'} | ` +
          `${info.framework || ''} | ${info.inference || ''} | Safety: ${info.safety || ''}`;
      }
    } catch (e) { /* offline UI mode */ }
  },

  async refreshModels() {
    try {
      const res = await fetch('/api/onnx/models');
      const data = await res.json();
      if (this.modelDir) {
        this.modelDir.textContent = `Model directory: ${data.model_dir} (${(data.models || []).length} model(s))`;
      }
      if (this.modelSelect) {
        this.modelSelect.innerHTML = '';
        if (!data.models || data.models.length === 0) {
          this.modelSelect.innerHTML = '<option value="">No .onnx models found in Dataset_30/models</option>';
        } else {
          data.models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.name;
            opt.textContent = `${m.name} (${m.size_kb} KB, ${m.modified})`;
            if (data.loaded_model === m.name) opt.selected = true;
            this.modelSelect.appendChild(opt);
          });
        }
      }
      this.updateControls(!!data.loaded, data.loaded_model);
      // AUTO-LOAD fallback: if the server has models but none loaded (e.g. the
      // browser panel was opened against an older server), load the first one
      // automatically so the model "just works" without a manual click.
      if (!data.loaded && data.models && data.models.length > 0 && !this._autoLoadTried) {
        this._autoLoadTried = true;
        App.log('ONNX: No model loaded yet — auto-loading available policy...');
        this.loadSelectedModel();
      }
    } catch (e) {
      console.warn('Could not list ONNX models:', e);
      if (this.modelDir) this.modelDir.textContent = 'Backend unreachable — is the FastAPI server running?';
    }
  },

  async fetchStatus() {
    try {
      const res = await fetch('/api/onnx/status');
      if (res.ok) this.handleStatus(await res.json());
    } catch (e) { /* offline UI mode */ }
  },

  async loadSelectedModel() {
    const name = this.modelSelect ? this.modelSelect.value : '';
    if (!name) {
      App.log('ONNX: No model selected.');
      return;
    }
    try {
      App.log(`ONNX: Loading policy ${name}...`);
      const res = await fetch('/api/onnx/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: name })
      });
      let data = {};
      try { data = await res.json(); } catch (e) { /* non-JSON error page */ }
      if (res.ok) {
        App.log(`ONNX: ${data.message || 'Model loaded.'}`);
        this.setStatusPill(true, data.model || name);
        this.showError(null);
      } else {
        const detail = data.detail || `HTTP ${res.status} ${res.statusText}`;
        App.log(`ONNX load failed: ${detail}`);
        this.showError(detail);
      }
      this.refreshModels();
      this.loadModelInfo();
    } catch (e) {
      App.log(`ONNX load error: ${e.message} (check the FastAPI server console)`);
      this.showError(e.message);
    }
  },

  async startAutonomous() {
    try {
      App.log('ONNX: Starting autonomous pick-and-place (30Hz closed loop)...');
      const res = await fetch('/api/onnx/start', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        App.log(`ONNX: ${data.message}`);
      } else {
        App.log(`ONNX start failed: ${data.detail || 'unknown error'}`);
        this.showError(data.detail || 'Start failed');
      }
      this.fetchStatus();
    } catch (e) {
      App.log(`ONNX start error: ${e.message}`);
    }
  },

  async stopAutonomous() {
    try {
      const res = await fetch('/api/onnx/stop', { method: 'POST' });
      const data = await res.json();
      App.log(`ONNX: ${data.message || 'Autonomous mode stopped.'}`);
      this.fetchStatus();
    } catch (e) {
      App.log(`ONNX stop error: ${e.message}`);
    }
  },

  updateControls(isLoaded, modelName) {
    if (this.btnStart) this.btnStart.disabled = !isLoaded;
    this.setStatusPill(isLoaded, modelName);
  },

  setStatusPill(isLoaded, modelName) {
    if (!this.statusPill || !this.statusText) return;
    if (isLoaded) {
      this.statusPill.className = 'status-pill connected';
      this.statusText.textContent = `Model loaded: ${modelName || 'ready'}`;
    } else {
      this.statusPill.className = 'status-pill';
      this.statusText.textContent = 'No model loaded';
    }
  },

  showError(msg) {
    if (!this.errorBanner) return;
    if (!msg) {
      this.errorBanner.style.display = 'none';
      return;
    }
    this.errorBanner.textContent = `! ${msg}`;
    this.errorBanner.style.display = 'block';
  },

  /* Live telemetry pushed by backend WebSocket type 'onnx_status' */
  handleStatus(d) {
    if (!d) return;

    // Start / Stop / Override button state
    if (this.btnStart && this.btnStop && this.btnOverride) {
      this.btnStart.style.display = d.is_running ? 'none' : '';
      this.btnStop.style.display = d.is_running ? '' : 'none';
      this.btnOverride.style.display = d.is_running ? '' : 'none';
      this.btnStart.disabled = !d.is_loaded;
    }
    this.setStatusPill(d.is_loaded, d.model_name);
    this.showError(d.last_error);

    if (this.holdBanner) this.holdBanner.style.display = d.is_running && d.holding ? '' : 'none';

    if (this.hz) this.hz.textContent = (d.infer_hz || 0).toFixed(1);
    if (this.frames) this.frames.textContent = d.frames || 0;
    if (this.runtime) this.runtime.textContent = (d.runtime_sec || 0).toFixed(1);
    if (this.gripProb && d.predicted_joints) this.gripProb.textContent = (d.predicted_joints[5] || 0).toFixed(2);

    if (this.blockPose && d.is_running) {
      // Block pose comes from the vision pipeline broadcast (via /api/vision/status fetch below)
    }

    if (this.smoothedJoints && d.smoothed_joints) {
      const names = ['Base', 'Shldr', 'Elbow', 'W.Pitch', 'W.Roll'];
      this.smoothedJoints.textContent =
        d.smoothed_joints.slice(0, 5).map((v, i) => `${names[i]} ${v}°`).join(' | ') +
        ` | Gripper ${d.smoothed_joints[5]}°`;
    }
    if (this.predictedJoints && d.predicted_joints) {
      this.predictedJoints.textContent =
        d.predicted_joints.slice(0, 5).map(v => v.toFixed(1)).join(', ');
    }
  }
};

// Fetch block pose at 2Hz for the panel display (independent of inference loop)
setInterval(async () => {
  try {
    const res = await fetch('/api/vision/status');
    if (!res.ok) return;
    const v = await res.json();
    const el = document.getElementById('onnxBlockPose');
    const elValid = document.getElementById('onnxBlockValid');
    if (!el) return;
    if (v.latest_block_pose && v.latest_block_pose.valid) {
      const p = v.latest_block_pose;
      el.textContent = `X=${p.x_cm}cm Y=${p.y_cm}cm θ=${p.theta_deg}°`;
      if (elValid) { elValid.textContent = '(DETECTED ✓)'; elValid.style.color = '#2E7D32'; }
    } else {
      if (elValid) { elValid.textContent = '(searching...)'; elValid.style.color = '#E65100'; }
    }
  } catch (e) { /* offline */ }
}, 500);

window.OnnxPanel = OnnxPanel;

document.addEventListener('DOMContentLoaded', () => {
  OnnxPanel.init();
});
