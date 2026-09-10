# Decision Log — Vision-Based Autonomous Robotic Arm

> **Purpose:** Append-only chronological log of every engineering decision.
> **Rule:** NEVER delete or modify past entries. Only append new ones.
> **Referenced by:** `agent_bible.md` (summary table) and `.gemini/rules.md`

---

## Decision #1 — Perception Architecture
- **Date:** 2026-07-06
- **Decision:** Use Hybrid Perception (OpenCV features → Neural Network) instead of End-to-End (raw pixels → Neural Network).
- **Alternatives Rejected:** End-to-end image-to-action (requires massive datasets, heavy compute, harder to debug).
- **Rationale:** Smaller datasets, faster training, lower compute (must run on RPi5 4GB), modular debugging. OpenCV handles perception; NN focuses only on motion policy.

---

## Decision #2 — Stage 1 Detection Method
- **Date:** 2026-07-06
- **Decision:** Use ArUco markers on sponge blocks (with rigid cardboard backing) for Stage 1.
- **Alternatives Rejected:** Raw color/contour detection (fragile under variable lighting and robot shadows).
- **Rationale:** Guarantees 100% robust pose estimation regardless of lighting. If the imitation learning policy fails during Stage 1, we KNOW it's the policy's fault, not noisy perception. Isolates subsystems for debugging.

---

## Decision #3 — Coordinate System
- **Date:** 2026-07-06
- **Decision:** Use calibrated real-world coordinates (centimeters from robot base) for neural network input.
- **Alternatives Rejected:** Raw pixel coordinates (ties policy to exact camera resolution and position).
- **Rationale:** Better policy generalization. Decouples the learned policy from camera-specific parameters. Requires one-time homography calibration.

---

## Decision #4 — Teleoperation Control Mode
- **Date:** 2026-07-06
- **Decision:** Use Cartesian Inverse Kinematics (PS5 joystick controls end-effector X,Y,Z; Python computes joint angles).
- **Alternatives Rejected:** Direct Joint Control (human controls each joint individually).
- **Rationale:** Humans produce much smoother, more natural demonstrations when controlling in Cartesian space. Direct joint control of 6 joints is extremely difficult for humans, resulting in jerky demonstrations that the AI would learn to replicate.

---

## Decision #5 — Safety System
- **Date:** 2026-07-06
- **Decision:** Physical emergency stop switch (cuts 6V servo power) + 500ms software watchdog on Arduino (auto-returns to home if serial communication drops).
- **Alternatives Rejected:** Software-only safety (unreliable if Python crashes).
- **Rationale:** Untrained ML policies WILL command erratic movements. Physical E-stop prevents gear stripping and frame damage. Software watchdog handles graceful disconnection.

---

## Decision #6 — Serial Protocol
- **Date:** 2026-07-06
- **Decision:** Binary 6-byte packets at 115200 baud, 30 Hz target.
- **Alternatives Rejected:** ASCII text commands (higher latency, more parsing overhead).
- **Rationale:** Minimal transmission overhead. One byte per servo (0–180). Fast parsing on Arduino. Reduces teleoperation latency for smoother demonstrations.

---

## Decision #7 — Block Material
- **Date:** 2026-07-06
- **Decision:** Use sponge cubes as manipulation objects.
- **Alternatives Rejected:** Wooden blocks, plastic blocks (too heavy for MG90S gripper servo).
- **Rationale:** Ultra-lightweight prevents gripper stall. Compressible so gripper doesn't need to be precisely calibrated. ArUco marker mounted on rigid cardboard backing glued to sponge top.

---

## Decision #8 — Stage 1 Environment
- **Date:** 2026-07-06
- **Decision:** Box is FIXED, block is randomly placed.
- **Alternatives Rejected:** Both objects random (adds unnecessary complexity for a validation stage).
- **Rationale:** Stage 1 exists purely to validate the pipeline. Fixing the box simplifies the learning problem and isolates the "pick from random position" skill. Stage 2 introduces full randomness.

---

## Decision #9 — Robot Arm Type
- **Date:** 2026-07-06
- **Decision:** This is a true 6-DOF serial manipulator (NOT an EEZYbotARM MK2).
- **Alternatives Rejected:** N/A — this was a factual correction by the user.
- **Rationale:** The arm has independent Wrist Pitch and Wrist Roll servos, giving it true 6-DOF. MK2 uses a parallel linkage that locks the wrist angle, making it effectively 3-DOF for positioning. This distinction matters for the IK solver.

---

## Decision #10 — Home Position Assembly Strategy
- **Date:** 2026-07-06
- **Decision:** Mount arm parts to maximize physical workspace range. Use joint offsets in software to handle the mathematical mapping.
- **Alternatives Rejected:** Mounting all joints straight-up at 90° for mathematical convenience (wastes half the range of motion).
- **Rationale:** The user correctly identified that mounting the elbow horizontally wastes downward reach. Strategy: find the mechanical collision limits, mount at the midpoint, then compensate in Python with offset constants.

---

## Decision #11 — Dashboard Type
- **Date:** 2026-07-23
- **Decision:** Web-based dashboard (HTML/CSS/JS frontend + Python FastAPI/WebSocket backend).
- **Alternatives Rejected:** Python desktop app (PyQt/Tkinter) — less portable, harder to make look premium.
- **Rationale:** Works identically on MacBook and Raspberry Pi 5. Accessible from any device on the same WiFi. Better aesthetics for capstone demo. Zero framework build step (vanilla JS).

---

## Decision #12 — Camera 2 Role
- **Date:** 2026-07-06
- **Decision:** Side camera (Camera 2) is for dataset logging only. It is NOT used by the neural network.
- **Alternatives Rejected:** Using both cameras for perception (unnecessary complexity for a 2D table workspace).
- **Rationale:** The top camera provides all the (X, Y, θ) information needed for the flat workspace. The side camera records video for future research (potential end-to-end policies, ACT-style models).

---

## Decision #13 — Deployment Target
- **Date:** 2026-07-06
- **Decision:** Final autonomous system runs on Raspberry Pi 5 (4GB RAM).
- **Alternatives Rejected:** Keeping it on the MacBook (not a standalone system).
- **Rationale:** The capstone goal is a standalone robot. RPi5 4GB is sufficient for OpenCV + a lightweight PyTorch model inference.

---

## Decision #14 — Arduino Port Management
- **Date:** 2026-07-23
- **Decision:** Use Arduino CLI (`arduino-cli`) for port detection and firmware management throughout development. Switch to direct `pyserial` on Raspberry Pi 5.
- **Alternatives Rejected:** Manual port selection, raw pyserial port scanning.
- **Rationale:** Arduino CLI provides reliable board detection, port listing, and firmware flashing. Can be integrated into the dashboard for one-click firmware uploads.

---

## Decision #15 — Dashboard Authentication
- **Date:** 2026-07-23
- **Decision:** No authentication on the dashboard.
- **Alternatives Rejected:** Login page (unnecessary overhead).
- **Rationale:** Dashboard runs on local network only. No external access.

---

## Decision #16 — Dashboard Responsiveness
- **Date:** 2026-07-23
- **Decision:** Support laptop and tablet (minimum 768px width). Phone is NOT supported.
- **Alternatives Rejected:** Full mobile responsive (unnecessary; nobody operates a robotic arm from a phone).
- **Rationale:** Tablet support is useful for monitoring while standing near the robot. Phone screens are too small for meaningful interaction.

---

## Decision #26 — World Frame Corner Origin (Marker 2 at 0,0)
- **Date:** 2026-07-24
- **Decision:** Define the platform corner (where ArUco Marker 2 will be placed) as the World Origin $(X_w=0, Y_w=0)$. The entire $50\text{cm} \times 50\text{cm}$ board operates strictly in positive coordinates ($X_w \in [0, 50]$, $Y_w \in [0, 50]$). The exact physical offset of the Robot Base $(X_{\text{base}}, Y_{\text{base}})$ will be measured and registered in software once physical mounting is completed.
- **Alternatives Rejected:** Defining the centered Robot Base as $(0, 0)$ which created negative $X$ values for the left side of the platform.
- **Rationale:** Standard dual-frame robotics transformation: Vision detects all objects in positive World Coordinates $(X_w, Y_w)$, and Python converts to Robot Base coordinates ($X_r = X_w - X_{\text{base}}$, $Y_r = Y_w - Y_{\text{base}}$) before passing to the Inverse Kinematics solver.

---

## Decision #24 — Prime Engineering Directive: 100% Smooth Motion Policy
- **Date:** 2026-08-06
- **Status:** LOCKED (THE MOST IMPORTANT RULE OF THE PROJECT)
- **Decision:** Every single movement of the 6-DOF robotic arm — across PS5 teleoperation joysticks, web control sliders, automated routines (Home, Lock 90°, Solo Sweep), IK Cartesian mode, and autonomous inference — MUST ALWAYS pass through Exponential Moving Average (EMA) low-pass filtering ($\alpha = 0.18$) and Cosine S-curve trajectory interpolation. Zero sudden movements, zero snaps, zero jerks, and zero current spikes are permitted under any condition.
- **Rationale:** Protects MG996R and MG90S high-torque metal gears from backlash wear, prevents power supply brownouts, guarantees safety, and produces ultra-smooth, organic teleoperation demonstrations for imitation learning dataset collection.

