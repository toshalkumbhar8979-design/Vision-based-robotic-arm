"""
==============================================================================
DASHBOARD FASTAPI BACKEND SERVER
==============================================================================

Project:  Vision-Based Autonomous Robotic Arm
File:     main.py
Location: dashboard/backend/

PURPOSE:
    Asynchronous web server providing REST endpoints and WebSocket real-time
    communication for the Dashboard UI. Serves the static Warm Cream HTML/CSS/JS
    frontend and interfaces directly with serial_manager.py.

KEY ENDPOINTS:
    - GET  /api/ports             Lists available serial ports
    - POST /api/connect           Connects to a specific serial port
    - POST /api/disconnect        Disconnects from Arduino
    - POST /api/lock90            Locks all 6 servos at 90° for assembly
    - POST /api/home              Moves all servos to Home Position
    - POST /api/estop             Triggers Emergency Stop
    - POST /api/estop/reset       Resets Emergency Stop state
    - WS   /ws                    Real-time WebSocket for telemetry & slider streaming

RELATED DECISIONS:
    - Decision #11: Web-based Dashboard (FastAPI + WebSockets)
    - Decision #15: No authentication required
    - Decision #18: Warm light cream theme support
    - Decision #19: Active physical assembly tool
==============================================================================
"""

import os
import json
import asyncio
import logging
import urllib.request
import urllib.error
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from serial_manager import serial_manager
from vision_manager import vision_manager_cam1
from ik_solver import ik_solver
from autonomous_manager import autonomous_manager, MODEL_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DashboardBackend")

app = FastAPI(
    title="Robotic Arm Control Dashboard Backend",
    version="1.0.0"
)

UPLOADS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/uploads"))
os.makedirs(UPLOADS_DIR, exist_ok=True)

SUPABASE_URL = "https://pzewxynfhrylnqbkkeeq.supabase.co"
SUPABASE_KEY = "sb_publishable_5OpuR0lsXoop77YXHtP01g_owDDLGe_"

@app.post("/api/upload")
async def upload_media_file(file: UploadFile = File(...)):
    """Uploads media (video/photo/doc) locally and syncs to Supabase Cloud Storage."""
    clean_name = f"{int(asyncio.get_event_loop().time() * 1000)}_{file.filename.replace(' ', '_')}"
    local_path = os.path.join(UPLOADS_DIR, clean_name)
    
    contents = await file.read()
    with open(local_path, "wb") as f:
        f.write(contents)
        
    public_url = f"/uploads/{clean_name}"
    
    # Attempt background sync to Supabase Cloud Storage
    try:
        supa_url = f"{SUPABASE_URL}/storage/v1/object/journal-media/{clean_name}"
        req = urllib.request.Request(supa_url, data=contents, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("x-upsert", "true")
        req.add_header("Content-Type", file.content_type or "application/octet-stream")
        
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 201):
                public_url = f"{SUPABASE_URL}/storage/v1/object/public/journal-media/{clean_name}"
    except Exception as e:
        logger.warning(f"Cloud storage sync warning (using local URL): {e}")

    file_ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    return {
        "status": "success",
        "name": file.filename,
        "type": file_ext,
        "url": public_url
    }

# Allow CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track active WebSocket connections
active_connections: List[WebSocket] = []


# Request Models
class ConnectRequest(BaseModel):
    port: str
    baudrate: int = 115200


class ServoAnglesRequest(BaseModel):
    angles: List[int]


CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "kinematics_config.json"))
JOURNAL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "journal_entries.json"))
DATASET_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "dataset_episodes.json"))
DATASETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "datasets"))
os.makedirs(DATASETS_DIR, exist_ok=True)

class KinematicsConfigRequest(BaseModel):
    L1: float = 9.5
    L2: float = 12.0
    L3: float = 9.0
    L4: float = 14.0
    offsets: List[int] = [0, 0, 0, 0, 0, 0]
    gripper_closed: int = 85
    gripper_open: int = 140

class IKSolveRequest(BaseModel):
    x: float
    y: float
    z: float
    pitch_deg: float = 45.0
    roll_deg: float = 90.0
    gripper_angle: int = 140

class JournalEntriesRequest(BaseModel):
    entries: List[Dict[str, Any]]

class DatasetEpisodesRequest(BaseModel):
    episodes: List[Dict[str, Any]]


from dataset_formatter import save_compact_dataset_file, save_individual_episodes, load_individual_episodes

@app.on_event("shutdown")
def shutdown_event():
    logger.info("Stopping vision manager camera streams...")
    vision_manager_cam1.stop_camera()
    logger.info("Stopping ONNX autonomous mode (if running)...")
    autonomous_manager.stop_sync()


@app.get("/api/video_feed/1")
async def video_feed_cam1():
    """Live MJPEG video feed for Camera 1 (Logitech C270 Workspace View) with real-time OpenCV ArUco Marker ID 0 detection."""
    return StreamingResponse(
        vision_manager_cam1.generate_mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/api/vision/status")
async def get_vision_status():
    """Returns camera connection status, detected ArUco IDs, and real-world block pose relative to Origin Tag ID 2."""
    return {
        "camera1_connected": vision_manager_cam1.is_camera_connected,
        "detected_marker_ids": vision_manager_cam1.last_detected_ids,
        "latest_block_pose": vision_manager_cam1.latest_block_pose
    }


@app.get("/api/dataset")
async def get_dataset_episodes():
    """Returns persistent list of recorded demonstration episodes from individual JSON files."""
    return load_individual_episodes(DATASETS_DIR, DATASET_PATH)


@app.post("/api/dataset")
async def save_dataset_episodes(req: DatasetEpisodesRequest):
    """Saves persistent list of demonstration episodes into individual episode_XXX.json files in datasets/."""
    save_individual_episodes(req.episodes, DATASETS_DIR, DATASET_PATH)
    return {"status": "saved", "count": len(req.episodes)}


@app.get("/api/journal")
async def get_journal_entries():
    """Returns shared master list of journal entries."""
    if os.path.exists(JOURNAL_PATH):
        try:
            with open(JOURNAL_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []


@app.post("/api/journal")
async def save_journal_entries(req: JournalEntriesRequest):
    """Saves shared master list of journal entries to backend file."""
    with open(JOURNAL_PATH, "w") as f:
        json.dump(req.entries, f, indent=2)
    return {"status": "saved", "count": len(req.entries)}


@app.get("/api/kinematics")
async def get_kinematics_config():
    """Returns persistent Kinematic Calibration parameters."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "L1": 9.5, "L2": 12.0, "L3": 9.0, "L4": 14.0,
        "offsets": [0, 0, 0, 0, 0, 0],
        "gripper_closed": 85, "gripper_open": 140
    }


@app.post("/api/kinematics")
async def save_kinematics_config(req: KinematicsConfigRequest):
    """Saves updated Kinematic Calibration parameters (L1-L4, offsets, gripper angles) and syncs to ik_solver and serial_manager."""
    data = req.model_dump()
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)
    ik_solver.L1 = req.L1
    ik_solver.L2 = req.L2
    ik_solver.L3 = req.L3
    ik_solver.L4 = req.L4
    serial_manager.gripper_open = req.gripper_open
    serial_manager.gripper_closed = req.gripper_closed
    return {"status": "saved", "config": data}


@app.post("/api/ik/solve")
async def solve_ik_endpoint(req: IKSolveRequest):
    """Solves 3D Analytical Inverse Kinematics for target (X, Y, Z) in cm."""
    angles, reachable, msg = ik_solver.solve_ik(
        x=req.x, y=req.y, z=req.z,
        pitch_deg=req.pitch_deg, roll_deg=req.roll_deg,
        gripper_angle=req.gripper_angle
    )
    return {
        "status": "success" if reachable else "warning",
        "reachable": reachable,
        "angles": angles,
        "message": msg,
        "target": {"x": req.x, "y": req.y, "z": req.z, "pitch_deg": req.pitch_deg, "roll_deg": req.roll_deg}
    }


@app.post("/api/ik/move")
async def move_ik_endpoint(req: IKSolveRequest):
    """Solves 3D IK and smoothly dispatches calculated joint angles to physical servos."""
    if autonomous_manager.is_running:
        raise HTTPException(status_code=409, detail="ONNX autonomous mode is running — press Stop Autonomous Mode first.")
    angles, reachable, msg = ik_solver.solve_ik(
        x=req.x, y=req.y, z=req.z,
        pitch_deg=req.pitch_deg, roll_deg=req.roll_deg,
        gripper_angle=req.gripper_angle
    )
    success, send_msg = serial_manager.send_angles(angles)
    await broadcast_status()
    return {
        "status": "success" if (reachable and success) else "warning",
        "reachable": reachable,
        "angles": angles,
        "message": f"{msg} | Serial: {send_msg}",
        "target": {"x": req.x, "y": req.y, "z": req.z, "pitch_deg": req.pitch_deg, "roll_deg": req.roll_deg}
    }


@app.get("/api/fk")
async def get_forward_kinematics():
    """Computes and returns current 3D Cartesian coordinates (X, Y, Z in cm) of the physical arm."""
    current_angles = serial_manager.current_angles
    fk_res = ik_solver.forward_kinematics(*current_angles)
    return {
        "status": "success",
        "current_angles": current_angles,
        "cartesian": fk_res
    }


@app.get("/api/ports")
async def list_ports():
    """Lists available serial ports."""
    return {"ports": serial_manager.list_available_ports()}


@app.post("/api/connect")
async def connect_port(req: ConnectRequest):
    """Connects to specified serial port."""
    success, msg = serial_manager.connect(req.port, req.baudrate)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    await broadcast_status()
    return {"status": "connected", "message": msg}


@app.post("/api/auto-connect")
async def auto_connect_port():
    """Auto-detects and connects to Arduino."""
    success, msg = serial_manager.auto_connect()
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    await broadcast_status()
    return {"status": "connected", "message": msg}


@app.post("/api/disconnect")
async def disconnect_port():
    """Disconnects serial connection."""
    success, msg = serial_manager.disconnect()
    await broadcast_status()
    return {"status": "disconnected", "message": msg}


@app.post("/api/servos")
async def set_servo_angles(req: ServoAnglesRequest):
    """Sets 6 servo angles (0–180)."""
    if autonomous_manager.is_running:
        raise HTTPException(status_code=409, detail="ONNX autonomous mode is running — press Stop Autonomous Mode first.")
    success, msg = serial_manager.send_angles(req.angles)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    await broadcast_status()
    return {"status": "success", "angles": serial_manager.current_angles}


@app.post("/api/lock90")
async def lock_all_90():
    """Locks all servos at 90° for assembly (Decision #19)."""
    if autonomous_manager.is_running:
        raise HTTPException(status_code=409, detail="ONNX autonomous mode is running — press Stop Autonomous Mode first.")
    asyncio.create_task(serial_manager.lock_all_90(broadcast_callback=broadcast_status))
    return {"status": "success", "message": "Locking all servos at 90°"}


@app.post("/api/home")
async def move_home():
    """Moves all servos to Home Position."""
    if autonomous_manager.is_running:
        raise HTTPException(status_code=409, detail="ONNX autonomous mode is running — press Stop Autonomous Mode first.")
    asyncio.create_task(serial_manager.move_to_home(broadcast_callback=broadcast_status))
    return {"status": "success", "message": "Moving to Home Position"}


@app.post("/api/servos/test/{servo_index}")
async def test_servo(servo_index: int):
    """Performs a solo sweep test on a single servo for assembly diagnostics."""
    if autonomous_manager.is_running:
        raise HTTPException(status_code=409, detail="ONNX autonomous mode is running — press Stop Autonomous Mode first.")
    asyncio.create_task(serial_manager.test_single_servo(servo_index, broadcast_callback=broadcast_status))
    return {"status": "success", "message": f"Testing Servo {servo_index}"}


@app.post("/api/estop")
async def emergency_stop():
    """Triggers Emergency Stop."""
    success, msg = serial_manager.emergency_stop()
    await broadcast_status()
    return {"status": "estop_active", "message": msg}


@app.post("/api/estop/reset")
async def reset_estop():
    """Resets Emergency Stop state."""
    success, msg = serial_manager.reset_estop()
    await broadcast_status()
    return {"status": "estop_reset", "message": msg}


# --------------------------------------------------------------------------
# ONNX Autonomous Policy (Behaviour Cloning Pick & Place)
# --------------------------------------------------------------------------
class OnnxLoadRequest(BaseModel):
    model: str


@app.get("/api/onnx/models")
async def list_onnx_models():
    """Lists available trained ONNX policies in Dataset_30/models."""
    return {"models": autonomous_manager.list_models(),
            "model_dir": MODEL_DIR,
            "loaded": autonomous_manager.is_loaded,
            "loaded_model": autonomous_manager.model_name}


@app.post("/api/onnx/load")
async def load_onnx_model(req: OnnxLoadRequest):
    """Loads the selected ONNX policy into the inference session."""
    success, msg = autonomous_manager.load_model(req.model)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    await broadcast_status()
    return {"status": "success", "message": msg, "model": autonomous_manager.model_name}


@app.post("/api/onnx/start")
async def start_onnx_autonomous():
    """Starts the 30Hz closed-loop autonomous pick-and-place (ONNX policy)."""
    success, msg = await autonomous_manager.start(broadcast_callback=broadcast_status)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "success", "message": msg}


@app.post("/api/onnx/stop")
async def stop_onnx_autonomous():
    """Stops autonomous mode — dashboard returns to normal manual operation."""
    success, msg = await autonomous_manager.stop()
    await broadcast_status()
    return {"status": "success", "message": msg}


@app.get("/api/onnx/status")
async def get_onnx_status():
    """Snapshot of the ONNX autonomous engine (for the dashboard panel)."""
    return autonomous_manager.get_status()


@app.get("/api/onnx/info")
async def get_onnx_info():
    """Model Card — architecture, dataset, metrics and I/O contract of the policy."""
    return autonomous_manager.get_model_info()


@app.post("/api/onnx/override")
async def onnx_manual_override():
    """MANUAL OVERRIDE — instantly halts the policy, freezes the arm in place,
    and returns control to the operator (no homing motion)."""
    success, msg = await autonomous_manager.override()
    await broadcast_status()
    return {"status": "success", "message": msg}


# WebSocket Handler for Real-Time Telemetry & Slider Control

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    logger.info("New WebSocket client connected.")
    
    # Send initial status on connect
    await websocket.send_json({"type": "status", "data": serial_manager.get_status()})

    try:
        while True:
            data_str = await websocket.receive_text()
            try:
                data = json.loads(data_str)
                action_type = data.get("type")

                if action_type == "set_angles":
                    # While ONNX autonomous mode is running the policy owns the
                    # serial line — manual slider commands are ignored.
                    if autonomous_manager.is_running:
                        logger.warning("set_angles ignored: ONNX autonomous mode is running.")
                    else:
                        angles = data.get("angles", [])
                        serial_manager.send_angles(angles)
                        await broadcast_status()

                elif action_type == "move_ik":
                    if autonomous_manager.is_running:
                        logger.warning("move_ik ignored: ONNX autonomous mode is running.")
                    else:
                        x = float(data.get("x", 0.0))
                        y = float(data.get("y", 20.0))
                        z = float(data.get("z", 5.0))
                        pitch_deg = float(data.get("pitch_deg", -30.0))
                        roll_deg = float(data.get("roll_deg", 90.0))
                        gripper_angle = int(data.get("gripper_angle", 140))
                        angles, reachable, msg = ik_solver.solve_ik(x, y, z, pitch_deg, roll_deg, gripper_angle)
                        serial_manager.send_angles(angles)
                        await broadcast_status()

                elif action_type == "lock90":
                    asyncio.create_task(serial_manager.lock_all_90(broadcast_callback=broadcast_status))

                elif action_type == "home":
                    asyncio.create_task(serial_manager.move_to_home(broadcast_callback=broadcast_status))

                elif action_type == "sweep":
                    asyncio.create_task(serial_manager.run_joint_sweep_test(broadcast_callback=broadcast_status))

                elif action_type == "test_servo":
                    servo_index = int(data.get("index", 0))
                    asyncio.create_task(serial_manager.test_single_servo(servo_index, broadcast_callback=broadcast_status))

                elif action_type == "estop":
                    serial_manager.emergency_stop()
                    await broadcast_status()

                elif action_type == "reset_estop":
                    serial_manager.reset_estop()
                    await broadcast_status()

            except json.JSONDecodeError:
                logger.warning("Received non-JSON WebSocket message.")

    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info("WebSocket client disconnected.")


async def broadcast_status():
    """Broadcasts current status to all connected WebSocket clients."""
    if not active_connections:
        return
    status_data = {"type": "status", "data": serial_manager.get_status()}
    for conn in list(active_connections):
        try:
            await conn.send_json(status_data)
        except Exception:
            if conn in active_connections:
                active_connections.remove(conn)


# Mount static frontend files
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    # Use port 8050 to avoid conflicts with macOS AirPlay Receiver (which uses port 8000)
    uvicorn.run("main:app", host="0.0.0.0", port=8050, reload=True)
