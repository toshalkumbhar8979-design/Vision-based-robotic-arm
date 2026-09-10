"""
==============================================================================
IMITATION LEARNING POLICY NETWORK TRAINING (PYTORCH)
==============================================================================

Project:  Vision-Based Autonomous Robotic Arm
File:     train_policy.py
Location: dashboard/backend/

PURPOSE:
    Trains an end-to-end Behavior Cloning (BC) policy on the recorded 
    demonstrations (30 / 60 / 90 episodes).
    Maps observation vector [θ1..θ5, gripper, block_x, block_y, block_theta] (9 dims)
    to target actions [θ1'..θ5', gripper'] (6 dims).
    Exports trained model to PyTorch (.pth) and ONNX (.onnx) for real-time
    30Hz inference on Raspberry Pi 5.
==============================================================================
"""

import os
import sys
import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import Dataset, DataLoader
except ImportError:
    print("PyTorch not installed in this environment. Run: pip install torch")
    sys.exit(0)

# Path to exported dataset
DATASET_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../dataset_export/master_dataset_all_episodes.npz"))
OUTPUT_MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "models"))

class RoboticDemonstrationDataset(Dataset):
    def __init__(self, npz_path):
        data = np.load(npz_path)
        self.obs = torch.tensor(data["observations"], dtype=torch.float32)
        self.acts = torch.tensor(data["actions"], dtype=torch.float32)
        
        # Normalize observation features for faster convergence
        # Joints: 0-180 -> normalized to [0, 1]
        # Coordinates: X in [0, 25], Y in [0, 30] -> normalized to [0, 1]
        self.obs_scale = torch.tensor([180.0, 180.0, 180.0, 180.0, 180.0, 1.0, 25.0, 30.0, 180.0], dtype=torch.float32)
        self.obs_norm = self.obs / self.obs_scale

    def __len__(self):
        return len(self.obs)

    def __getitem__(self, idx):
        return self.obs_norm[idx], self.acts[idx]

class ImitationPolicyNet(nn.Module):
    """Deep residual Behavior Cloning policy network for 6-DOF robotic manipulation."""
    def __init__(self, obs_dim=9, joint_dim=5):
        super().__init__()
        
        self.backbone = nn.Sequential(
            nn.Linear(obs_dim, 256),
            nn.LayerNorm(256),
            nn.Mish(),
            nn.Dropout(0.05),
            nn.Linear(256, 256),
            nn.LayerNorm(256),
            nn.Mish(),
            nn.Dropout(0.05),
            nn.Linear(256, 128),
            nn.LayerNorm(128),
            nn.Mish(),
        )
        
        # Continuous primary 5 joint head [θ1..θ5]
        self.joint_head = nn.Linear(128, joint_dim)
        
        # Discrete binary gripper state head [0=OPEN, 1=CLOSED]
        self.gripper_head = nn.Linear(128, 1)

    def forward(self, x):
        feat = self.backbone(x)
        joints = self.joint_head(feat)
        gripper_logits = self.gripper_head(feat)
        gripper_prob = torch.sigmoid(gripper_logits)
        return torch.cat([joints, gripper_prob], dim=-1)

def train_policy(epochs=100, batch_size=32, lr=1e-3):
    os.makedirs(OUTPUT_MODEL_DIR, exist_ok=True)
    
    if not os.path.exists(DATASET_FILE):
        print(f"Dataset file {DATASET_FILE} not found. Please run export_dataset.py first.")
        return

    dataset = RoboticDemonstrationDataset(DATASET_FILE)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    
    print(f"Loaded {len(dataset)} state-action transition pairs for training.")
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ImitationPolicyNet().to(device)
    
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    
    mse_loss_fn = nn.MSELoss()
    bce_loss_fn = nn.BCELoss()
    
    print(f"Starting policy training for {epochs} epochs on {device}...")
    
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        
        for obs_b, acts_b in dataloader:
            obs_b = obs_b.to(device)
            acts_b = acts_b.to(device)
            
            optimizer.zero_grad()
            preds = model(obs_b)
            
            # Joint angle loss (MSE)
            joint_loss = mse_loss_fn(preds[:, :5], acts_b[:, :5])
            
            # Gripper binary state loss (BCE)
            gripper_loss = bce_loss_fn(preds[:, 5], acts_b[:, 5])
            
            loss = joint_loss + 5.0 * gripper_loss
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item() * len(obs_b)
            
        scheduler.step()
        epoch_loss = total_loss / len(dataset)
        
        if epoch % 10 == 0 or epoch == 1:
            print(f"Epoch [{epoch:03d}/{epochs:03d}] - Loss: {epoch_loss:.4f} (Joint MSE: {joint_loss.item():.4f}, Gripper BCE: {gripper_loss.item():.4f})")

    # Save PyTorch weights
    pth_path = os.path.join(OUTPUT_MODEL_DIR, "imitation_policy.pth")
    torch.save(model.state_dict(), pth_path)
    print(f"\nTrained policy saved: {pth_path}")
    
    # Export to ONNX for ultra-low latency Raspberry Pi 5 execution
    onnx_path = os.path.join(OUTPUT_MODEL_DIR, "imitation_policy.onnx")
    dummy_input = torch.randn(1, 9, device=device)
    torch.onnx.export(
        model,
        dummy_input,
        onnx_path,
        input_names=["observation"],
        output_names=["action"],
        dynamic_axes={"observation": {0: "batch_size"}, "action": {0: "batch_size"}},
        opset_version=14
    )
    print(f"Exported ONNX model for Raspberry Pi 5 inference: {onnx_path}")

if __name__ == "__main__":
    train_policy()
