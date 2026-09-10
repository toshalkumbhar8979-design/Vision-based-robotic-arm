/* ==========================================================================
   TELEOPERATION PANEL & DUAL-MODE PS5 CONTROLLER INTEGRATION (JS)
   ==========================================================================
   Project:  Vision-Based Autonomous Robotic Arm
   File:     teleop_panel.js
   Location: dashboard/frontend/js/

   PURPOSE:
     Handles live PS5 DualSense controller teleoperation with 2 modes:
       1. Cartesian Inverse Kinematics (IK) Mode (Left Stick: X/Y, Right Stick: Z height)
       2. Direct Joint Motor Control Mode (Velocity-Based Rate Integrator)
     
     GRIPPER STATE MACHINE:
       - Default / Unlocked: R2 released -> Gripper stays at 10°.
       - R2 Pressed: Gripper moves slowly towards 180°.
       - R2 Released: Gripper travels back to 10° slowly.
       - L2 Pressed: Gripper LOCKS at current angle (R2 ignored).
       - L2 Pressed again: Gripper UNLOCKS and travels back to 10° slowly.
   ========================================================================== */

const TeleopPanel = {
  gamepadIndex: null,
  animFrameId: null,
  activeMode: 'joint', // 'ik' or 'joint'
  isGripperLocked: false,
  L1: 9.5,
  L2: 12.0,
  L3: 9.0,
  L4: 14.0,
  integratedAngles: [90, 90, 90, 90, 90, 140], // Continuous Velocity-Based Integrator
  smoothedAngles: [90, 90, 90, 90, 90, 140],   // EMA Low-Pass Filter State

  buttonNames: [
    'Cross (×)', 'Circle (○)', 'Square (□)', 'Triangle (△)',
    'L1', 'R1', 'L2', 'R2',
    'Share', 'Options', 'L3', 'R3',
    'D-Pad ↑', 'D-Pad ↓', 'D-Pad ←', 'D-Pad →',
    'PS', 'Touchpad'
  ],

  init() {
    this.cacheDOM();
    this.buildButtonIndicators();
    this.bindEvents();
    this.startLoop();
    this.loadKinematicsConfig();
    this.updateModeUI();
  },

  cacheDOM() {
    this.statusPill = document.getElementById('ps5StatusPill');
    this.statusText = document.getElementById('ps5StatusText');
    this.leftDot = document.getElementById('ps5LeftDot');
    this.rightDot = document.getElementById('ps5RightDot');
    this.leftVal = document.getElementById('ps5LeftVal');
    this.rightVal = document.getElementById('ps5RightVal');
    this.l2Fill = document.getElementById('ps5L2Fill');
    this.r2Fill = document.getElementById('ps5R2Fill');
    this.l1Fill = document.getElementById('ps5L1Fill');
    this.r1Fill = document.getElementById('ps5R1Fill');
    this.l2Val = document.getElementById('ps5L2Val');
    this.r2Val = document.getElementById('ps5R2Val');
    this.l1Val = document.getElementById('ps5L1Val');
    this.r1Val = document.getElementById('ps5R1Val');
    this.buttonsGrid = document.getElementById('ps5ButtonsGrid');
    this.axesList = document.getElementById('ps5AxesList');
    this.btnSaveKinematics = document.getElementById('btnSaveKinematics');

    // Teleop Mode Switcher DOM elements
    this.btnToggleMode = document.getElementById('btnToggleTeleopMode');
    this.lblModeBtnText = document.getElementById('lblModeBtnText');
    this.lblActiveModePill = document.getElementById('lblActiveModePill');
    this.lblTeleopNoteTitle = document.getElementById('lblTeleopNoteTitle');
    this.lblTeleopNoteText = document.getElementById('lblTeleopNoteText');

    if (this.axesList) {
      this.axesList.innerHTML = '<div style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-muted); padding: 12px 0;">No controller connected.<br>Press any button on PS5 DualSense to display live axes.</div>';
    }
  },

  buildButtonIndicators() {
    if (!this.buttonsGrid) return;
    this.buttonsGrid.innerHTML = '';
    this.buttonNames.forEach((name, i) => {
      const div = document.createElement('div');
      div.className = 'btn-indicator';
      div.id = `ps5Btn${i}`;
      div.textContent = name;
      this.buttonsGrid.appendChild(div);
    });
  },

  bindEvents() {
    if (this.btnSaveKinematics) {
      this.btnSaveKinematics.addEventListener('click', () => this.saveKinematicsConfig());
    }

    window.addEventListener('gamepadconnected', (e) => {
      this.gamepadIndex = e.gamepad.index;
      if (this.statusPill && this.statusText) {
        this.statusPill.className = 'status-pill connected';
        this.statusText.textContent = `Connected: ${e.gamepad.id}`;
      }
      if (window.App && App.log) {
        App.log(`Teleoperation Mode Switched: ${this.activeMode.toUpperCase()} (${this.activeMode === 'ik' ? 'Cartesian 3D Space: X/Y/Z Joystick Control' : 'Direct Joint Rate Control'})`);
      }
    });

    window.addEventListener('gamepaddisconnected', (e) => {
      if (e.gamepad.index === this.gamepadIndex) {
        this.gamepadIndex = null;
        if (this.statusPill && this.statusText) {
          this.statusPill.className = 'status-pill';
          this.statusText.textContent = 'PS5 Controller Disconnected';
        }
        if (window.App && App.log) {
          App.log('PS5 DualSense Controller Disconnected.');
        }
      }
    });
  },

  toggleMode() {
    this.activeMode = (this.activeMode === 'joint') ? 'ik' : 'joint';
    this.cartesianPos = this.forwardKinematics(this.integratedAngles);
    console.log('[TeleopPanel] Mode toggled to:', this.activeMode);

    this.updateModeUI();
  },

  updateModeUI() {
    const btnText = document.getElementById('lblModeBtnText');
    const pill = document.getElementById('lblActiveModePill');
    const noteTitle = document.getElementById('lblTeleopNoteTitle');
    const noteText = document.getElementById('lblTeleopNoteText');

    if (this.activeMode === 'ik') {
      if (btnText) btnText.textContent = 'Direct Joint Control Mode →';
      if (pill) {
        pill.textContent = 'Active: Cartesian IK';
        pill.style.background = 'rgba(46, 125, 50, 0.15)';
        pill.style.color = '#2E7D32';
      }
      if (noteTitle) noteTitle.textContent = 'Cartesian Inverse Kinematics (IK) Teleoperation Architecture';
      if (noteText) {
        noteText.innerHTML = `
          1. <strong>Left Stick (X / Y):</strong> Moves the end-effector in Cartesian table space (centimeters relative to base).<br>
          2. <strong>Right Stick (Z):</strong> Moves end-effector Z-height up and down towards table.<br>
          3. <strong>R1 / L1 Bumpers:</strong> Rotates Wrist Roll clockwise / anti-clockwise.<br>
          4. <strong>Cross (×) / Circle (○) Buttons:</strong> Changes Wrist Pitch angle.<br>
          5. <strong>R2 / L2 Triggers:</strong> R2 closes gripper towards 85°; releasing R2 opens to 140°; L2 locks/unlocks position.<br>
          6. <strong>Options Button (≡):</strong> Smoothly returns all 6 joints to Home Position [90°, 90°, 90°, 90°, 90°, 140°].
        `;
      }
      if (window.App && App.log) {
        App.log(`Teleoperation Mode Switched: CARTESIAN IK (Current X:${this.cartesianPos.x}cm, Y:${this.cartesianPos.y}cm, Z:${this.cartesianPos.z}cm)`);
      }
    } else {
      if (btnText) btnText.textContent = 'Cartesian IK Mode →';
      if (pill) {
        pill.textContent = 'Active: Direct Joint Control';
        pill.style.background = 'rgba(196, 120, 74, 0.15)';
        pill.style.color = 'var(--accent-primary)';
      }
      if (noteTitle) noteTitle.textContent = 'Direct Joint Motor Control Teleoperation Architecture';
      if (noteText) {
        noteText.innerHTML = `
          1. <strong>Left Stick (X):</strong> Smoothly rotates Base Servo (0° to 180°).<br>
          2. <strong>Left Stick (Y):</strong> Smoothly rotates Shoulder Servo (0° to 180°).<br>
          3. <strong>Right Stick (Y):</strong> Smoothly rotates Elbow Servo (0° to 180°).<br>
          4. <strong>R1 / L1 Bumpers:</strong> Smoothly rotates Wrist Roll CW / CCW.<br>
          5. <strong>Cross (×) / Circle (○) Buttons:</strong> Smoothly rotates Wrist Pitch UP / DOWN.<br>
          6. <strong>R2 / L2 Triggers:</strong> R2 closes gripper towards 85°; releasing R2 opens to 140°; L2 locks/unlocks position.<br>
          7. <strong>Options Button (≡):</strong> Smoothly returns all 6 joints to Home Position [90°, 90°, 90°, 90°, 90°, 140°].
        `;
      }
      if (window.App && App.log) {
        App.log('Teleoperation Mode Switched: DIRECT JOINT RATE CONTROL');
      }
    }
  },

  solveIK(x, y, z, theta4_val = 90, theta5_val = 90, theta6_val = 140) {
    const L1 = parseFloat(this.L1) || 9.5;
    const L2 = parseFloat(this.L2) || 12.0;
    const L3 = parseFloat(this.L3) || 9.0;

    if (isNaN(x) || isNaN(y) || isNaN(z)) {
      return [90, 90, 90, theta4_val, theta5_val, theta6_val];
    }

    if (y < 1.0) y = 1.0;

    // 1. Base Angle (θ1)
    const theta1 = 90.0 + (Math.atan2(x, y) * (180.0 / Math.PI));

    // 2. Radial distance from base
    const r = Math.hypot(x, y);
    const z_rel = z - L1;

    // 3. Planar distance D from shoulder (0,0) to wrist joint (r, z_rel)
    const D = Math.hypot(r, z_rel);
    const max_reach = L2 + L3;
    const min_reach = Math.abs(L2 - L3);
    const D_clamped = Math.max(min_reach + 0.001, Math.min(max_reach - 0.001, D));

    // 4. Law of Cosines for Elbow (θ3)
    const cos_gamma = (L2 * L2 + L3 * L3 - D_clamped * D_clamped) / (2.0 * L2 * L3);
    const gamma = Math.acos(Math.max(-1.0, Math.min(1.0, cos_gamma)));
    const theta3 = 45.0 + ((Math.PI - gamma) * (180.0 / Math.PI));

    // 5. Law of Cosines for Shoulder (θ2)
    const alpha1 = Math.atan2(z_rel, r);
    const cos_alpha2 = (L2 * L2 + D_clamped * D_clamped - L3 * L3) / (2.0 * L2 * D_clamped);
    const alpha2 = Math.acos(Math.max(-1.0, Math.min(1.0, cos_alpha2)));
    const psi = alpha1 + alpha2;
    const theta2 = 180.0 - (psi * (180.0 / Math.PI));

    const safeNum = (v, def = 90) => isNaN(v) ? def : v;

    return [
      Math.max(0, Math.min(180, Math.round(safeNum(theta1, 90)))),
      Math.max(15, Math.min(165, Math.round(safeNum(theta2, 90)))),
      Math.max(15, Math.min(165, Math.round(safeNum(theta3, 90)))),
      Math.max(0, Math.min(180, Math.round(safeNum(theta4_val, 90)))),
      Math.max(0, Math.min(180, Math.round(safeNum(theta5_val, 90)))),
      Math.max(85, Math.min(140, Math.round(safeNum(theta6_val, 140))))
    ];
  },

  forwardKinematics(angles) {
    if (!angles || !Array.isArray(angles) || angles.some(a => isNaN(a))) {
      return { x: 0.0, y: 15.0, z: 15.0, pitch_deg: 90.0, roll_deg: 90.0 };
    }
    const [theta1, theta2, theta3] = angles;
    const L1 = parseFloat(this.L1) || 9.5;
    const L2 = parseFloat(this.L2) || 12.0;
    const L3 = parseFloat(this.L3) || 9.0;

    const b = (theta1 - 90.0) * (Math.PI / 180.0);
    const s = (180.0 - theta2) * (Math.PI / 180.0);
    const e_rel = (theta3 - 45.0) * (Math.PI / 180.0);
    const e = s - e_rel;

    const r = L2 * Math.cos(s) + L3 * Math.cos(e);
    const z = L1 + L2 * Math.sin(s) + L3 * Math.sin(e);

    const x = r * Math.sin(b);
    const y = r * Math.cos(b);

    return {
      x: parseFloat((isNaN(x) ? 0 : x).toFixed(1)),
      y: parseFloat((isNaN(y) ? 15.0 : y).toFixed(1)),
      z: parseFloat((isNaN(z) ? 15.0 : z).toFixed(1)),
      pitch_deg: (angles && angles[3]) || 90.0,
      roll_deg: (angles && angles[4]) || 90.0
    };
  },

  async loadKinematicsConfig() {
    // 1. Instantly restore from localStorage if available
    const localOpen = localStorage.getItem('gripper_open');
    const localClosed = localStorage.getItem('gripper_closed');
    const goc = document.getElementById('inputGripperOpenCard');
    const gcc = document.getElementById('inputGripperClosedCard');
    const go = document.getElementById('angleGripperOpen');
    const gc = document.getElementById('angleGripperClosed');

    if (localOpen) {
      if (goc) goc.value = localOpen;
      if (go) go.value = localOpen;
    }
    if (localClosed) {
      if (gcc) gcc.value = localClosed;
      if (gc) gc.value = localClosed;
    }

    // 2. Load from backend configuration file
    try {
      const res = await fetch('/api/kinematics');
      if (!res.ok) return;
      const cfg = await res.json();
      
      const l1 = document.getElementById('inputL1');
      const l2 = document.getElementById('inputL2');
      const l3 = document.getElementById('inputL3');
      const l4 = document.getElementById('inputL4');

      if (l1 && cfg.L1) l1.value = cfg.L1;
      if (l2 && cfg.L2) l2.value = cfg.L2;
      if (l3 && cfg.L3) l3.value = cfg.L3;
      if (l4 && cfg.L4) l4.value = cfg.L4;
      if (cfg.gripper_closed && !localClosed) {
        if (gc) gc.value = cfg.gripper_closed;
        if (gcc) gcc.value = cfg.gripper_closed;
        localStorage.setItem('gripper_closed', cfg.gripper_closed);
      }
      if (cfg.gripper_open && !localOpen) {
        if (go) go.value = cfg.gripper_open;
        if (goc) goc.value = cfg.gripper_open;
        localStorage.setItem('gripper_open', cfg.gripper_open);
      }

      if (cfg.offsets) {
        for (let i = 0; i < 5; i++) {
          const el = document.getElementById(`offsetServo${i}`);
          if (el) el.value = cfg.offsets[i] || 0;
        }
      }
    } catch (e) {
      console.warn('Could not load kinematics config:', e);
    }
  },

  async saveKinematicsConfig() {
    const l1 = parseFloat(document.getElementById('inputL1')?.value || 9.5);
    const l2 = parseFloat(document.getElementById('inputL2')?.value || 12.0);
    const l3 = parseFloat(document.getElementById('inputL3')?.value || 9.0);
    const l4 = parseFloat(document.getElementById('inputL4')?.value || 14.0);
    const gc = parseInt(document.getElementById('angleGripperClosed')?.value || document.getElementById('inputGripperClosedCard')?.value || 85, 10);
    const go = parseInt(document.getElementById('angleGripperOpen')?.value || document.getElementById('inputGripperOpenCard')?.value || 140, 10);

    localStorage.setItem('gripper_open', go);
    localStorage.setItem('gripper_closed', gc);

    const offsets = [];
    for (let i = 0; i < 5; i++) {
      offsets.push(parseInt(document.getElementById(`offsetServo${i}`)?.value || 0, 10));
    }

    try {
      const res = await fetch('/api/kinematics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ L1: l1, L2: l2, L3: l3, L4: l4, offsets, gripper_closed: gc, gripper_open: go })
      });
      if (res.ok && window.App && App.log) {
        App.log(`Saved Kinematic Calibration: L1=${l1}cm, L2=${l2}cm, L3=${l3}cm, L4=${l4}cm | Gripper Open=${go}°, Close=${gc}°`);
      }
    } catch (e) {
      if (window.App && App.log) App.log(`Failed to save kinematic calibration: ${e.message}`);
    }
  },

  applyDeadzone(val, deadzone = 0.08) {
    return Math.abs(val) < deadzone ? 0 : val;
  },

  startLoop() {
    const update = () => {
      if (this.gamepadIndex !== null) {
        const gp = navigator.getGamepads()[this.gamepadIndex];
        if (gp) {
          this.updateSticks(gp);
          this.updateTriggers(gp);
          this.updateButtons(gp);
          this.updateAxes(gp);
          this.processControlInputs(gp);
        }
      } else {
        // Scan for gamepads if not yet indexed
        const gamepads = navigator.getGamepads ? navigator.getGamepads() : [];
        for (let i = 0; i < gamepads.length; i++) {
          if (gamepads[i]) {
            this.gamepadIndex = gamepads[i].index;
            if (window.App && App.log) App.log(`PS5 DualSense Controller Auto-Detected: ${gamepads[i].id}`);
            break;
          }
        }
      }
      this.animFrameId = requestAnimationFrame(update);
    };
    update();
  },

  updateSticks(gp) {
    const lx = this.applyDeadzone(gp.axes[0] || 0);
    const ly = this.applyDeadzone(gp.axes[1] || 0);
    const rx = this.applyDeadzone(gp.axes[2] || 0);
    const ry = this.applyDeadzone(gp.axes[3] || 0);

    const maxOffset = 50;
    if (this.leftDot) {
      this.leftDot.style.left = `calc(50% + ${lx * maxOffset}px)`;
      this.leftDot.style.top = `calc(50% + ${ly * maxOffset}px)`;
    }
    if (this.rightDot) {
      this.rightDot.style.left = `calc(50% + ${rx * maxOffset}px)`;
      this.rightDot.style.top = `calc(50% + ${ry * maxOffset}px)`;
    }

    if (this.leftVal) this.leftVal.textContent = `X: ${lx.toFixed(2)} Y: ${ly.toFixed(2)}`;
    if (this.rightVal) this.rightVal.textContent = `X: ${rx.toFixed(2)} Y: ${ry.toFixed(2)}`;
  },

  updateTriggers(gp) {
    const l2 = gp.buttons[6] ? (gp.buttons[6].value !== undefined ? gp.buttons[6].value : (gp.buttons[6].pressed ? 1 : 0)) : 0;
    const r2 = gp.buttons[7] ? (gp.buttons[7].value !== undefined ? gp.buttons[7].value : (gp.buttons[7].pressed ? 1 : 0)) : 0;
    const l1 = gp.buttons[4] ? (gp.buttons[4].value !== undefined ? gp.buttons[4].value : (gp.buttons[4].pressed ? 1 : 0)) : 0;
    const r1 = gp.buttons[5] ? (gp.buttons[5].value !== undefined ? gp.buttons[5].value : (gp.buttons[5].pressed ? 1 : 0)) : 0;

    if (this.l2Fill) this.l2Fill.style.width = `${l2 * 100}%`;
    if (this.r2Fill) this.r2Fill.style.width = `${r2 * 100}%`;
    if (this.l1Fill) this.l1Fill.style.width = `${l1 * 100}%`;
    if (this.r1Fill) this.r1Fill.style.width = `${r1 * 100}%`;

    if (this.l2Val) this.l2Val.textContent = `${Math.round(l2 * 100)}%`;
    if (this.r2Val) this.r2Val.textContent = `${Math.round(r2 * 100)}%`;
    if (this.l1Val) this.l1Val.textContent = `${Math.round(l1 * 100)}%`;
    if (this.r1Val) this.r1Val.textContent = `${Math.round(r1 * 100)}%`;
  },

  updateButtons(gp) {
    for (let i = 0; i < Math.min(gp.buttons.length, this.buttonNames.length); i++) {
      const el = document.getElementById(`ps5Btn${i}`);
      const btn = gp.buttons[i];
      const isPressed = btn ? (btn.pressed || btn.value > 0.3) : false;
      if (el) {
        if (isPressed) {
          el.style.backgroundColor = 'var(--accent-primary)';
          el.style.borderColor = 'var(--accent-primary)';
          el.style.color = '#FAF7F2';
        } else {
          el.style.backgroundColor = 'var(--bg-page)';
          el.style.borderColor = 'var(--border-subtle)';
          el.style.color = 'var(--text-muted)';
        }
      }
    }
  },

  updateAxes(gp) {
    if (!this.axesList) return;
    if (this.axesList.children.length !== gp.axes.length) {
      this.axesList.innerHTML = '';
      for (let i = 0; i < gp.axes.length; i++) {
        const row = document.createElement('div');
        row.className = 'axis-row';
        row.style.cssText = 'display: flex; align-items: center; gap: 10px; margin-bottom: 6px;';
        row.innerHTML = `
          <span style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-muted); width: 50px;">Axis ${i}</span>
          <div style="flex: 1; height: 8px; background: var(--bg-page); border: 1px solid var(--border-subtle); border-radius: 4px; overflow: hidden; position: relative;">
            <div id="ps5AxisBar${i}" style="position: absolute; height: 100%; background: var(--accent-primary); transition: all 0.05s linear;"></div>
          </div>
          <span id="ps5AxisVal${i}" style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-main); width: 45px; text-align: right;">0.00</span>
        `;
        this.axesList.appendChild(row);
      }
    }

    for (let i = 0; i < gp.axes.length; i++) {
      const val = gp.axes[i];
      const pct = ((val + 1) / 2) * 100;
      const bar = document.getElementById(`ps5AxisBar${i}`);
      const valEl = document.getElementById(`ps5AxisVal${i}`);
      if (bar) {
        bar.style.left = val >= 0 ? '50%' : `${pct}%`;
        bar.style.width = `${Math.abs(val) * 50}%`;
      }
      if (valEl) valEl.textContent = val.toFixed(2);
    }
  },

  isButtonPressed(btn) {
    if (!btn) return false;
    if (typeof btn === 'object') {
      return btn.pressed || (btn.value !== undefined && btn.value > 0.3);
    }
    return btn === 1;
  },

  processControlInputs(gp) {
    const stepSpeed = 1.0; // Degrees per frame at full stick deflection (~60°/sec)

    const xPressed = this.isButtonPressed(gp.buttons[0]);      // Cross (×) -> Wrist Pitch UP
    const circlePressed = this.isButtonPressed(gp.buttons[1]); // Circle (○) -> Wrist Pitch DOWN
    const l1Pressed = this.isButtonPressed(gp.buttons[4]);     // L1 Bumper -> Wrist Roll CCW
    const r1Pressed = this.isButtonPressed(gp.buttons[5]);     // R1 Bumper -> Wrist Roll CW
    const l2Pressed = this.isButtonPressed(gp.buttons[6]);     // L2 Trigger -> Gripper Lock Toggle
    const optionsPressed = this.isButtonPressed(gp.buttons[9]);// Options (≡) -> Move to Home Position
    const r2Btn = gp.buttons[7];
    const r2Val = r2Btn ? (r2Btn.value !== undefined ? r2Btn.value : (r2Btn.pressed ? 1 : 0)) : 0;

    const lx = this.applyDeadzone(gp.axes[0] || 0); // Base Servo (Ch 0)
    const ly = this.applyDeadzone(gp.axes[1] || 0); // Shoulder Servo (Ch 1)
    const ry = this.applyDeadzone(gp.axes[3] || 0); // Elbow Servo (Ch 2)

    // Handle Options Button Press (Move to Home Position smoothly via Cosine S-Curve)
    if (optionsPressed && !this.wasOptionsPressed) {
      if (window.App && App.sendWS) {
        App.sendWS('home');
        if (window.App && App.log) {
          App.log('Action: PS5 Options button pressed — Smooth Cosine S-Curve transition to Home Position...');
        }
      }
      this.isHomingSmoothly = true;
      this.homingProgress = 0.0;
      this.homingStartAngles = [...this.integratedAngles];
    }
    this.wasOptionsPressed = optionsPressed;

    // Smooth Cosine S-Curve Homing Interpolation (~1.2 seconds / 72 frames)
    if (this.isHomingSmoothly) {
      this.homingProgress += 1.0 / 72.0;
      if (this.homingProgress >= 1.0) {
        this.homingProgress = 1.0;
        this.isHomingSmoothly = false;
      }
      const ease = 0.5 * (1.0 - Math.cos(Math.PI * this.homingProgress));
      const openAngle = parseInt(document.getElementById('angleGripperOpen')?.value || document.getElementById('inputGripperOpenCard')?.value || 140, 10);
      const targetHome = [90, 90, 90, 90, 90, openAngle];
      for (let i = 0; i < 6; i++) {
        this.integratedAngles[i] = this.homingStartAngles[i] + (targetHome[i] - this.homingStartAngles[i]) * ease;
        this.smoothedAngles[i] = Math.round(this.integratedAngles[i]);
      }
    }

    // Handle Gripper Lock Toggle (L2)
    if (l2Pressed && !this.wasL2Pressed) {
      this.isGripperLocked = !this.isGripperLocked;
      if (window.App && App.log) {
        App.log(`Gripper Lock ${this.isGripperLocked ? 'LOCKED (Position Saved)' : 'UNLOCKED (Returning to 145°)'}`);
      }
    }
    this.wasL2Pressed = l2Pressed;

    // Gripper Binary State Control (R2 Smoothly Glides Closed, L2 Smoothly Glides Open)
    const openAngle = parseInt(document.getElementById('angleGripperOpen')?.value || 140, 10);
    const closeAngle = parseInt(document.getElementById('angleGripperClosed')?.value || 85, 10);

    if (r2Val > 0.05) {
      // R2 Pressed -> Smoothly glide gripper closed towards closeAngle
      if (this.integratedAngles[5] > closeAngle) {
        this.integratedAngles[5] = Math.max(closeAngle, this.integratedAngles[5] - (stepSpeed * 2.5));
      } else if (this.integratedAngles[5] < closeAngle) {
        this.integratedAngles[5] = Math.min(closeAngle, this.integratedAngles[5] + (stepSpeed * 2.5));
      }
      this.gripperState = 1; // 1 = CLOSED
    } else if (l2Pressed) {
      // L2 Pressed -> Smoothly glide gripper open towards openAngle
      if (this.integratedAngles[5] < openAngle) {
        this.integratedAngles[5] = Math.min(openAngle, this.integratedAngles[5] + (stepSpeed * 2.5));
      } else if (this.integratedAngles[5] > openAngle) {
        this.integratedAngles[5] = Math.max(openAngle, this.integratedAngles[5] - (stepSpeed * 2.5));
      }
      this.gripperState = 0; // 0 = OPEN
    }

    // Check if the user is actively manipulating any stick, button, or trigger
    // Wrist Pitch Control (Cross X / Circle O)
    if (xPressed) {
      this.integratedAngles[3] = Math.min(180, this.integratedAngles[3] + stepSpeed);
    } else if (circlePressed) {
      this.integratedAngles[3] = Math.max(0, this.integratedAngles[3] - stepSpeed);
    }

    // Wrist Roll Control (R1 / L1)
    if (r1Pressed) {
      this.integratedAngles[4] = Math.min(180, this.integratedAngles[4] + stepSpeed);
    } else if (l1Pressed) {
      this.integratedAngles[4] = Math.max(0, this.integratedAngles[4] - stepSpeed);
    }

    if (this.activeMode === 'joint') {
      // Direct Joint Motor Control Mode (Velocity Rate Integrator)
      if (Math.abs(lx) > 0.05) {
        // Reversed Base direction per user spec: Left Joystick LEFT moves Base LEFT
        this.integratedAngles[0] = Math.max(0, Math.min(180, this.integratedAngles[0] - (lx * stepSpeed * 1.5)));
      }
      if (Math.abs(ly) > 0.05) {
        this.integratedAngles[1] = Math.max(0, Math.min(180, this.integratedAngles[1] + (ly * stepSpeed * 1.5)));
      }
      if (Math.abs(ry) > 0.05) {
        // Reversed Elbow direction per user spec: Right Joystick FORWARD moves Elbow FORWARD
        this.integratedAngles[2] = Math.max(0, Math.min(180, this.integratedAngles[2] - (ry * stepSpeed * 1.5)));
      }
    } else if (this.activeMode === 'ik') {
      // Cartesian 3D Space IK Mode (Primary 3-DOF Joint Velocity Control)
      if (!this.cartesianPos) {
        this.cartesianPos = this.forwardKinematics(this.integratedAngles);
      }
      
      const posSpeed = 0.12; // cm per frame (~7.2 cm/sec for silky smooth precision)
      if (Math.abs(lx) > 0.05) {
        // Left stick LX: moves X (Left/Right)
        this.cartesianPos.x -= (lx * posSpeed);
      }
      if (Math.abs(ly) > 0.05) {
        // Left stick LY: moves Y (Forward/Backward)
        this.cartesianPos.y -= (ly * posSpeed);
      }
      if (Math.abs(ry) > 0.05) {
        // Right stick RY: moves Z (Up/Down)
        this.cartesianPos.z -= (ry * posSpeed);
      }

      // Clamp 3D Cartesian Position to safe physical wrist workspace box
      this.cartesianPos.x = Math.max(-18.0, Math.min(18.0, this.cartesianPos.x));
      this.cartesianPos.y = Math.max(4.0, Math.min(20.0, this.cartesianPos.y));
      this.cartesianPos.z = Math.max(2.0, Math.min(30.0, this.cartesianPos.z));

      // Solve 3-DOF IK for primary 3 joints (Base θ1, Shoulder θ2, Elbow θ3)
      const ikAngles = this.solveIK(
        this.cartesianPos.x,
        this.cartesianPos.y,
        this.cartesianPos.z,
        this.integratedAngles[3],
        this.integratedAngles[4],
        this.integratedAngles[5]
      );
      
      for (let i = 0; i < 3; i++) {
        this.integratedAngles[i] = ikAngles[i];
      }
    }

    // PRIME DIRECTIVE: Apply Exponential Moving Average (EMA) Low-Pass Filter with exact endpoint threshold snapping FOR ALL 6 SERVOS
    const alpha = 0.25; // Smooth motion interpolation factor
    for (let i = 0; i < 6; i++) {
      const targetVal = Math.round(this.integratedAngles[i]);
      const diff = Math.abs(targetVal - this.smoothedAngles[i]);
      if (diff <= 3 || targetVal === 0 || targetVal === 180) {
        // Snap smoothly when within 3° threshold or at hard limits (0°, 180°)
        this.smoothedAngles[i] = targetVal;
      } else {
        this.smoothedAngles[i] = Math.round((targetVal * alpha) + (this.smoothedAngles[i] * (1 - alpha)));
      }
    }

    // Check if controller is actively giving control inputs or smoothing towards target
    const isJoystickInput = (Math.abs(lx) > 0.05) || (Math.abs(ly) > 0.05) || (Math.abs(ry) > 0.05) ||
                            xPressed || circlePressed || r1Pressed || l1Pressed || l2Pressed || optionsPressed || (r2Val > 0.05) ||
                            this.isHomingSmoothly;

    if (isJoystickInput) {
      if (typeof ServoPanel !== 'undefined' && ServoPanel.setAngles) {
        ServoPanel.setAngles(this.smoothedAngles);
      }
    }
  }
};

// Global event delegation for 100% reliable click interception
document.addEventListener('click', (e) => {
  const btn = e.target.closest('#btnToggleTeleopMode');
  if (btn) {
    e.preventDefault();
    e.stopPropagation();
    TeleopPanel.toggleMode();
  }
});

window.toggleTeleopMode = function() {
  TeleopPanel.toggleMode();
};

document.addEventListener('DOMContentLoaded', () => {
  TeleopPanel.init();
});
