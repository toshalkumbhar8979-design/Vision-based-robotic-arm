"""
==============================================================================
ROBOTIC DATASET EXPORTER TO HDF5 (.h5) & NUMPY (.npz)
==============================================================================

Project:  Vision-Based Autonomous Robotic Arm
File:     export_dataset.py
Location: dashboard/backend/

PURPOSE:
    Converts recorded JSON demonstration episodes into compact binary NumPy (.npz)
    and HDF5 (.h5) formats required for Behavior Cloning (ACT / Diffusion Policy)
    neural network training.
==============================================================================
"""

import os
import glob
import json
import numpy as np

DATASETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "datasets"))
DATASET_JSON = os.path.abspath(os.path.join(os.path.dirname(__file__), "dataset_episodes.json"))
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../dataset_export"))

def load_all_demonstrations():
    """Loads all episodes from datasets/ directory, falling back to dataset_episodes.json."""
    episodes = []
    if os.path.exists(DATASETS_DIR):
        files = sorted(glob.glob(os.path.join(DATASETS_DIR, "episode_*.json")))
        for fpath in files:
            try:
                with open(fpath, "r") as f:
                    episodes.append(json.load(f))
            except Exception as e:
                print(f"Warning: Failed to load {fpath}: {e}")
                
    if not episodes and os.path.exists(DATASET_JSON):
        try:
            with open(DATASET_JSON, "r") as f:
                episodes = json.load(f)
        except Exception:
            pass
            
    return episodes

def export_dataset():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    episodes = load_all_demonstrations()
    
    if not episodes:
        print(f"No demonstration episodes found in {DATASETS_DIR} or {DATASET_JSON}.")
        return

    print(f"Loaded {len(episodes)} demonstration episodes.")

    all_obs = []
    all_actions = []
    all_episode_lengths = []

    for ep in episodes:
        ep_num = ep.get("number", 1)
        frames = ep.get("trajectory", [])
        if len(frames) < 2:
            continue
        
        # Block pose for this demonstration
        init_pose = ep.get("initial_block_pose") or {"x_cm": 0.0, "y_cm": 0.0, "theta_deg": 0.0}
        bx = float(init_pose.get("x_cm", 0.0))
        by = float(init_pose.get("y_cm", 0.0))
        bth = float(init_pose.get("theta_deg", 0.0))
        
        ep_obs = []
        ep_acts = []
        
        for k in range(len(frames) - 1):
            curr_f = frames[k]
            next_f = frames[k + 1]
            
            # Current joint state + gripper + target block pose: [θ1..θ5, g, X, Y, θ] (9 dims)
            curr_joints = curr_f.get("joints", curr_f.get("angles", [90,90,90,90,90])[:5])
            curr_grip = float(curr_f.get("gripper_state", 0))
            obs_vector = list(curr_joints) + [curr_grip, bx, by, bth]
            
            # Next target action: [θ1'..θ5', g'] (6 dims)
            next_joints = next_f.get("joints", next_f.get("angles", [90,90,90,90,90])[:5])
            next_grip = float(next_f.get("gripper_state", 0))
            act_vector = list(next_joints) + [next_grip]
            
            ep_obs.append(obs_vector)
            ep_acts.append(act_vector)
            
        ep_obs = np.array(ep_obs, dtype=np.float32)
        ep_acts = np.array(ep_acts, dtype=np.float32)
        
        all_obs.append(ep_obs)
        all_actions.append(ep_acts)
        all_episode_lengths.append(len(ep_obs))
        
        # Save individual compressed episode
        ep_file = os.path.join(OUTPUT_DIR, f"episode_{ep_num:03d}.npz")
        np.savez_compressed(ep_file, observations=ep_obs, actions=ep_acts)
        print(f"Exported Episode #{ep_num:03d} -> {ep_file} ({len(ep_obs)} transitions)")

    # Concatenate all transitions for batch PyTorch training
    full_obs = np.concatenate(all_obs, axis=0)
    full_acts = np.concatenate(all_actions, axis=0)
    
    master_file = os.path.join(OUTPUT_DIR, "master_dataset_all_episodes.npz")
    np.savez_compressed(
        master_file,
        observations=full_obs,
        actions=full_acts,
        episode_lengths=np.array(all_episode_lengths, dtype=np.int32),
        num_episodes=len(all_obs)
    )
    print(f"\nSuccessfully generated master PyTorch training dataset: {master_file}")
    print(f"Total transitions: {len(full_obs)} | Obs shape: {full_obs.shape} | Act shape: {full_acts.shape}")

if __name__ == "__main__":
    export_dataset()

