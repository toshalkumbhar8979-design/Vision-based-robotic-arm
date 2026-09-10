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
  UI_VERSION: 'v1.0.48',
  API_BASE: '',   // '' = same origin; auto-detected fallback lives here

  init() {
    this.cacheDOM();
    this.bindEvents();
    this.showUiVersion();
    this.installErrorSurfacer();
    this.bootstrapWithRetry(0);
  },

  /* Prefix helper: all API calls go through this so the panel can follow the
     real backend even when the page itself is served by something else
     (e.g. VS Code Live Server on :5500, or opened as a file). */
  api(path) {
    return this.API_BASE + path;
  },

  /* Shows the UI version on the page so a stale browser cache is instantly visible */
  showUiVersion() {
    const el = document.getElementById('onnxUiVersion');
    if (el) el.textContent = `UI ${this.UI_VERSION}`;
  },

  /* Surface unexpected JS errors in the panel instead of failing silently */
  installErrorSurfacer() {
    window.addEventListener('error', (e) => {
      if (e && e.message && this.errorBanner) {
        this.showError(`Panel JS error: ${e.message}`);
      }
    });
  },

  /* Finds a server that actually has the /api/onnx routes.
     Tries: same origin -> localhost:8050 -> 127.0.0.1:8050 */
  async probeBackends() {
    const candidates = ['', 'http://localhost:8050', 'http://127.0.0.1:8050'];
    let saw404 = null;
    for (const base of candidates) {
      try {
        const res = await fetch(base + '/api/onnx/models', { cache: 'no-store' });
        if (res.ok) {
          this.API_BASE = base;
          return { ok: true, base };
        }
        if (res.status === 404) saw404 = base || location.origin;
      } catch (e) { /* unreachable, try next */ }
    }
    return { ok: false, saw404 };
  },

  /* Initial load with retries — survives page-open-before-server races */
  async bootstrapWithRetry(attempt) {
    const probe = await this.probeBackends();
    if (probe.ok) {
      this.showError(null);
      await this.refreshModels();
      this.loadModelInfo();
      this.fetchStatus();
      return;
    }

    const wrongOrigin = location.protocol === 'file:' ||
                        (location.port && location.port !== '8050');
    let msg;
    if (probe.saw404) {
      msg = `The page origin (${probe.saw404}) has NO /api/onnx backend. ` +
            'The API lives on the FastAPI server. Open http://localhost:8050 directly.';
    } else if (wrongOrigin) {
      msg = `You opened the dashboard from "${location.origin || 'file://'}". ` +
            'That origin cannot reach the robot API. Open http://localhost:8050';
    } else {
      msg = 'Backend unreachable on :8050. Start it with: cd dashboard/backend && python main.py, ' +
            'then open http://localhost:8050';
    }

    if (this.modelDir) {
      this.modelDir.innerHTML =
        'Correct dashboard URL: <a href="http://localhost:8050" style="color: var(--accent-primary); font-weight: 700;">http://localhost:8050</a>';
    }
    this.showError(`${msg} (attempt ${attempt + 1}/4)`);
    if (attempt < 3) {
      setTimeout(() => this.bootstrapWithRetry(attempt + 1), 2500);
    }
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
    this.btnModelCard = document.getElementById('btnOnnxModelCard');
    this.btnStatusModelCard = document.getElementById('btnOnnxStatusModelCard');
    this.modelCardModal = document.getElementById('onnxModelCardModal');
    this.btnModelCardClose = document.getElementById('btnOnnxModelCardClose');
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
    if (this.btnModelCard) this.btnModelCard.addEventListener('click', () => this.openModelCard());
    if (this.btnStatusModelCard) this.btnStatusModelCard.addEventListener('click', () => this.openModelCard());
    if (this.btnModelCardClose) this.btnModelCardClose.addEventListener('click', () => this.closeModelCard());
    if (this.modelCardModal) {
      // Click on the dark backdrop closes; clicks inside the card do not.
      this.modelCardModal.addEventListener('click', (e) => {
        if (e.target === this.modelCardModal) this.closeModelCard();
      });
    }
    // Esc closes the floating window
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.closeModelCard();
    });
  },

  /* Floating Model Card window */
  openModelCard() {
    if (!this.modelCardModal) return;
    this.modelCardModal.style.display = 'flex';
    this.loadModelInfo();   // always fresh when opened
  },

  closeModelCard() {
    if (this.modelCardModal) this.modelCardModal.style.display = 'none';
  },

  /* MANUAL OVERRIDE: instant take-control against erratic/AWOL policy behaviour */
  async manualOverride() {
    try {
      App.log('ONNX: MANUAL OVERRIDE pressed — halting model instantly...');
      const res = await fetch(this.api('/api/onnx/override'), { method: 'POST' });
      const data = await res.json();
      App.log(`ONNX: ${data.message || 'Override engaged.'}`);
      this.showError(null);
      this.fetchStatus();
    } catch (e) {
      App.log(`ONNX override error: ${e.message}`);
    }
  },

  /* Model Card: pull architecture / dataset / metrics / contract and render it neatly */
  async loadModelInfo() {
    try {
      const res = await fetch(this.api('/api/onnx/info'), { cache: 'no-store' });
      if (!res.ok) return;
      const info = await res.json();

      if (this.infoName) this.infoName.textContent = info.model_name || '(no model loaded)';

      if (this.infoArch) {
        this.infoArch.innerHTML =
          `<div style="line-height: 1.7;">${info.architecture || '—'}</div>`;
      }

      if (this.infoDataset) {
        this.infoDataset.innerHTML =
          `<div style="line-height: 1.7;">${info.dataset || '—'}</div>` +
          `<div style="margin-top: 6px; color: var(--text-muted); line-height: 1.6;">` +
          `${info.transitions || ''} · ${info.epochs ?? '?'} training epochs</div>`;
      }

      if (this.infoMetrics) {
        const chip = (t) => `<span style="display: inline-block; background: var(--bg-card, #FFFDF9); ` +
          `border: 1px solid var(--accent-success); border-radius: 999px; padding: 4px 14px; ` +
          `color: var(--accent-success); font-weight: 700;">${t}</span>`;
        this.infoMetrics.innerHTML =
          chip(`Joint MAE ${info.val_joint_mae_deg ?? '—'}°`) +
          chip(`Gripper accuracy ${info.gripper_accuracy || '—'}`);
      }

      if (this.infoContract) {
        const tag = (t) => `<span style="color: var(--accent-primary); font-weight: 700;">${t}</span>`;
        this.infoContract.innerHTML =
          `<div style="line-height: 1.7;">${tag('IN&nbsp;&nbsp;→&nbsp;')} ${info.obs_contract || '—'}</div>` +
          `<div style="line-height: 1.7; margin-top: 6px;">${tag('OUT&nbsp;→&nbsp;')} ${info.act_contract || '—'}</div>`;
      }

      if (this.infoFile) {
        const kv = (k, v) => `<div style="line-height: 1.7;">` +
          `<span style="color: var(--text-muted);">${k}</span> <span>${v}</span></div>`;
        this.infoFile.innerHTML =
          kv('File:', `${info.model_name} · ${info.file_size_kb ?? '?'} KB · exported ${info.exported || '—'}`) +
          `<div style="margin-top: 6px; color: var(--text-muted); line-height: 1.6;">${info.framework || ''}</div>` +
          `<div style="margin-top: 4px; color: var(--text-muted); line-height: 1.6;">${info.inference || ''}</div>` +
          `<div style="margin-top: 8px; line-height: 1.6;">` +
          `<span style="color: var(--accent-success); font-weight: 700;">Safety:</span> ` +
          `<span>${info.safety || ''}</span></div>`;
      }
    } catch (e) { /* offline UI mode */ }
  },

  async refreshModels() {
    try {
      const res = await fetch(this.api('/api/onnx/models'), { cache: 'no-store' });
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
      const res = await fetch(this.api('/api/onnx/status'), { cache: 'no-store' });
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
      const res = await fetch(this.api('/api/onnx/load'), {
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
      const res = await fetch(this.api('/api/onnx/start'), { method: 'POST' });
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
      const res = await fetch(this.api('/api/onnx/stop'), { method: 'POST' });
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
    const res = await fetch(this.api('/api/vision/status'));
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
