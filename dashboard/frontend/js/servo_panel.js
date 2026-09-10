/* ==========================================================================
   SERVO CONTROL PANEL & ASSEMBLY HELPER (JS)
   ==========================================================================
   Project:  Vision-Based Autonomous Robotic Arm
   File:     servo_panel.js
   Location: dashboard/frontend/js/

   PURPOSE:
     Manages 6-DOF joint sliders, Lock 90° assembly mode, Home position button,
     Emergency Stop button, and Serial port connection management.
   ========================================================================== */

const ServoPanel = {
  NUM_SERVOS: 6,
  sliders: [],
  valueDisplays: [],
  currentAngles: [90, 90, 90, 90, 90, 140],
  lastSendTime: 0,
  sendIntervalMs: 33, // ~30Hz send rate limit

  init() {
    this.cacheDOM();
    this.bindEvents();
    this.fetchPorts();
  },

  cacheDOM() {
    for (let i = 0; i < this.NUM_SERVOS; i++) {
      this.sliders[i] = document.getElementById(`sliderServo${i}`);
      this.valueDisplays[i] = document.getElementById(`valServo${i}`);
    }

    this.btnLock90 = document.getElementById('btnLock90');
    this.btnHome = document.getElementById('btnHome');
    this.btnSweep = document.getElementById('btnSweep');
    this.btnEstop = document.getElementById('btnEstop');
    this.btnResetEstop = document.getElementById('btnResetEstop');
    this.btnAutoConnect = document.getElementById('btnAutoConnect');
    this.btnConnect = document.getElementById('btnConnect');
    this.btnDisconnect = document.getElementById('btnDisconnect');
    this.portSelect = document.getElementById('portSelect');
  },

  bindEvents() {
    // Slider input listeners (manual drag throttled sending)
    for (let i = 0; i < this.NUM_SERVOS; i++) {
      if (this.sliders[i]) {
        this.sliders[i].addEventListener('input', () => {
          let val = parseInt(this.sliders[i].value, 10);
          val = Math.min(180, Math.max(0, val)); // Full range 0° to 180° testing limit
          this.currentAngles[i] = val;
          if (this.valueDisplays[i]) {
            this.valueDisplays[i].textContent = `${val}°`;
          }
          this.throttledSendAngles();
        });
      }
    }

    // Lock All at 90° Button (Decision #19 & #20 — Smooth S-Curve Lock)
    if (this.btnLock90) {
      this.btnLock90.addEventListener('click', () => {
        App.sendWS('lock90');
        App.log('Action: Smooth transition to Lock All at 90°...');
        if (window.TeleopPanel) {
          window.TeleopPanel.integratedAngles = [90, 90, 90, 90, 90, 90];
          window.TeleopPanel.smoothedAngles = [90, 90, 90, 90, 90, 90];
        }
      });
    }

    // Move to Home Position Button (Decision #20 — Smooth S-Curve Home)
    if (this.btnHome) {
      this.btnHome.addEventListener('click', () => {
        App.sendWS('home');
        App.log('Action: Smooth transition to Home Position...');
        if (window.TeleopPanel) {
          window.TeleopPanel.integratedAngles = [90, 90, 90, 90, 90, 140];
          window.TeleopPanel.smoothedAngles = [90, 90, 90, 90, 90, 140];
        }
      });
    }

    // Run Joint Sweep Test Button (Decision #19 & #20 — Smooth S-Curve Sweep)
    if (this.btnSweep) {
      this.btnSweep.addEventListener('click', () => {
        App.sendWS('sweep');
        App.log('Action: Started Zero-Jerk Joint Sweep Test Routine...');
      });
    }

    // Emergency Stop Button (Decision #5)
    if (this.btnEstop) {
      this.btnEstop.addEventListener('click', () => {
        App.sendWS('estop');
        App.log('CRITICAL: EMERGENCY STOP ACTIVATED!');
      });
    }

    // Reset E-Stop Button
    if (this.btnResetEstop) {
      this.btnResetEstop.addEventListener('click', () => {
        App.sendWS('reset_estop');
        App.log('Action: Emergency Stop Reset.');
      });
    }

    // Serial Port Connection Management
    if (this.btnAutoConnect) {
      this.btnAutoConnect.addEventListener('click', () => this.autoConnectPort());
    }

    if (this.btnConnect) {
      this.btnConnect.addEventListener('click', () => this.connectSelectedPort());
    }

    if (this.btnDisconnect) {
      this.btnDisconnect.addEventListener('click', () => this.disconnectPort());
    }
  },

  /* Trigger single servo solo test (Decision #19) */
  testServo(index) {
    App.sendWS('test_servo', { index });
    App.log(`Action: Testing Servo ${index} in isolation...`);
  },

  /* Get current angles array from sliders */
  getAnglesFromSliders() {
    const angles = [];
    for (let i = 0; i < this.NUM_SERVOS; i++) {
      let val = parseInt(this.sliders[i] ? this.sliders[i].value : this.currentAngles[i], 10);
      val = Math.min(180, Math.max(0, val));
      angles.push(val);
    }
    return angles;
  },

  /* Open Gripper to calibrated open angle via smooth gliding S-Curve */
  openGripper() {
    const openAngle = parseInt(document.getElementById('angleGripperOpen')?.value || document.getElementById('inputGripperOpenCard')?.value || 140, 10);
    const startAngle = this.currentAngles[5];
    const durationMs = 400; // 400ms smooth gliding transition
    const steps = 15;
    let stepCount = 0;

    if (window.TeleopPanel) window.TeleopPanel.gripperState = 0; // 0 = OPEN

    const timer = setInterval(() => {
      stepCount++;
      const progress = stepCount / steps;
      const ease = 0.5 * (1.0 - Math.cos(Math.PI * progress));
      const currentVal = Math.round(startAngle + (openAngle - startAngle) * ease);

      this.currentAngles[5] = currentVal;
      if (this.sliders[5]) this.sliders[5].value = currentVal;
      if (this.valueDisplays[5]) this.valueDisplays[5].textContent = `${currentVal}°`;
      if (window.TeleopPanel) {
        window.TeleopPanel.integratedAngles[5] = currentVal;
        window.TeleopPanel.smoothedAngles[5] = currentVal;
      }
      this.throttledSendAngles();

      if (stepCount >= steps) {
        clearInterval(timer);
        if (window.App && App.log) App.log(`Action: Gripper Glided Open → State 0 (${openAngle}°)`);
      }
    }, 25);
  },

  /* Close Gripper to calibrated close angle via smooth gliding S-Curve */
  closeGripper() {
    const closeAngle = parseInt(document.getElementById('angleGripperClosed')?.value || document.getElementById('inputGripperClosedCard')?.value || 85, 10);
    const startAngle = this.currentAngles[5];
    const durationMs = 400; // 400ms smooth gliding transition
    const steps = 15;
    let stepCount = 0;

    if (window.TeleopPanel) window.TeleopPanel.gripperState = 1; // 1 = CLOSED

    const timer = setInterval(() => {
      stepCount++;
      const progress = stepCount / steps;
      const ease = 0.5 * (1.0 - Math.cos(Math.PI * progress));
      const currentVal = Math.round(startAngle + (closeAngle - startAngle) * ease);

      this.currentAngles[5] = currentVal;
      if (this.sliders[5]) this.sliders[5].value = currentVal;
      if (this.valueDisplays[5]) this.valueDisplays[5].textContent = `${currentVal}°`;
      if (window.TeleopPanel) {
        window.TeleopPanel.integratedAngles[5] = currentVal;
        window.TeleopPanel.smoothedAngles[5] = currentVal;
      }
      this.throttledSendAngles();

      if (stepCount >= steps) {
        clearInterval(timer);
        if (window.App && App.log) App.log(`Action: Gripper Glided Closed → State 1 (${closeAngle}°)`);
      }
    }, 25);
  },

  /* Set sliders from an array of angles */
  setSlidersFromAngles(angles) {
    for (let i = 0; i < Math.min(angles.length, this.NUM_SERVOS); i++) {
      this.currentAngles[i] = angles[i];
      if (this.sliders[i]) this.sliders[i].value = angles[i];
      if (this.valueDisplays[i]) this.valueDisplays[i].textContent = `${angles[i]}°`;
    }
  },

  /* Called by TeleopPanel in Direct Joint Control Mode to drive sliders & hardware */
  setAngles(angles) {
    this.setSlidersFromAngles(angles);
    this.throttledSendAngles();
  },

  /* Throttled WebSocket sender to maintain ~30Hz packet rate */
  throttledSendAngles() {
    const now = Date.now();
    if (now - this.lastSendTime >= this.sendIntervalMs) {
      this.lastSendTime = now;
      const angles = this.getAnglesFromSliders();
      App.sendWS('set_angles', { angles });
    }
  },

  /* Update sliders when backend sends status update */
  updateSlidersFromBackend(angles) {
    // Only update if user is NOT actively dragging sliders, typing in input boxes, or teleoperating
    if (document.activeElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'SELECT')) {
      return;
    }
    if (window.TeleopPanel && window.TeleopPanel.gamepadIndex !== null) {
      return;
    }
    this.setSlidersFromAngles(angles);
    if (window.TeleopPanel) {
      window.TeleopPanel.integratedAngles = [...angles];
      window.TeleopPanel.smoothedAngles = [...angles];
    }
  },

  /* Fetch list of available serial ports via REST API */
  async fetchPorts() {
    try {
      const res = await fetch('/api/ports');
      if (!res.ok) return;
      const data = await res.json();
      
      if (this.portSelect) {
        this.portSelect.innerHTML = '';
        if (data.ports && data.ports.length > 0) {
          data.ports.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.port;
            opt.textContent = `${p.port} (${p.board_name})`;
            if (p.is_arduino) opt.selected = true;
            this.portSelect.appendChild(opt);
          });
        } else {
          this.portSelect.innerHTML = '<option value="">No Arduino ports detected</option>';
        }
      }
    } catch (e) {
      console.warn('Could not fetch serial ports:', e);
    }
  },

  async autoConnectPort() {
    try {
      App.log('Auto-detecting Arduino port...');
      const res = await fetch('/api/auto-connect', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        App.log(`Success: ${data.message}`);
      } else {
        App.log(`Failed: ${data.detail || 'Could not auto-connect'}`);
      }
    } catch (e) {
      App.log(`Connection error: ${e.message}`);
    }
  },

  async connectSelectedPort() {
    const selectedPort = this.portSelect ? this.portSelect.value : '';
    if (!selectedPort) {
      App.log('Please select a serial port first.');
      return;
    }

    try {
      App.log(`Connecting to ${selectedPort}...`);
      const res = await fetch('/api/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: selectedPort, baudrate: 115200 })
      });
      const data = await res.json();
      if (res.ok) {
        App.log(`Success: ${data.message}`);
      } else {
        App.log(`Error: ${data.detail || 'Connection failed'}`);
      }
    } catch (e) {
      App.log(`Connection error: ${e.message}`);
    }
  },

  async disconnectPort() {
    try {
      const res = await fetch('/api/disconnect', { method: 'POST' });
      const data = await res.json();
      App.log(`Disconnected: ${data.message}`);
    } catch (e) {
      App.log(`Disconnect error: ${e.message}`);
    }
  }
};

// Export to window scope
window.ServoPanel = ServoPanel;

document.addEventListener('DOMContentLoaded', () => {
  ServoPanel.init();
});
