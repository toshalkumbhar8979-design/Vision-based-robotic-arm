#!/usr/bin/env python3
"""
==============================================================================
BEHAVIOUR CLONING TRAINING — 750 EPISODES -> ONNX POLICY
==============================================================================
Project:  Vision-Based Autonomous Robotic Arm
File:     train_onnx.py
Location: Dataset_30/

PURPOSE:
  Trains the Imitation Learning (Behaviour Cloning) policy on the combined
  750-episode demonstration dataset (30 real human DJT + 720 synthetic) and
  exports an ONNX model for 30Hz inference on Raspberry Pi 5.

  Follows the repo conventions of dashboard/backend/export_dataset.py and
  train_policy.py:
    Observation (9 dims): [th1..th5, gripper_state, block_x, block_y, block_theta]
    Action     (6 dims): [th1'..th5', gripper']      (joints in DEGREES, gripper binary)

  ONNX CONTRACT (normalization baked into the graph — no external pre-processing):
    Input  'observation': float32 [N, 9]  (RAW values: degrees, gripper 0/1, cm, deg)
    Output 'action':      float32 [N, 6]  (5 joint angles in DEGREES 0-180,
                                           + gripper open probability 0-1)

HARDWARE:
  CPU training (PyTorch 2.x): ~550k transitions, MLP 9->256->256->128.
  On RTX 5050 (8GB VRAM): same script runs unmodified on CUDA — install the
  cu126/cu128 wheel (pip install torch --index-url https://download.pytorch.org/whl/cu128)
  and training accelerates ~20x; CPU (24GB RAM) is fully sufficient for this MLP.
==============================================================================
"""

import os
import json
import glob
import math
import random
import time

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

HERE = os.path.abspath(os.path.dirname(__file__))
DS_DIR = os.path.abspath(os.path.join(HERE, "datasets"))
MODELS_DIR = os.path.abspath(os.path.join(HERE, "models"))
NPZ_PATH = os.path.abspath(os.path.join(HERE, "master_dataset_all_episodes.npz"))

SEED = 42
EPOCHS = 50
BATCH = 1024
LR = 1e-3
VAL_EPISODES = 36  # ~5% of 750, held out by episode (no frame leakage)

# Normalization scale for observations (RAW -> [0,1]-ish).
# Joints 0-180, gripper binary, block x/y in cm (workspace 25x30 -> use 30),
# block theta -180..180.
OBS_SCALE = torch.tensor([180.0, 180.0, 180.0, 180.0, 180.0, 1.0, 30.0, 30.0, 180.0])


class ImitationPolicyNet(nn.Module):
    """Deep residual BC policy network (identical architecture to train_policy.py)."""
    def __init__(self, obs_dim=9, joint_dim=5):
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Linear(obs_dim, 256), nn.LayerNorm(256), nn.Mish(), nn.Dropout(0.05),
            nn.Linear(256, 256), nn.LayerNorm(256), nn.Mish(), nn.Dropout(0.05),
            nn.Linear(256, 128), nn.LayerNorm(128), nn.Mish(),
        )
        self.joint_head = nn.Linear(128, joint_dim)   # continuous 5 primary joints
        self.gripper_head = nn.Linear(128, 1)          # binary gripper state

    def forward(self, x):
        feat = self.backbone(x)
        joints = self.joint_head(feat)
        gripper_prob = torch.sigmoid(self.gripper_head(feat))
        return torch.cat([joints, gripper_prob], dim=-1)


class NormalizedPolicy(nn.Module):
    """Wraps the policy so the ONNX graph consumes RAW observations directly."""
    def __init__(self, net, obs_scale):
        super().__init__()
        self.net = net
        self.register_buffer("obs_scale", obs_scale)

    def forward(self, raw_obs):
        return self.net(raw_obs / self.obs_scale)


def load_transitions():
    """Loads all 750 episodes and builds (obs, act) transition arrays (repo convention)."""
    files = sorted(glob.glob(os.path.join(DS_DIR, "episode_*.json")))
    assert len(files) == 750, f"Expected 750 episodes, found {len(files)}"
    all_obs, all_acts, ep_bounds, ep_nums = [], [], [], []
    for f in files:
        with open(f, "r") as fh:
            ep = json.load(fh)
        pose = ep["initial_block_pose"]
        bx, by, bth = float(pose["x_cm"]), float(pose["y_cm"]), float(pose["theta_deg"])
        tr = ep["trajectory"]
        start = len(all_obs)
        for k in range(len(tr) - 1):
            cur, nxt = tr[k], tr[k + 1]
            obs = list(cur["joints"]) + [float(cur["gripper_state"]), bx, by, bth]
            act = list(nxt["joints"]) + [float(nxt["gripper_state"])]
            all_obs.append(obs)
            all_acts.append(act)
        ep_bounds.append((start, len(all_obs)))
        ep_nums.append(ep["number"])
    obs = np.asarray(all_obs, dtype=np.float32)
    acts = np.asarray(all_acts, dtype=np.float32)
    return obs, acts, ep_bounds, ep_nums


def train(obs, acts, ep_bounds):
    """Trains the BC policy with episode-level train/val split."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device} | torch {torch.__version__}")

    obs_t = torch.from_numpy(obs)
    acts_t = torch.from_numpy(acts)

    # Episode-level split (no frame leakage between train and val)
    n_eps = len(ep_bounds)
    rng = random.Random(SEED)
    val_idx = set(rng.sample(range(n_eps), VAL_EPISODES))
    tr_rows = np.concatenate([np.arange(s, e) for i, (s, e) in enumerate(ep_bounds) if i not in val_idx])
    va_rows = np.concatenate([np.arange(s, e) for i, (s, e) in enumerate(ep_bounds) if i in val_idx])
    print(f"Episodes: {n_eps - VAL_EPISODES} train / {VAL_EPISODES} val | "
          f"Transitions: {len(tr_rows)} train / {len(va_rows)} val")

    obs_scale = OBS_SCALE.to(device)
    obs_tr = (obs_t[tr_rows] / obs_scale).to(device)
    acts_tr = acts_t[tr_rows].to(device)
    obs_va = (obs_t[va_rows] / obs_scale).to(device)
    acts_va = acts_t[va_rows].to(device)

    net = ImitationPolicyNet().to(device)
    opt = optim.AdamW(net.parameters(), lr=LR, weight_decay=1e-4)
    sched = optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)
    mse_fn, bce_fn = nn.MSELoss(), nn.BCELoss()

    n = len(tr_rows)
    for epoch in range(1, EPOCHS + 1):
        net.train()
        perm = torch.randperm(n, device=device)
        t0 = time.time()
        total_loss = 0.0
        for b in range(0, n, BATCH):
            idx = perm[b:b + BATCH]
            ob, ac = obs_tr[idx], acts_tr[idx]
            opt.zero_grad()
            pred = net(ob)
            loss = mse_fn(pred[:, :5], ac[:, :5]) + 5.0 * bce_fn(pred[:, 5], ac[:, 5])
            loss.backward()
            opt.step()
            total_loss += loss.item() * len(idx)
        sched.step()

        if epoch == 1 or epoch % 5 == 0:
            net.eval()
            with torch.no_grad():
                pv = net(obs_va)
                joint_mae = (pv[:, :5] - acts_va[:, :5]).abs().mean().item()
                grip_pred = (pv[:, 5] > 0.5).float()
                grip_acc = (grip_pred == acts_va[:, 5]).float().mean().item()
            print(f"Epoch {epoch:03d}/{EPOCHS} | loss {total_loss / n:.5f} | "
                  f"val joint MAE {joint_mae:.2f} deg | grip acc {grip_acc * 100:.1f}% "
                  f"| {time.time() - t0:.1f}s/ep", flush=True)
    return net, device


def export_onnx(net, device, obs, acts, ep_bounds):
    """Exports the raw-input ONNX policy and verifies it with onnxruntime."""
    os.makedirs(MODELS_DIR, exist_ok=True)
    pth_path = os.path.join(MODELS_DIR, "imitation_policy_750ep.pth")
    torch.save(net.state_dict(), pth_path)
    print(f"\nSaved PyTorch weights: {pth_path}")

    wrapper = NormalizedPolicy(net, OBS_SCALE.to(device)).to(device).eval()
    onnx_path = os.path.join(MODELS_DIR, "imitation_policy_750ep.onnx")
    dummy = torch.randn(1, 9, device=device) * 90.0
    torch.onnx.export(
        wrapper, dummy, onnx_path,
        input_names=["observation"], output_names=["action"],
        dynamic_axes={"observation": {0: "batch"}, "action": {0: "batch"}},
        opset_version=14, dynamo=False,  # legacy exporter (no onnxscript dependency)
    )
    print(f"Exported ONNX model: {onnx_path}")

    # Verification: ONNX runtime output must match PyTorch on real dataset frames
    import onnxruntime as ort
    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(SEED)
    sample = rng.choice(len(obs), size=2048, replace=False)
    torch_out = wrapper(torch.from_numpy(obs[sample]).to(device)).detach().cpu().numpy()
    ort_out = sess.run(["action"], {"observation": obs[sample]})[0]
    err = np.abs(torch_out - ort_out).max()
    print(f"ONNX verification vs PyTorch: max abs diff {err:.6f} "
          f"({'PASS' if err < 1e-3 else 'FAIL'})")
    print(f"Sample inference: obs {np.round(obs[sample[0]], 2).tolist()} -> "
          f"action {np.round(ort_out[0], 2).tolist()}")


def main():
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    random.seed(SEED)
    torch.set_num_threads(max(1, (os.cpu_count() or 4) - 2))

    obs, acts, ep_bounds, ep_nums = load_transitions()
    print(f"Loaded 750 episodes -> {len(obs)} transitions "
          f"(obs {obs.shape}, act {acts.shape})")
    np.savez_compressed(NPZ_PATH, observations=obs, actions=acts,
                        episode_numbers=np.array(ep_nums))
    print(f"Master dataset saved: {NPZ_PATH}")

    net, device = train(obs, acts, ep_bounds)
    export_onnx(net, device, obs, acts, ep_bounds)


if __name__ == "__main__":
    main()
