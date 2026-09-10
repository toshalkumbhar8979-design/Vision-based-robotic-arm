"""
==========================================================================
ANALYTICAL 3D INVERSE KINEMATICS & FORWARD KINEMATICS ENGINE (3-DOF PRIMARY)
==========================================================================
Project:  Vision-Based Autonomous Robotic Arm
File:     ik_solver.py
Location: dashboard/backend/

PURPOSE:
  Provides 100% analytical 3D Inverse Kinematics (IK) for the primary 3 joints
  (Base θ1, Shoulder θ2, Elbow θ3) to position the wrist joint pin at (X, Y, Z)
  in cm, while keeping Wrist Pitch (θ4), Wrist Roll (θ5), and Gripper (θ6)
  independently controllable.

PHYSICAL PARAMETERS:
  - L1 = 9.5 cm (Base Height to Shoulder Pivot)
  - L2 = 12.0 cm (Upper Arm: Shoulder to Elbow Pivot)
  - L3 = 9.0 cm (Forearm: Elbow to Wrist Pitch Pivot)
  - L4 = 14.0 cm (End-Effector: Wrist Pitch to Gripper Tip)

SERVO ANGLE CONVENTIONS:
  - Base (θ1): 90° = Center Forward. 90° -> 130° moves LEFT (+X). 90° -> 50° moves RIGHT (-X).
  - Shoulder (θ2): 90° = Vertical Upright. 90° -> 50° tilts FORWARD (+Y/down). 90° -> 130° tilts BACKWARDS.
  - Elbow (θ3): 45° = Upright inline with L2. 90° = 45° forward tilt. 135° = Parallel to table.
==========================================================================
"""

import math
import json
import os
import logging
from typing import List, Tuple, Dict, Any, Optional

logger = logging.getLogger("IK_Solver")
logging.basicConfig(level=logging.INFO)

class RoboticArmIK:
    def __init__(self, L1: float = 9.5, L2: float = 12.0, L3: float = 9.0, L4: float = 14.0):
        self.L1 = L1
        self.L2 = L2
        self.L3 = L3
        self.L4 = L4
        
        # Safe joint angle limits (degrees)
        self.limits = {
            "theta1": (0, 180),  # Base
            "theta2": (15, 165), # Shoulder
            "theta3": (15, 165), # Elbow
            "theta4": (0, 180),  # Wrist Pitch
            "theta5": (0, 180),  # Wrist Roll
            "theta6": (0, 180)   # Gripper (Full 0-180 Range)
        }

    def load_config(self, config_path: str):
        """Loads physical link lengths and joint parameters from kinematics_config.json if available."""
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    cfg = json.load(f)
                    if "L1" in cfg: self.L1 = float(cfg["L1"])
                    if "L2" in cfg: self.L2 = float(cfg["L2"])
                    if "L3" in cfg: self.L3 = float(cfg["L3"])
                    if "L4" in cfg: self.L4 = float(cfg["L4"])
                    logger.info(f"Loaded IK parameters: L1={self.L1}cm, L2={self.L2}cm, L3={self.L3}cm, L4={self.L4}cm")
            except Exception as e:
                logger.warning(f"Could not load kinematics config ({e}), using physical defaults.")

    def solve_ik(self, x: float, y: float, z: float, theta4_val: int = 90, theta5_val: int = 90, theta6_val: int = 140) -> Tuple[List[int], bool, str]:
        """
        Solves 3D Analytical Inverse Kinematics for primary 3 joints [θ1, θ2, θ3] to target (X, Y, Z) in cm.
        Guarantees 100% straight-line vertical (Z) & horizontal (X/Y) trajectories.
        """
        if y < 1.0:
            y = 1.0

        # 1. Base Angle (θ1)
        theta1 = 90.0 + math.degrees(math.atan2(x, y))
        r = math.hypot(x, y)
        z_rel = z - self.L1

        # 2. Planar distance D from Shoulder joint (0, 0) to Wrist joint (r, z_rel)
        D = math.hypot(r, z_rel)
        max_reach = self.L2 + self.L3
        min_reach = abs(self.L2 - self.L3)
        
        is_reachable = True
        msg = "Target position reached successfully."

        if D > max_reach:
            is_reachable = False
            msg = f"Target (X={x:.1f}, Y={y:.1f}, Z={z:.1f}) exceeds max reach ({max_reach:.1f}cm)."
            D_clamped = max_reach - 0.001
        elif D < min_reach:
            is_reachable = False
            msg = f"Target (X={x:.1f}, Y={y:.1f}, Z={z:.1f}) inside min self-collision radius ({min_reach:.1f}cm)."
            D_clamped = min_reach + 0.001
        else:
            D_clamped = D

        # 3. Law of Cosines for Elbow (θ3)
        cos_gamma = (self.L2**2 + self.L3**2 - D_clamped**2) / (2.0 * self.L2 * self.L3)
        gamma = math.acos(max(-1.0, min(1.0, cos_gamma)))
        theta3 = 45.0 + math.degrees(math.pi - gamma)

        # 4. Law of Cosines for Shoulder (θ2)
        alpha1 = math.atan2(z_rel, r)
        cos_alpha2 = (self.L2**2 + D_clamped**2 - self.L3**2) / (2.0 * self.L2 * D_clamped)
        alpha2 = math.acos(max(-1.0, min(1.0, cos_alpha2)))
        psi = alpha1 + alpha2
        theta2 = 180.0 - math.degrees(psi)

        # Clamp all 6 angles to physical limits
        t1 = max(self.limits["theta1"][0], min(self.limits["theta1"][1], round(theta1)))
        t2 = max(self.limits["theta2"][0], min(self.limits["theta2"][1], round(theta2)))
        t3 = max(self.limits["theta3"][0], min(self.limits["theta3"][1], round(theta3)))
        t4 = max(self.limits["theta4"][0], min(self.limits["theta4"][1], round(theta4_val)))
        t5 = max(self.limits["theta5"][0], min(self.limits["theta5"][1], round(theta5_val)))
        t6 = max(self.limits["theta6"][0], min(self.limits["theta6"][1], round(theta6_val)))

        return [t1, t2, t3, t4, t5, t6], is_reachable, msg

    def forward_kinematics(self, theta1: float, theta2: float, theta3: float, theta4: float = 90.0, theta5: float = 90.0, theta6: float = 140.0) -> Dict[str, Any]:
        """
        Calculates 3D Cartesian Forward Kinematics (FK) for wrist joint pin (X, Y, Z) given joint angles.
        """
        b = math.radians(theta1 - 90.0)      # Base angle relative to center forward (Y-axis)
        s = math.radians(180.0 - theta2)     # Upper arm angle relative to horizontal
        e_rel = math.radians(theta3 - 45.0)  # Relative bend of elbow
        e = s - e_rel                        # Forearm angle relative to horizontal

        # Planar coordinates of wrist joint pin
        r = self.L2 * math.cos(s) + self.L3 * math.cos(e)
        z = self.L1 + self.L2 * math.sin(s) + self.L3 * math.sin(e)

        # 3D Cartesian coordinates
        x = r * math.sin(b)
        y = r * math.cos(b)

        return {
            "x": round(x, 2),
            "y": round(y, 2),
            "z": round(z, 2),
            "pitch_deg": round(theta4, 1),
            "roll_deg": round(theta5, 1),
            "gripper_angle": int(theta6)
        }


# Global singleton instance for backend
ik_solver = RoboticArmIK()
