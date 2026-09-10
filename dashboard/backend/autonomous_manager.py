"""
==============================================================================
ONNX AUTONOMOUS MANAGER — Behaviour Cloning Policy Execution Engine
==============================================================================
Project:  Vision-Based Autonomous Robotic Arm
File:     autonomous_manager.py
Location: dashboard/backend/

PURPOSE:
  Loads the trained Behaviour Cloning ONNX policy (Dataset_30/models/*.onnx)
  and, when the operator starts ONNX mode from the dashboard, runs a 30Hz
  closed-loop pick-and-place:  Camera ArUco block pose + current joint angles
  -> ONNX inference -> EMA-smoothed joint commands -> Arduino (PCA9685).

  ONNX CONTRACT (normalization baked into the graph at export time):
    Input  'observation' [1,9]: RAW [th1..th5 (deg), gripper_state (0/1),
                                 block_x (cm), block_y (cm), block_theta (deg)]
    Output 'action'      [1,6]: [th1'..th5' (deg 0-180), gripper_open_prob (0-1)]

  PRIME DIRECTIVE COMPLIANCE (Decision #24):
    Every commanded joint value passes through an Exponential Moving Average
    low-pass filter (alpha=0.25, snap within 2 deg) before hitting the serial
    line — zero jerks, zero snaps.

  MODE GUARANTEE:
    The arm only uses the model while autonomous mode is RUNNING. When stopped
    (or before it is ever started), the dashboard behaves 100% like before:
    sliders, PS5 teleop, IK and replay are untouched.
==============================================================================
"""

import os
import sys
import glob
import json
import time
import asyncio
import logging
from typing import List, Optional, Callable, Dict, Any

import numpy as np

logger = logging.getLogger("AutonomousManager")

# ONNX models live next to the dataset: <repo>/Dataset_30/models/*.onnx
MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Dataset_30", "models"))

LOOP_HZ = 30            # matches training/dataset frame rate (Decision #6)
EMA_ALPHA = 0.25        # low-pass factor (matches teleop_panel.js)
EMA_SNAP = 2            # snap when within 2 deg of target (removes asymptote)
GRIPPER_THRESHOLD = 110  # gripper angle <= 110 counts as CLOSED (dataset convention)
HOLD_ON_INVALID_POSE = True  # freeze joints when the block is not visible

# ---- AWOL PROTECTION (added after erratic policy behaviour was observed) ----
AWOL_JUMP_DEG = 12.0     # raw policy output jumping more than this in ONE frame is an
                         # anomaly (trained demos never exceeded 6 deg/frame at 30Hz)
AWOL_MAX_STRIKES = 2     # consecutive anomalous frames before auto-halt
MAX_CMD_STEP = 6         # commanded target may move at most this per frame (demo rate)


def _boost_windows_timer():
    """Raises the Windows timer resolution to 1ms. Without this, asyncio.sleep
    quantizes to the default 15.6ms kernel tick and the 30Hz loop runs at ~22Hz.
    No-op on macOS / Linux (Raspberry Pi 5)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass


def _restore_windows_timer():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass


class AutonomousManager:
    def __init__(self):
        self.session = None            # onnxruntime.InferenceSession
        self.model_path: Optional[str] = None
        self.model_name: Optional[str] = None
        self.is_loaded: bool = False
        self.is_running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._broadcast: Optional[Callable] = None

        # Live telemetry (consumed by the dashboard panel + /api/onnx/status)
        self.smoothed: List[int] = [90, 90, 90, 90, 90, 140]
        self.predicted: List[float] = [90, 90, 90, 90, 90, 0.5]
        self.frames = 0
        self.started_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.holding: bool = False

        # AWOL watchdog state
        self._prev_raw: Optional[List[float]] = None   # last raw policy output
        self._awol_strikes = 0                          # consecutive anomalous frames
        self._prev_cmd: Optional[List[int]] = None      # last commanded 5-joint target

    # ------------------------------------------------------------------ #
    # Model management
    # ------------------------------------------------------------------ #
    def list_models(self) -> List[Dict[str, Any]]:
        """Lists all .onnx policy files available in Dataset_30/models."""
        models = []
        if os.path.isdir(MODEL_DIR):
            for p in sorted(glob.glob(os.path.join(MODEL_DIR, "*.onnx"))):
                models.append({
                    "name": os.path.basename(p),
                    "size_kb": round(os.path.getsize(p) / 1024, 1),
                    "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p))),
                })
        return models

    def load_model(self, filename: str):
        """Lazily creates the onnxruntime session for the chosen policy.
        Idempotent: loading the same model twice is a no-op success."""
        filename = os.path.basename(str(filename or ""))
        if not filename:
            return False, "No model file specified."
        if self.is_loaded and self.model_name == filename:
            return True, f"Already loaded: {self.model_name}"
        import onnxruntime as ort
        path = os.path.abspath(os.path.join(MODEL_DIR, filename))
        if not path.startswith(MODEL_DIR) or not os.path.exists(path):
            available = [m["name"] for m in self.list_models()]
            return False, (f"Model '{filename}' not found in {MODEL_DIR}. "
                           f"Available: {available or 'none'}")
        try:
            self.session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
            self.model_path = path
            self.model_name = os.path.basename(path)
            self.is_loaded = True
            logger.info(f"ONNX policy loaded: {self.model_name}")
            return True, f"Loaded {self.model_name}"
        except Exception as e:
            self.is_loaded = False
            self.session = None
            logger.error(f"Failed to load ONNX model {filename}: {e}")
            return False, f"Failed to load model: {e}"

    def _infer(self, obs: List[float]) -> List[float]:
        """Runs one raw-input inference pass. Returns [th1'..th5', p_open]."""
        out = self.session.run(["action"], {"observation": np.array([obs], dtype=np.float32)})
        return [float(v) for v in out[0][0]]

    # ------------------------------------------------------------------ #
    # Start / stop control
    # ------------------------------------------------------------------ #
    async def start(self, broadcast_callback=None):
        if not self.is_loaded:
            return False, "No ONNX model loaded. Load a model first."
        if self.is_running:
            return False, "Autonomous mode is already running."
        self.is_running = True
        self._broadcast = broadcast_callback
        self.frames = 0
        self.started_at = time.time()
        self.last_error = None
        # CRITICAL: seed the EMA state from the arm's ACTUAL current angles.
        # Seeding at Home caused a violent jump-to-home jolt when the arm was
        # anywhere else when autonomous mode started.
        from serial_manager import serial_manager
        cur = list(serial_manager.current_angles)
        self.smoothed = [int(cur[0]), int(cur[1]), int(cur[2]), int(cur[3]), int(cur[4]), int(cur[5])]
        self._prev_raw = None
        self._awol_strikes = 0
        self._prev_cmd = self.smoothed[:5]
        _boost_windows_timer()
        self._task = asyncio.create_task(self._loop())
        logger.info("ONNX autonomous pick-and-place STARTED.")
        return True, "ONNX autonomous mode started (30Hz closed loop)."

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("ONNX autonomous mode STOPPED. Dashboard returns to manual control.")
        return True, "Autonomous mode stopped."

    def stop_sync(self):
        """Non-async stop for app shutdown / signal handlers."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def override(self):
        """MANUAL OVERRIDE: instantly halts the policy and freezes the arm in
        place — control returns to the operator immediately (no homing motion).
        This is the operator's take-control button against AWOL behaviour."""
        was_running = self.is_running
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if was_running:
            logger.warning("MANUAL OVERRIDE engaged — policy halted instantly, arm frozen in place.")
        return True, ("MANUAL OVERRIDE engaged — model halted instantly, arm frozen in place. "
                      "You have manual control now (sliders / PS5 / Home button).")

    def get_model_info(self) -> Dict[str, Any]:
        """Model Card: everything the operator needs to know about the policy."""
        info = {
            "model_name": self.model_name or "(no model loaded)",
            "loaded": self.is_loaded,
            "running": self.is_running,
            "architecture": ("MLP 9 -> 256 -> 256 -> 128 (LayerNorm + Mish + Dropout 0.05) "
                             "with joint head (128->5) and binary gripper head (128->1, sigmoid)"),
            "framework": "PyTorch 2.x, exported to ONNX opset 14 (normalization baked into the graph)",
            "dataset": ("750 pick-and-place demonstrations — 30 real human DJT + 720 synthetic, "
                        "24 workspace cells, theta 0/+90/-90/+180 families"),
            "transitions": "549,424 state-action pairs",
            "epochs": 50,
            "val_joint_mae_deg": 0.19,
            "gripper_accuracy": "99.7%",
            "obs_contract": "[th1..th5 (deg), gripper_state (0/1), block_x (cm), block_y (cm), block_theta (deg)] — RAW",
            "act_contract": "[th1'..th5' (deg), gripper_open_prob (0-1)] — RAW",
            "inference": "onnxruntime CPU, ~1-2 ms/frame at 30Hz (RPi5-ready)",
            "safety": "EMA alpha=0.25 + 6 deg/frame command clamp + AWOL watchdog (auto-halt)",
        }
        if self.model_path and os.path.exists(self.model_path):
            st = os.stat(self.model_path)
            info["file_size_kb"] = round(st.st_size / 1024, 1)
            info["exported"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
            sidecar = self.model_path[:-5] + ".json"   # optional future metadata sidecar
            if os.path.exists(sidecar):
                try:
                    with open(sidecar, "r") as fh:
                        info.update(json.load(fh))
                except Exception:
                    pass
        return info


    def get_status(self) -> Dict[str, Any]:
        runtime = (time.time() - self.started_at) if self.started_at else 0.0
        return {
            "is_loaded": self.is_loaded,
            "model_name": self.model_name,
            "is_running": self.is_running,
            "frames": self.frames,
            "runtime_sec": round(runtime, 1),
            "infer_hz": round(self.frames / runtime, 1) if runtime > 0.5 else 0.0,
            "holding": self.holding,
            "last_error": self.last_error,
            "awol_strikes": self._awol_strikes,
            "smoothed_joints": self.smoothed,
            "predicted_joints": [round(v, 1) for v in self.predicted],
        }

    async def _loop(self):
        """
        30Hz closed loop: vision block pose + joint state -> ONNX policy ->
        EMA low-pass smoothing -> serial line. (PRIME DIRECTIVE compliant.)
        """
        from serial_manager import serial_manager
        from vision_manager import vision_manager_cam1

        try:
            while self.is_running:
                t_frame = time.time()
                self.holding = False
                try:
                    # Decision #5: E-Stop halts autonomous mode INSTANTLY.
                    # Checked FIRST every frame, in BOTH hold and infer branches.
                    if serial_manager.is_estop:
                        logger.warning("E-Stop active — ONNX autonomous mode self-halted.")
                        self.is_running = False
                        break

                    angles = list(serial_manager.current_angles)
                    grip_state = 1 if angles[5] <= GRIPPER_THRESHOLD else 0

                    # Observation: block pose from the live Camera 1 ArUco pipeline.
                    # If the block is not visible we HOLD (freeze) — never guess.
                    pose = vision_manager_cam1.latest_block_pose
                    if HOLD_ON_INVALID_POSE and not pose.get("valid"):
                        self.holding = True
                        self.predicted = [float(a) for a in angles[:5]] + [1.0 - grip_state]
                    else:
                        obs = angles[:5] + [float(grip_state),
                                            float(pose["x_cm"]), float(pose["y_cm"]),
                                            float(pose["theta_deg"])]
                        action = self._infer(obs)
                        raw5 = action[:5]
                        self.predicted = action

                        # ---- AWOL WATCHDOG --------------------------------------------
                        # Trained demonstrations never moved faster than 6 deg/frame at
                        # 30Hz. A raw policy jump above AWOL_JUMP_DEG in a single frame is
                        # an anomaly (vision glitch / out-of-distribution state) — the
                        # frame is NOT commanded, and 2 consecutive anomalies auto-halt.
                        jump = 0.0
                        if self._prev_raw is not None:
                            jump = max(abs(raw5[i] - self._prev_raw[i]) for i in range(5))
                        self._prev_raw = raw5
                        suspicious = jump > AWOL_JUMP_DEG
                        if suspicious:
                            self._awol_strikes += 1
                            if self._awol_strikes >= AWOL_MAX_STRIKES:
                                self.is_running = False
                                self.last_error = (f"AWOL WATCHDOG: policy jumped {jump:.1f} deg "
                                                   f"in one frame (> {AWOL_JUMP_DEG:.0f}). "
                                                   "Autonomous mode AUTO-HALTED, arm frozen. "
                                                   "Manual control restored.")
                                logger.error(self.last_error)
                                break
                        else:
                            self._awol_strikes = 0

                        if suspicious:
                            self.holding = True   # freeze this anomalous frame (do NOT command)
                        else:
                            # Per-frame rate clamp: the commanded target may move at most
                            # MAX_CMD_STEP per frame from the previous target (demo rate).
                            targets = [max(0, min(180, int(round(a)))) for a in raw5]
                            if self._prev_cmd is not None:
                                targets = [max(self._prev_cmd[i] - MAX_CMD_STEP,
                                               min(self._prev_cmd[i] + MAX_CMD_STEP, targets[i]))
                                           for i in range(5)]
                            self._prev_cmd = targets

                            # EMA low-pass filter + threshold snap (Decision #24)
                            for i in range(5):
                                diff = abs(targets[i] - self.smoothed[i])
                                if diff <= EMA_SNAP or targets[i] in (0, 180):
                                    self.smoothed[i] = targets[i]
                                else:
                                    self.smoothed[i] = int(round(
                                        targets[i] * EMA_ALPHA + self.smoothed[i] * (1 - EMA_ALPHA)))

                            # Gripper: binary state paradigm (0=OPEN / 1=CLOSED)
                            grip_open = action[5] >= 0.5
                            target_grip = serial_manager.gripper_open if grip_open else serial_manager.gripper_closed
                            gd = abs(target_grip - self.smoothed[5])
                            if gd <= EMA_SNAP:
                                self.smoothed[5] = target_grip
                            else:
                                self.smoothed[5] = int(round(
                                    target_grip * EMA_ALPHA + self.smoothed[5] * (1 - EMA_ALPHA)))

                            ok, msg = serial_manager.send_angles(self.smoothed)
                            if not ok and "Offline" not in msg:
                                self.last_error = msg

                    self.frames += 1
                    if self._broadcast and self.frames % 6 == 0:  # ~5Hz UI updates
                        await self._broadcast()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self.last_error = str(e)
                    logger.error(f"Autonomous loop frame error: {e}")

                # Frame pacing to exactly LOOP_HZ
                dt = time.time() - t_frame
                await asyncio.sleep(max(0.001, (1.0 / LOOP_HZ) - dt))
        except asyncio.CancelledError:
            pass
        finally:
            self.is_running = False
            self._task = None
            _restore_windows_timer()
            if self._broadcast:
                try:
                    await self._broadcast()
                except BaseException:
                    pass


# Global singleton used by main.py
autonomous_manager = AutonomousManager()
