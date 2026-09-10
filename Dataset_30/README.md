# Dataset_30 — 750-Episode Demonstration Dataset & ONNX Policy

## Contents
| Path | Purpose |
|---|---|
| `datasets/episode_001..750.json` | Demonstrations: 30 real human DJT + 720 synthetic (same JSON style) |
| `episodes_index.json` | Quick manifest of the 720 synthetic episodes (numbers 31-750) |
| `master_dataset_all_episodes.npz` | All 549,424 transitions as arrays (obs 9-dim / act 6-dim) |
| `models/imitation_policy_750ep.pth` | Trained PyTorch BC policy weights |
| `models/imitation_policy_750ep.onnx` | ONNX policy for 30Hz RPi5 inference (raw obs in / raw action out) |
| `generate_dataset.py` | Synthetic episode generator (seeded, idempotent style, re-runnable) |
| `validate_dataset.py` | Full 750-episode validator (style, overlap, rates, ranges) |
| `train_onnx.py` | End-to-end: load -> npz -> train -> .pth -> .onnx -> verify |
| `export_only.py` | Re-export/verify ONNX from saved weights without retraining |
| `train_log.txt` | Training record of the 750-episode run |

## Dataset
- Numbers 1-30: real human DJT demonstrations (untouched, ids `ep-17889294...`..`ep-17889316...`).
- Numbers 31-750: synthetic, ids strictly increasing above the real max, files `episode_031..750.json`.
- Coverage: 24 pick cells (x in {2.5..27.5}, y in {6,11,16,21}) x 30 demos; block poses >= 0.6cm from every real pose; theta clusters near 0/+90/-90/+180 like the real data.
- Contract (matches `dashboard/backend/export_dataset.py`): obs `[th1..th5, gripper_state, block_x, block_y, block_theta]` -> action `[th1'..th5', gripper']`.

## Training results (50 epochs, CPU)
- Final val joint MAE **0.19 deg**, gripper accuracy **99.7%** (36 held-out episodes).
- ONNX verified vs PyTorch: max abs diff 0.000137 (PASS).

## ONNX contract (normalization baked into the graph)
- Input `observation`: float32 [N, 9] RAW `[th1..th5 (deg), gripper_state (0/1), block_x (cm), block_y (cm), block_theta (deg)]`
- Output `action`: float32 [N, 6] — 5 joint angles in DEGREES (clamp 0-180 in firmware) + gripper open probability (threshold 0.5).

## Hardware note (RTX 5050 8GB VRAM)
CPU training (24GB RAM) is fully sufficient for this MLP (~8 min for 50 epochs).
For ~20x speedup install the CUDA wheel: `pip install torch --index-url https://download.pytorch.org/whl/cu128`
— the script auto-detects CUDA with no code changes. 8GB VRAM is far more than needed.
