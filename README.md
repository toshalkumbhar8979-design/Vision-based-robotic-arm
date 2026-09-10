# Vision-Based Autonomous Robotic Arm

A vision-guided autonomous 6-DOF robotic arm that learns pick-and-place tasks from human demonstrations using **Imitation Learning (Behaviour Cloning)**.

## Project Structure

```
.
├── .gemini/
│   └── rules.md                 ← Agent rules (forces context loading every session)
├── firmware/
│   ├── servo_calibration/       ← Sets all servos to 90° for assembly
│   ├── robot_driver/            ← Production Arduino firmware
│   └── README.md                ← Firmware documentation
├── dashboard/                   ← Web-based control dashboard (NOT YET BUILT)
├── teleoperation/               ← PS5 controller + IK solver (NOT YET BUILT)
├── perception/                  ← OpenCV vision pipeline (NOT YET BUILT)
├── data/                        ← Dataset recording & storage (NOT YET BUILT)
├── models/                      ← Imitation learning models (NOT YET BUILT)
├── digital_twin/                ← Simulation environment (NOT YET BUILT)
├── ps5_controller_test.html              ← PS5 controller test & PoC
├── start_dashboard.sh                    ← One-click dashboard launcher
├── robotic arm synopsis.pdf               ← Submitted to collegext (updated every session)
├── architecture.md              ← System architecture document
├── agent_bible.md               ← Persistent AI context (updated every session)
├── decisions.md                 ← Append-only decision log with rationale
└── README.md                    ← This file
```

## Key Documents

| Document | Purpose |
|---|---|
| `architecture.md` | Complete system architecture (hardware, software, protocols) |
| `agent_bible.md` | AI assistant context continuity (decisions, status, history) |
| `decisions.md` | Full rationale for every engineering decision |
| `.gemini/rules.md` | Forces the AI to re-read context at every session start |

## Team

- **Soham Bhavsar** — Software, integration, deployment
- **Divyansh Dewangan** — Dataset collection, model training
- **Toshal Kumbhar** — CAD, digital twin, simulation

## Hardware

- 6-DOF 3D-printed robotic arm (3× MG996R + 3× MG90S)
- Arduino Uno Rev3 + PCA9685 PWM Driver
- 2× Logitech C270 webcams (top + side)
- PS5 DualSense controller (teleoperation)
- Raspberry Pi 5 4GB (deployment)
- 6V 5Ah sealed lead acid battery (servo power)
