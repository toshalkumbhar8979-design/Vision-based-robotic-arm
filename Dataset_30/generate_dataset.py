#!/usr/bin/env python3
"""
==============================================================================
SYNTHETIC DEMONSTRATION DATASET GENERATOR — EPISODES 31–750 (720 NEW)
==============================================================================
Project:  Vision-Based Autonomous Robotic Arm
File:     generate_dataset.py
Location: Dataset_30/

PURPOSE:
  Extends the 30 real human DJT (Direct Joint Teleoperation) demonstrations
  (episode_001.json .. episode_030.json, numbers 1–30) with 720 additional
  synthetic pick-and-place demonstrations in the EXACT same JSON style, so the
  combined 750-episode dataset can later be exported (.npz) and used to train
  the Behaviour Cloning ONNX policy (train_policy.py -> imitation_policy.onnx).

  720 = 24 pick cells (6 cols x 4 rows of the 5cm grid on the 25cm x 30cm
  workspace) x 30 demonstrations per cell.

STYLE CONTRACT (reverse-engineered from the 30 real DJT episodes):
  - 5 primary joints [th1..th5]; th4 (wrist pitch) locked at 90.
  - Frame phases: idle hold -> sequential reach -> grasp (g=1) -> lift ->
    transfer to place pose (th1~155-165, th2~78-108, th3~154-180) -> settle ->
    release (g=0) -> return home [90,90,90,90,90].
  - Rates: max per-frame joint delta <= 6 deg (30Hz, human DJT speed).
  - t values: start ~33, increment ~33ms (31-39 jitter).
  - Block poses: cell centers (2.5,7.5,12.5,17.5,22.5,27.5) x (6,11,16,21)
    with +/-1.2cm human placement jitter; guaranteed >=0.6cm from all 30 real
    episode poses (no overlap).
  - theta_deg: clusters near 0/+90/-90/+180 with jitter (matches real).
  - Joint fits from real data:
      th1_pick ~ (35 + 2.3*(20.5-y)) + (1.67 + 0.135*(y-6))*x
      th2_pick ~ 5 + 3.69*y
      th3_pick ~ 69 + 5.1*y
NON-OVERLAP GUARANTEE:
  - Numbers 31..750, files episode_031.json..episode_750.json (real: 1-30)
  - id timestamps strictly > max real id (ep-1788931605058), strictly increasing
  - Never modifies or rewrites episode_001..030
==============================================================================
"""

import json
import os
import math
import random
import glob

random.seed(20260910)  # Deterministic regeneration

HERE = os.path.abspath(os.path.dirname(__file__))
DS_DIR = os.path.abspath(os.path.join(HERE, "datasets"))
INDEX_PATH = os.path.abspath(os.path.join(HERE, "episodes_index.json"))

MAX_REAL_ID_MS = 1788931605058  # highest id among real 30
HOME = [90, 90, 90, 90, 90]
START_DATE = "Thu, Sep 10, 2026 09:00"

# 24 pick cells: 6 columns x 4 rows (5cm grid cells on 25cm x 30cm workspace)
PICK_CELLS = [(cx, cy) for cy in (6, 11, 16, 21) for cx in (2.5, 7.5, 12.5, 17.5, 22.5, 27.5)]
DEMOS_PER_CELL = 30  # 24 x 30 = 720


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def gclamp(mu, sig, lo, hi):
    """Gaussian sample clamped to [lo, hi]."""
    return clamp(random.gauss(mu, sig), lo, hi)


def fmt_num(v):
    """Matches real style: ints without .0, floats with 1 decimal."""
    iv = int(round(v))
    return str(iv) if abs(v - iv) < 1e-9 else str(round(v, 1))


def load_real_poses():
    """Loads the (x_cm, y_cm) of all 30 real episodes to guarantee no overlap."""
    poses = []
    for f in sorted(glob.glob(os.path.join(DS_DIR, "episode_*.json"))):
        n = int(os.path.basename(f)[8:11])
        if n > 30:
            break
        with open(f, "r") as fh:
            p = json.load(fh)["initial_block_pose"]
        poses.append((p["x_cm"], p["y_cm"]))
    return poses


def sample_pick_pose(cell):
    """Cell center + human placement jitter, re-rolled until >=0.6cm from real poses."""
    cx, cy = cell
    while True:
        x = round(cx + gclamp(0, 1.0, -1.2, 1.2), 1)
        y = round(cy + gclamp(0, 0.8, -1.0, 1.0), 1)
        if all(math.hypot(x - rx, y - ry) >= 0.6 for rx, ry in REAL_POSES):
            return x, y


def sample_block_theta():
    """Block orientation: clusters near 0/+90/-90/+180 with jitter (real pattern)."""
    base = random.choice([0, 90, -90, 180, -180])
    return round(base + gclamp(0, 3, -4.5, 4.5), 1)


def sample_pick_joints(x, y):
    """Pick-moment primary joints from the human-DJT fits (+/- human variance)."""
    th1 = gclamp((35 + 2.3 * (20.5 - y)) + (1.67 + 0.135 * (y - 6)) * x, 3.0, 20, 165)
    th2 = gclamp(5 + 3.69 * y, 3.5, 15, 90)
    th3 = gclamp(69 + 5.1 * y, 4.5, 85, 180)
    th5 = 90 if random.random() < 0.55 else gclamp(72, 10, 55, 88)  # th4 always 90
    return [int(round(th1)), int(round(th2)), int(round(th3)), 90, int(round(th5))]


def sample_place_joints():
    """Place-moment joints at the fixed target box (real range: 155-165/78-108/154-180)."""
    th1 = int(gclamp(160, 4, 155, 165))
    th2 = int(gclamp(93, 8, 78, 108))
    th3 = int(gclamp(168, 7, 154, 180))
    th5 = 90 if random.random() < 0.7 else int(gclamp(72, 10, 55, 90))
    return [th1, th2, th3, 90, th5]


def eased_move(a, b, n):
    """Cosine-eased integer-quantized move a->b over n frames (zero-velocity endpoints)."""
    out = []
    for i in range(1, n + 1):
        s = 0.5 * (1.0 - math.cos(math.pi * i / n))
        out.append(int(round(a + (b - a) * s)))
    return out


def build_trajectory(pick_j, place_j):
    """
    Builds one human-like DJT trajectory as [(joints, gripper_state), ...].
    Phases mirror the 30 real episodes (see module docstring).
    """
    idle_n = int(gclamp(35, 6, 25, 55))
    reach_n = int(gclamp(190, 30, 120, 280))
    settle_n = int(gclamp(7, 2, 4, 12))
    grasp_n = int(gclamp(120, 35, 60, 200))
    transfer_n = int(gclamp(160, 35, 100, 260))
    place_n = int(gclamp(55, 20, 30, 110))
    post_n = int(gclamp(30, 8, 20, 50))
    home_n = int(gclamp(110, 25, 70, 180))
    end_n = int(gclamp(30, 8, 20, 55))

    frames = []

    # Phase 1: idle hold at Home (g=0)
    frames.extend([(HOME, 0)] * idle_n)

    # Phase 2: sequential human reach with per-joint start windows (g=0)
    w1 = (random.uniform(0.0, 0.1), random.uniform(0.45, 0.6))   # base leads
    w2 = (random.uniform(0.30, 0.45), random.uniform(0.70, 0.85))
    w3 = (random.uniform(0.50, 0.65), 1.0)                        # elbow last
    w5 = (random.uniform(0.40, 0.70), 1.0)
    windows = [w1, w2, w3, (0.0, 0.0), w5]                        # th4 locked at 90
    for i in range(1, reach_n + 1):
        frac = i / reach_n
        j = []
        for k in range(5):
            a, b = windows[k]
            if k == 3 or frac >= b:
                j.append(pick_j[k])
            elif frac < a:
                j.append(HOME[k])
            else:
                s = 0.5 * (1.0 - math.cos(math.pi * (frac - a) / (b - a)))
                j.append(int(round(HOME[k] + (pick_j[k] - HOME[k]) * s)))
        frames.append((j, 0))

    # Phase 3: pre-grasp settle (g=0)
    frames.extend([(pick_j, 0)] * settle_n)

    # Phase 4: grasp hold — gripper closed, joints frozen with human micro-adjust (g=1)
    grasp_frames = [(pick_j, 1)] * grasp_n
    if random.random() < 0.5:  # real episodes show occasional 1-3 deg adjustments
        grasp_list = [list(f[0]) for f in grasp_frames]
        for _ in range(random.randint(2, 5)):
            k = random.randrange(3, grasp_n - 3)
            grasp_list[k][2] = clamp(grasp_list[k][2] + random.choice([-2, -1, 1, 2]), 0, 180)
            if random.random() < 0.4:
                grasp_list[k][1] = clamp(grasp_list[k][1] + random.choice([-1, 1]), 0, 180)
        frames.extend([(list(j), 1) for j in grasp_list])
    else:
        frames.extend([(pick_j, 1)] * grasp_n)

    # Phase 5: lift + transfer to place pose through a lift waypoint (g=1)
    lift2 = clamp(pick_j[1] + int(gclamp(9, 3, 5, 15)), 0, 180)     # shoulder rises (lift)
    lift3 = clamp(pick_j[2] + (int(gclamp(-65, 5, -75, -55)) if random.random() < 0.6
                              else int(gclamp(12, 4, 5, 20))), 0, 180)  # elbow folds / extends
    current = list(frames[-1][0])
    for i in range(1, transfer_n + 1):
        frac = i / transfer_n
        j = list(current)
        if frac < 0.35:      # lift: shoulder+elbow only
            s = 0.5 * (1.0 - math.cos(math.pi * frac / 0.35))
            j[1] = int(round(current[1] + (lift2 - current[1]) * s))
            j[2] = int(round(current[2] + (lift3 - current[2]) * s))
        else:                # main transfer: all joints ease to place pose
            s = 0.5 * (1.0 - math.cos(math.pi * (frac - 0.35) / 0.65))
            j[0] = int(round(current[0] + (place_j[0] - current[0]) * s))
            j[1] = int(round(lift2 + (place_j[1] - lift2) * s))
            j[2] = int(round(lift3 + (place_j[2] - lift3) * s))
            j[4] = int(round(current[4] + (place_j[4] - current[4]) * s))
        frames.append((j, 1))

    # Phase 6: place settle — slow shoulder descent onto box (g=1)
    drop = int(gclamp(12, 5, 5, 20))
    last_j = list(frames[-1][0])
    for v in eased_move(last_j[1], place_j[1] - drop, place_n):
        j = list(last_j)
        j[1] = v
        frames.append((j, 1))

    # Phase 7: post-release hold at place pose (g=0)
    frames.extend([(list(frames[-1][0]), 0)] * post_n)

    # Phase 8: cosine S-curve return to Home (Decision #20: zero-jerk motion)
    start = list(frames[-1][0])
    for v in zip(*[eased_move(start[k], HOME[k], home_n) for k in range(5)]):
        frames.append(([int(x) for x in v], 0))

    # Phase 9: end hold at Home (g=0)
    frames.extend([(HOME, 0)] * end_n)
    # Final sanitization pass: clamp every joint to [0,180] + enforce the <=6 deg/frame
    # rate limit by inserting midpoint frames (no velocity/teleport violations).
    sanitized = []
    prev = None
    for j, g in frames:
        j = [clamp(int(v), 0, 180) for v in j]
        if prev is not None and any(abs(j[k] - prev[k]) > 6 for k in range(5)):
            mid = [(j[k] + prev[k]) // 2 for k in range(5)]
            sanitized.append((mid, g))
        sanitized.append((j, g))
        prev = j
    return sanitized



def assign_timestamps(n_frames):
    """t values: start ~33ms, ~33ms/frame with human jitter (31-39ms)."""
    ts = []
    t = 33 + int(random.uniform(0, 2))
    for _ in range(n_frames):
        ts.append(t)
        t += int(clamp(round(random.gauss(33, 1.8)), 31, 39))
    return ts


def write_episode(number, ep_id, date_str, pose, frames, ts, path):
    """Writes one episode in the EXACT JSON style of the real 30 episodes."""
    x, y, theta = pose
    lines = ["{"]
    lines.append(f'  "id": "{ep_id}",')
    lines.append(f'  "number": {number},')
    lines.append(f'  "date": "{date_str}",')
    lines.append(f'  "frameCount": {len(frames)},')
    lines.append(f'  "durationSec": "{round(ts[-1] / 1000, 1)}",')
    lines.append(f'  "initial_block_pose": {{"x_cm": {fmt_num(x)}, "y_cm": {fmt_num(y)}, '
                 f'"theta_deg": {fmt_num(theta)}, "valid": true}},')
    lines.append('  "trajectory": [')
    traj_lines = [f'    {{"t":{ts[i]},"joints":{str(j)},"gripper_state":{g}}}'
                  for i, (j, g) in enumerate(frames)]
    lines.append(",\n".join(traj_lines))
    lines.append("  ]")
    lines.append("}")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def minute_to_date_str(offset_min):
    """'Thu, Sep 10, 2026 HH:MM' from minutes since 09:00."""
    hh = 9 + offset_min // 60
    mm = offset_min % 60
    return f"Thu, Sep 10, 2026 {hh:02d}:{mm:02d}"


REAL_POSES = load_real_poses()

def main():
    os.makedirs(DS_DIR, exist_ok=True)
    index = []
    id_ms = MAX_REAL_ID_MS
    number = 30
    for cell_idx, cell in enumerate(PICK_CELLS):
        for _ in range(DEMOS_PER_CELL):
            number += 1  # 31..750
            pose_xy = sample_pick_pose(cell)
            pose = (pose_xy[0], pose_xy[1], sample_block_theta())
            pick_j = sample_pick_joints(pose_xy[0], pose_xy[1])
            place_j = sample_place_joints()
            frames = build_trajectory(pick_j, place_j)
            ts = assign_timestamps(len(frames))

            id_ms += int(random.uniform(4000, 55000))  # strictly increasing, > max real id
            ep_id = f"ep-{id_ms}"
            date_str = minute_to_date_str(number - 31)  # 1 minute per demo from 09:00

            fname = f"episode_{number:03d}.json"
            write_episode(number, ep_id, date_str, pose, frames, ts,
                          os.path.join(DS_DIR, fname))
            index.append({
                "number": number, "file": fname, "id": ep_id, "date": date_str,
                "x_cm": pose[0], "y_cm": pose[1], "theta_deg": pose[2],
                "frameCount": len(frames), "durationSec": round(ts[-1] / 1000, 1),
            })
        print(f"[OK] Cell {cell_idx + 1}/24 done (x={cell[0]}, y={cell[1]}) "
              f"-> episodes {number - DEMOS_PER_CELL + 1}..{number}")

    with open(INDEX_PATH, "w") as fh:
        json.dump(index, fh, indent=2)
    print(f"\n[DONE] Generated {len(index)} synthetic episodes (31..{number}).")
    print(f"[DONE] Index written: {INDEX_PATH}")


if __name__ == "__main__":
    main()



