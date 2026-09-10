# Architecture Document — Vision-Based Autonomous Robotic Arm

> **Last Updated:** 2026-07-23
> This document is the single source of truth for the system architecture.

---

## 1. Project Goal

Build a vision-guided autonomous 6-DOF robotic arm that learns pick-and-place tasks from human demonstrations using Imitation Learning (Behaviour Cloning). The system uses a hybrid perception architecture: OpenCV extracts scene features, and a neural network learns only the robot motion policy.

---

## 2. Hardware Architecture

### 2.1 Robotic Arm
| Component | Specification |
|---|---|
| Degrees of Freedom | 6 (including gripper) |
| Frame | 3D printed (Amazon kit) |
| Base Servo | MG996R (PCA9685 Channel 0) |
| Shoulder Servo | MG996R (PCA9685 Channel 1) |
| Elbow Servo | MG996R (PCA9685 Channel 2) |
| Wrist Pitch Servo | MG90S (PCA9685 Channel 3) |
| Wrist Roll Servo | MG90S (PCA9685 Channel 4) |
| Gripper Servo | MG90S (PCA9685 Channel 5) |

### 2.2 Electronics
| Component | Role |
|---|---|
| Arduino Uno Rev3 | Low-level serial-to-I2C bridge (receives joint angles, commands PCA9685) |
| PCA9685 16-Channel PWM Driver | Generates precise PWM signals for all 6 servos via I2C |
| 6V 5Ah Sealed Lead Acid Battery | Powers servos only |
| Physical Emergency Stop Switch | Cuts 6V servo power supply instantly |

### 2.3 Compute
| Phase | Computer | Role |
|---|---|---|
| Development & Training | MacBook | Teleoperation host, dataset collection, model training |
| Deployment | Raspberry Pi 5 (4GB) | Autonomous execution host (runs OpenCV + trained model) |

### 2.4 Vision System
| Camera | Model | Mount | Purpose |
|---|---|---|---|
| Camera 1 (Top) | Logitech C270 | Vertical pole, looking straight down | Primary perception (OpenCV feature extraction) |
| Camera 2 (Side) | Logitech C270 | Side of workspace | Secondary (dataset logging, future research) |

### 2.5 Workspace
- **Size:** ~40 cm × 40 cm wooden plank
- **Robot:** Mounted at one edge
- **Objects:** Lightweight sponge blocks with ArUco markers (Stage 1) / colored sponges (Stage 2)
- **Lighting:** Variable (not controlled)

---

## 3. Communication Architecture

```
PS5 Controller ──USB/BT──► MacBook (Python)
                              │
                              ├── IK Solver ──► Joint Angles
                              │
                              ├── Serial (115200 baud, 6-byte binary) ──► Arduino Uno
                              │                                              │
                              │                                         I2C (Wire.h)
                              │                                              │
                              │                                         PCA9685 ──PWM──► 6 Servos
                              │
                              ├── Camera 1 (USB) ──► OpenCV Pipeline
                              └── Camera 2 (USB) ──► Dataset Recorder
```

### Serial Protocol
- **Baud Rate:** 115200
- **Packet Format:** 6 raw bytes (one per servo, value 0–180)
- **Frequency:** 30 Hz target
- **Safety:** 500ms watchdog timeout → auto return to Home

---

## 4. Software Architecture

### 4.1 Arduino Firmware (`firmware/`)
| File | Purpose | Status |
|---|---|---|
| `servo_calibration/servo_calibration.ino` | Sets all servos to 90° for physical assembly | ✅ Written |
| `robot_driver/robot_driver.ino` | Production firmware: serial listener + PCA9685 driver + watchdog | ✅ Written |

### 4.2 Python Backend (MacBook / Raspberry Pi)
| Module | Purpose | Status |
|---|---|---|
| `teleoperation/` | PS5 controller input + IK solver + serial sender | ❌ Not started |
| `perception/` | OpenCV pipeline (ArUco / color detection + world coordinate mapping) | ❌ Not started |
| `data/` | Synchronized dataset recording & management | ❌ Not started |
| `models/` | Imitation learning model training & inference | ❌ Not started |
| `digital_twin/` | Simulation environment | ❌ Not started |
| `dashboard/` | Web-based control dashboard | ❌ Not started (planning phase) |

### 4.3 Dashboard (`dashboard/`)
- **Type:** Web-based (HTML/CSS/JS frontend + Python WebSocket backend)
- **Purpose:** Single unified interface for calibration, teleoperation, perception tuning, dataset management, training monitoring, and autonomous execution
- **Runs on:** MacBook (development) and Raspberry Pi 5 (deployment)

---

## 5. Perception Pipeline

### Stage 1 (System Validation)
- **Method:** ArUco marker detection (lighting-invariant)
- **Objects:** 1 block (random position), 1 box (fixed position)
- **Extracted Features:** Block (X, Y, θ), Box (X, Y, θ) — all in calibrated real-world coordinates (cm from robot base)

### Stage 2 (Multi-Object Sorting)
- **Method:** Color & contour detection (HSV thresholding)
- **Objects:** 2 colored blocks (random), 2 colored boxes (random)
- **Extracted Features:** Per object: (X, Y, θ, Color)

### Coordinate System
- **Raw:** Pixel coordinates from camera (640×480)
- **Calibrated:** Real-world centimeters relative to robot base origin
- **Calibration Method:** One-time homography using known reference points on the workspace

---

## 6. Learning Architecture

### Method: Imitation Learning (Behaviour Cloning)
- **Input:** OpenCV feature vector (object poses in world coordinates)
- **Output:** Full joint trajectory sequence (each step = 6 angles)
- **Framework:** PyTorch
- **Training Hardware:** MacBook
- **Inference Hardware:** Raspberry Pi 5

### Demonstration Collection
- **Controller:** PS5 DualSense
- **Control Mode:** Cartesian IK (operator moves end-effector in X,Y,Z; Python computes joint angles)
- **Episode Structure:** Home → Pick → Place → Home
- **Stage 1 Target:** 150–250 demonstrations
- **Stage 2 Target:** 250–500 demonstrations

---

## 7. Key Engineering Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Perception approach | Hybrid (OpenCV features → NN) | Smaller datasets, faster training, easier debugging vs end-to-end |
| Stage 1 detection | ArUco markers | Guarantees robust perception under variable lighting; isolates ML pipeline bugs |
| Coordinate system | Calibrated real-world (cm) | Better policy generalization vs raw pixel coordinates |
| Teleoperation mode | Cartesian IK control | Smoother demonstrations for humans vs direct joint control |
| Serial protocol | Binary 6-byte packets | Lower latency than ASCII; minimal parsing overhead |
| Dashboard | Web-based | Works on both MacBook and RPi5; better aesthetics for capstone demo |
| Block material | Sponge | Ultra-lightweight; prevents MG90S gripper servo stall |
| ArUco mounting | Cardboard backing glued to sponge top | Keeps marker flat and rigid for reliable detection |

---

## 8. Project Phases

1. **Hardware Integration** — Assemble arm, test servos, calibrate home position ← CURRENT
2. **Dashboard Development** — Build web-based control interface ← NEXT
3. **PS5 Teleoperation + IK** — Controller input, kinematic solver, serial comms
4. **Camera Integration** — Dual camera feeds, ArUco detection, calibration
5. **OpenCV Perception Module** — Feature extraction pipeline
6. **Dataset Recording Framework** — Synchronized episode capture
7. **Imitation Learning Model** — Architecture, training, evaluation
8. **Autonomous Execution** — Closed-loop inference on RPi5
9. **Digital Twin** — Simulation environment
10. **Deployment & Optimization** — RPi5 performance tuning
