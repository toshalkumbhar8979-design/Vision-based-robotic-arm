# Control Dashboard — Vision-Based Autonomous Robotic Arm

> **Theme:** Warm Light Mode (Cream/Linen/Sand)
> **Typography:** DM Serif Display, Source Sans 3, IBM Plex Mono
> **Status:** Phase A Complete (Skeleton + Servo Control Panel + Assembly Helper)

## Overview

The Control Dashboard is a unified, web-based control interface designed for the entire lifecycle of the 6-DOF Vision-Based Autonomous Robotic Arm. It runs seamlessly on both **MacBook** (development/training) and **Raspberry Pi 5** (deployment).

## Architecture

- **Backend:** Python (FastAPI + WebSockets + `pyserial`)
- **Frontend:** Vanilla HTML5 + CSS3 + JavaScript (Zero Node.js build dependencies)
- **Serial Protocol:** Binary 6-byte packet streaming at 115200 Baud (Decision #6)
- **Port Management:** `arduino-cli` / port scan auto-detection (Decision #15)

## Directory Structure

```
dashboard/
├── backend/
│   ├── main.py              ← FastAPI server & WebSocket endpoint
│   ├── serial_manager.py    ← Arduino serial connection manager
│   └── requirements.txt     ← Python dependencies (fastapi, uvicorn, pyserial)
├── frontend/
│   ├── index.html           ← Main Warm Cream UI shell
│   ├── css/
│   │   └── styles.css       ← Design system (warm light cream palette)
│   └── js/
│       ├── app.js           ← Core application & WebSocket manager
│       └── servo_panel.js   ← Servo sliders, Lock 90°, Home, E-stop logic
└── README.md
```

## How to Run Dashboard Phase A

1. Navigate to the backend directory:
   ```bash
   cd "dashboard/backend"
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Start the FastAPI server:
   ```bash
   python3 main.py
   ```

4. Open your browser to `http://localhost:8050` (or access from your tablet on the same WiFi using `http://<your-mac-ip>:8050`).

## Features (Phase A)

- **ONNX Autonomous Policy (panel: "ONNX Model"):**
  - Loads trained Behaviour Cloning policies from `Dataset_30/models/*.onnx` (backend `autonomous_manager.py`).
  - **Start Autonomous Pick & Place** runs a 30Hz closed loop: Camera 1 ArUco block pose + current joints → ONNX inference → EMA-smoothed joint commands → Arduino. If the block is not visible the arm HOLDS (frozen) instead of guessing.
  - **Stop** (or any E-stop, software or physical) instantly halts the policy and returns manual control.
  - While running, manual commands (sliders, PS5 teleop, IK move, solo tests) are ignored/blocked so the policy owns the arm; when stopped the dashboard behaves exactly as before.
  - Live telemetry: inference Hz, frames, runtime, gripper open probability, block pose, commanded vs. predicted joints.

- **Physical Assembly Assistant (Decision #19):**
  - **Lock All at 90° Button:** Single click to lock all 6 servos at center position while mounting plastic arm parts onto servo gear shafts.
  - **6 Live Interactive Sliders:** Drag sliders to test physical joint ranges and verify no plastic collisions occur.
- **Safety Controls (Decision #5):**
  - **Emergency Stop Button:** Instant software E-stop that cuts commands and forces Home position.
  - **Home Position Button:** Resets all joints to default upright position.
- **Serial Port Management (Decision #15):**
  - Auto-detects connected Arduino Uno USB ports.
  - Live status indicator (Offline / Connected / E-Stop).
  - Activity log box.
