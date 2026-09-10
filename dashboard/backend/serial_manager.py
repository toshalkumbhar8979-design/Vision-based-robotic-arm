"""
==============================================================================
SERIAL MANAGER — Arduino Communication Subsystem
==============================================================================

Project:  Vision-Based Autonomous Robotic Arm
File:     serial_manager.py
Location: dashboard/backend/

PURPOSE:
    Manages the low-level USB Serial connection between the Python backend
    (FastAPI / host machine) and the Arduino Uno firmware (robot_driver.ino).

KEY FEATURES:
    - Integrates with `arduino-cli board list --json` to detect genuine Arduinos (Decision #15)
    - Filters out macOS system virtual ports (debug-console, Bluetooth ports)
    - Transmits binary 6-byte command packets at 115200 baud (Decision #6)
    - Enforces 0–180 degree clamping per servo
    - Provides instant "Lock at 90°", "Home", and "Emergency Stop" routines

RELATED DECISIONS (from decisions.md):
    - Decision #5: Safety System (Emergency Stop + Watchdog)
    - Decision #6: Serial Protocol (Binary 6-byte packets at 115200 baud)
    - Decision #14: Arduino Port Management (`arduino-cli` / port scan)
    - Decision #19: Dashboard Phase A as Hardware Assembly Tool
    - Decision #20: S-Curve Cosine Interpolation for Smooth Motion
==============================================================================
"""

import os
import time
import math
import json
import shutil
import asyncio
import subprocess
import threading
import logging
from typing import List, Dict, Optional, Tuple
import serial
import serial.tools.list_ports

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SerialManager")

NUM_SERVOS = 6
DEFAULT_BAUD = 115200

# Gripper Angle Calibration Constants (User will calibrate post-assembly)
GRIPPER_CLOSED_ANGLE = 85
GRIPPER_OPEN_ANGLE = 140

DEFAULT_HOME_ANGLES = [90, 90, 90, 90, 90, GRIPPER_OPEN_ANGLE]

# List of macOS/Linux virtual Bluetooth & audio ports that must NEVER be listed or connected
IGNORED_PORT_KEYWORDS = [
    "debug-console",
    "bluetooth",
    "wlan-debug",
    "soc",
    "tty.bluetooth",
    "cu.bluetooth",
    "stone",
    "airdopes",
    "airpods",
    "speaker",
    "headset",
    "headphone",
    "handsfree"
]


CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "kinematics_config.json"))

class SerialManager:
    def __init__(self):
        self._serial: Optional[serial.Serial] = None
        self.port: Optional[str] = None
        self.baudrate: int = DEFAULT_BAUD
        self.is_connected: bool = False
        self.is_estop: bool = False
        
        self.gripper_open: int = 140
        self.gripper_closed: int = 85
        self.load_kinematics_config()

        # Track current commanded angles [Base, Shoulder, Elbow, WristPitch, WristRoll, Gripper]
        self.current_angles: List[int] = [90, 90, 90, 90, 90, self.gripper_open]
        
        # Thread lock for serial writing
        self._lock = threading.Lock()
        self.is_sweeping: bool = False

        # Cached CLI check to avoid subprocess slowdowns during 30Hz WebSocket streaming
        self._has_cli_cache: Optional[bool] = None
        self._cli_msg_cache: str = ""

    def load_kinematics_config(self):
        """Loads persisted gripper open/close angles from kinematics_config.json on startup."""
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    cfg = json.load(f)
                    self.gripper_open = cfg.get("gripper_open", 140)
                    self.gripper_closed = cfg.get("gripper_closed", 85)
            except Exception as e:
                logger.warning(f"Could not load kinematics_config.json in SerialManager: {e}")

    def check_arduino_cli(self, force_refresh: bool = False) -> Tuple[bool, str]:
        """Checks if `arduino-cli` is installed and available in PATH (cached)."""
        if self._has_cli_cache is not None and not force_refresh:
            return self._has_cli_cache, self._cli_msg_cache

        cli_path = shutil.which("arduino-cli")
        if cli_path:
            try:
                res = subprocess.run(["arduino-cli", "version"], capture_output=True, text=True, timeout=2)
                self._has_cli_cache = True
                self._cli_msg_cache = res.stdout.strip()
                return True, self._cli_msg_cache
            except Exception as e:
                self._has_cli_cache = False
                self._cli_msg_cache = f"arduino-cli error: {e}"
                return False, self._cli_msg_cache
        self._has_cli_cache = False
        self._cli_msg_cache = "arduino-cli is NOT installed. (Run: `brew install arduino-cli`)"
        return False, self._cli_msg_cache

    async def smooth_transition_to_angles(self, target_angles: List[int], duration_sec: float = 1.2, broadcast_callback=None) -> Tuple[bool, str]:
        """
        Executes Cosine S-Curve minimum-jerk trajectory interpolation to transition smoothly
        from current_angles to target_angles. Ramps acceleration from zero to prevent mechanical jerks.
        (Decision #20)
        """
        if self.is_estop:
            return False, "Transition aborted: Emergency Stop is active."

        start_angles = list(self.current_angles)
        target_clamped = [max(0, min(180, int(a))) for a in target_angles]

        steps = max(10, int(duration_sec * 30)) # 30Hz target update rate
        dt = duration_sec / steps

        for step in range(1, steps + 1):
            if self.is_estop:
                logger.warning("Smooth transition cancelled due to E-Stop.")
                return False, "Cancelled by E-Stop"

            # Cosine S-Curve blending factor t_factor in [0, 1]
            t = step / steps
            s_factor = (1.0 - math.cos(math.pi * t)) / 2.0  # Zero velocity at t=0 and t=1

            interpolated = [
                int(start_angles[i] + (target_clamped[i] - start_angles[i]) * s_factor)
                for i in range(NUM_SERVOS)
            ]

            self.send_angles(interpolated)
            if broadcast_callback:
                await broadcast_callback()
            await asyncio.sleep(dt)

        return True, "Smooth transition completed"

    async def test_single_servo(self, servo_index: int, broadcast_callback=None) -> Tuple[bool, str]:
        """
        Performs a smooth solo sweep test on a single servo (0 to 5) from current -> 30° -> 150° -> 90°
        to test individual joint movement in isolation during physical assembly.
        """
        if self.is_estop:
            return False, "Cannot test servo: Emergency Stop is active."

        if servo_index < 0 or servo_index >= NUM_SERVOS:
            return False, f"Invalid servo index {servo_index}."

        logger.info(f"Starting Solo Test on Servo {servo_index}...")
        start_angles = list(self.current_angles)

        # Target 1: 30 degrees
        t1 = list(start_angles)
        t1[servo_index] = 30
        await self.smooth_transition_to_angles(t1, duration_sec=0.8, broadcast_callback=broadcast_callback)
        await asyncio.sleep(0.2)

        # Target 2: 150 degrees
        t2 = list(start_angles)
        t2[servo_index] = 150
        await self.smooth_transition_to_angles(t2, duration_sec=1.0, broadcast_callback=broadcast_callback)
        await asyncio.sleep(0.2)

        # Target 3: Return to 90 degrees
        t3 = list(start_angles)
        t3[servo_index] = 90
        await self.smooth_transition_to_angles(t3, duration_sec=0.8, broadcast_callback=broadcast_callback)

        return True, f"Solo test on Servo {servo_index} completed."

    async def move_to_home(self, broadcast_callback=None) -> Tuple[bool, str]:
        """Moves all servos smoothly to predefined Home Position angles (Decision #20)."""
        self.is_estop = False
        return await self.smooth_transition_to_angles(DEFAULT_HOME_ANGLES, duration_sec=1.2, broadcast_callback=broadcast_callback)

    async def run_joint_sweep_test(self, broadcast_callback=None) -> Tuple[bool, str]:
        """
        Executes a smooth Cosine S-Curve joint sweep test across all 6 servos to verify
        mechanical assembly and check for physical plastic collisions.
        Automatically returns smoothly to Home Position upon completion. (Decision #20)
        """
        if self.is_estop:
            return False, "Cannot sweep: Emergency Stop is active."

        if self.is_sweeping:
            return False, "Sweep test is already running."

        self.is_sweeping = True
        logger.info("Starting Zero-Jerk Joint Sweep Test...")

        # Define sweep waypoints: (Base, Shoulder, Elbow, WristPitch, WristRoll, Gripper)
        waypoints = [
            [45, 90, 90, 90, 90, GRIPPER_CLOSED_ANGLE],    # Base left (start sweeping immediately)
            [135, 90, 90, 90, 90, GRIPPER_CLOSED_ANGLE],   # Base right
            [90, 60, 120, 90, 90, GRIPPER_CLOSED_ANGLE],   # Shoulder/Elbow flex
            [90, 120, 60, 90, 90, GRIPPER_CLOSED_ANGLE],   # Shoulder/Elbow extend
            [90, 90, 90, 45, 45, GRIPPER_CLOSED_ANGLE],    # Wrist pitch/roll min
            [90, 90, 90, 135, 135, GRIPPER_CLOSED_ANGLE],  # Wrist pitch/roll max
            [90, 90, 90, 90, 90, GRIPPER_OPEN_ANGLE],      # Gripper open
            [90, 90, 90, 90, 90, GRIPPER_CLOSED_ANGLE],    # Gripper close
        ]

        try:
            for target in waypoints:
                if self.is_estop or not self.is_sweeping:
                    logger.warning("Sweep aborted due to E-Stop or cancel signal.")
                    break

                await self.smooth_transition_to_angles(target, duration_sec=1.0, broadcast_callback=broadcast_callback)
                await asyncio.sleep(0.15) # Pause briefly at each waypoint

            # Final smooth return to Home Position
            logger.info("Sweep completed. Returning smoothly to Home Position.")
            await self.smooth_transition_to_angles(DEFAULT_HOME_ANGLES, duration_sec=1.2, broadcast_callback=broadcast_callback)
        finally:
            self.is_sweeping = False

        return True, "Joint Sweep Test completed."

    def check_arduino_cli(self) -> Tuple[bool, str]:
        """Checks if `arduino-cli` is installed and available in PATH."""
        cli_path = shutil.which("arduino-cli")
        if cli_path:
            try:
                res = subprocess.run(["arduino-cli", "version"], capture_output=True, text=True, timeout=2)
                return True, res.stdout.strip()
            except Exception as e:
                return False, f"arduino-cli error: {e}"
        return False, "arduino-cli is NOT installed. (Run: `brew install arduino-cli`)"

    def list_available_ports(self) -> List[Dict[str, str]]:
        """
        Scans for available serial ports using both `arduino-cli` (if available)
        and `pyserial.tools.list_ports`. Filters out macOS virtual debug ports.
        """
        arduino_cli_boards = {}
        has_cli, _ = self.check_arduino_cli()

        # Try query via arduino-cli JSON output first (Decision #15)
        if has_cli:
            try:
                res = subprocess.run(
                    ["arduino-cli", "board", "list", "--json"],
                    capture_output=True, text=True, timeout=3
                )
                if res.returncode == 0:
                    data = json.loads(res.stdout)
                    # arduino-cli board list JSON structure
                    detected_list = data if isinstance(data, list) else data.get("detected_ports", [])
                    for entry in detected_list:
                        port_info = entry.get("port", {})
                        port_address = port_info.get("address", "")
                        boards = entry.get("matching_boards", [])
                        if port_address:
                            board_name = boards[0].get("name") if boards else "Unknown Board"
                            arduino_cli_boards[port_address] = {
                                "is_arduino": len(boards) > 0 or "arduino" in port_info.get("protocol_label", "").lower(),
                                "board_name": board_name
                            }
            except Exception as e:
                logger.warning(f"arduino-cli query failed: {e}")

        ports = serial.tools.list_ports.comports()
        result = []

        for p in ports:
            dev = p.device
            dev_lower = dev.lower()
            
            # Skip system virtual ports that are not physical USB devices
            if any(k in dev_lower for k in IGNORED_PORT_KEYWORDS):
                continue

            desc = p.description or ""
            desc_lower = desc.lower()

            # Check if identified by arduino-cli or pyserial keywords
            cli_info = arduino_cli_boards.get(dev, {})
            is_arduino = (
                cli_info.get("is_arduino", False) or
                "arduino" in desc_lower or
                "usbmodem" in dev_lower or
                "ttyacm" in dev_lower or
                "ch340" in desc_lower or
                "ftdi" in desc_lower
            )

            board_name = cli_info.get("board_name") or (desc if desc and desc != "n/a" else "USB Serial Device")

            result.append({
                "port": dev,
                "description": desc,
                "board_name": board_name,
                "is_arduino": is_arduino
            })

        return result

    def auto_connect(self) -> Tuple[bool, str]:
        """
        Attempts to auto-detect and connect to a genuine Arduino Uno.
        Refuses to connect to virtual macOS system ports.
        """
        ports = self.list_available_ports()
        if not ports:
            return False, "No physical USB serial devices detected. Please plug in your Arduino Uno."

        # Prioritize ports identified as genuine Arduino / USB Modem
        target_port = None
        for p in ports:
            if p["is_arduino"]:
                target_port = p["port"]
                break
        
        if not target_port:
            return False, "No genuine Arduino detected. Please connect your Arduino Uno via USB cable."

        return self.connect(target_port)

    def connect(self, port: str, baudrate: int = DEFAULT_BAUD) -> Tuple[bool, str]:
        """Establishes serial connection to specified port."""
        dev_lower = port.lower()
        if any(k in dev_lower for k in IGNORED_PORT_KEYWORDS):
            return False, f"Refusing to connect to virtual system port '{port}'."

        with self._lock:
            if self.is_connected:
                self._disconnect_internal()

            try:
                logger.info(f"Connecting to Arduino on {port} @ {baudrate} baud...")
                self._serial = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    timeout=0.1,
                    write_timeout=0.1
                )
                time.sleep(1.5)  # Wait for Arduino reset after DTR toggle
                
                self.port = port
                self.baudrate = baudrate
                self.is_connected = True
                self.is_estop = False
                logger.info(f"Successfully connected to Arduino on {port}")
                
                # Send home angles on initial connection
                self._send_bytes_internal(self.current_angles)
                return True, f"Connected to {port}"
                
            except Exception as e:
                self.is_connected = False
                self.port = None
                logger.error(f"Failed to connect to {port}: {e}")
                return False, str(e)

    def disconnect(self) -> Tuple[bool, str]:
        """Safely closes the serial connection."""
        with self._lock:
            return self._disconnect_internal()

    def _disconnect_internal(self) -> Tuple[bool, str]:
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception as e:
                logger.warning(f"Error closing port: {e}")
        self.is_connected = False
        self.port = None
        return True, "Disconnected"

    def send_angles(self, angles: List[int]) -> Tuple[bool, str]:
        """
        Sends 6 servo angles (0–180) to Arduino as a binary 6-byte packet.
        Format: [Base, Shoulder, Elbow, WristPitch, WristRoll, Gripper]
        """
        if self.is_estop:
            return False, "Emergency Stop is ACTIVE. Reset E-Stop first."
            
        if len(angles) != NUM_SERVOS:
            return False, f"Expected exactly {NUM_SERVOS} angles, got {len(angles)}"

        # Clamp all angles to safe 0–180 range across all 6 servos
        clamped_angles = [max(0, min(180, int(a))) for a in angles]

        with self._lock:
            self.current_angles = clamped_angles
            if not self.is_connected or not self._serial or not self._serial.is_open:
                # Return success for simulation/UI testing even if offline
                return True, "Angles updated (Offline mode)"

            return self._send_bytes_internal(clamped_angles)

    def _send_bytes_internal(self, angles: List[int]) -> Tuple[bool, str]:
        """Internal helper to write raw 7-byte packet with 0xFF header byte framing over serial."""
        try:
            # Prepend 0xFF header byte to guarantee 100% anti-jitter packet boundary alignment
            packet = bytes([0xFF] + list(angles))
            self._serial.write(packet)
            self._serial.flush()
            return True, "Packet sent"
        except Exception as e:
            logger.error(f"Serial write error: {e}")
            self.is_connected = False
            return False, f"Write error: {e}"

    async def lock_all_90(self, broadcast_callback=None) -> Tuple[bool, str]:
        """Locks all 6 servos smoothly to 90 degrees for mechanical assembly."""
        self.is_estop = False
        angles = [90, 90, 90, 90, 90, 90]
        return await self.smooth_transition_to_angles(angles, duration_sec=1.0, broadcast_callback=broadcast_callback)

    async def move_to_home(self, broadcast_callback=None) -> Tuple[bool, str]:
        """Moves all servos smoothly to predefined Home Position angles."""
        self.is_estop = False
        home_angles = [90, 90, 90, 90, 90, self.gripper_open]
        return await self.smooth_transition_to_angles(home_angles, duration_sec=1.2, broadcast_callback=broadcast_callback)

    def emergency_stop(self) -> Tuple[bool, str]:
        """
        Triggers instant software Emergency Stop.
        Flags E-Stop state and attempts to send Home angles.
        """
        self.is_estop = True
        logger.warning("EMERGENCY STOP TRIGGERED!")
        
        with self._lock:
            if self.is_connected and self._serial and self._serial.is_open:
                try:
                    # Attempt sending home angles immediately
                    self._serial.write(bytes(DEFAULT_HOME_ANGLES))
                    self._serial.flush()
                except Exception as e:
                    logger.error(f"E-Stop write error: {e}")
                    
        return True, "EMERGENCY STOP ACTIVATED"

    def reset_estop(self) -> Tuple[bool, str]:
        """Clears Emergency Stop state."""
        self.is_estop = False
        logger.info("Emergency stop reset.")
        return True, "E-Stop reset"

    def get_status(self) -> Dict:
        """Returns complete serial connection & servo state for WebSocket broadcast."""
        has_cli, cli_msg = self.check_arduino_cli()
        return {
            "is_connected": self.is_connected,
            "port": self.port,
            "baudrate": self.baudrate,
            "is_estop": self.is_estop,
            "is_sweeping": self.is_sweeping,
            "angles": self.current_angles,
            "has_arduino_cli": has_cli,
            "arduino_cli_info": cli_msg
        }


# Global singleton instance for the backend
serial_manager = SerialManager()
