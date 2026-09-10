#!/bin/bash
# ==============================================================================
# DASHBOARD FULL STACK STARTUP SCRIPT (macOS / Linux / Git-Bash)
# ==============================================================================
# Project:  Vision-Based Autonomous Robotic Arm
# Location: <repo>/start_dashboard.sh
#
# PURPOSE:
#   ONE-COMBINED launcher that starts EVERYTHING the dashboard needs at once:
#     1. Python dependency check (installs requirements.txt if missing)
#     2. FastAPI backend server  ->  http://localhost:8050  (serves dashboard UI,
#        robot API, WebSocket, camera feeds, and AUTO-LOADS pickyv1.onnx)
#     3. Local Netron model-graph viewer  ->  http://localhost:8088
#        (lazily started on demand by the backend via /api/onnx/graph/start,
#         so no separate step is needed — it boots the first time you click
#         "Model Graph" and stays available afterwards)
#     4. Opens the dashboard in your default browser
#
# WHAT RUNS AT ONCE:
#   - Backend (uvicorn, port 8050)  [foreground; Ctrl+C stops everything]
#   - Netron viewer (port 8088)     [child of the backend, on-demand + persistent]
#   - Dashboard UI                  [your browser]
#
# USAGE:
#   ./start_dashboard.sh            (or double-click in Finder / Git-Bash)
# ==============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
BACKEND_DIR="$SCRIPT_DIR/dashboard/backend"
VENV_DIR="$BACKEND_DIR/venv"

echo "================================================================"
echo "  Vision-Based Autonomous Robotic Arm — FULL STACK STARTUP"
echo "================================================================"

# --------------------------------------------------------------------------
# 1. Python environment (venv if present, else system python3)
# --------------------------------------------------------------------------
if [ -d "$VENV_DIR" ]; then
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    echo "[OK] Activated Python virtual environment."
else
    echo "[INFO] No venv found — using system python3."
fi

PYTHON="python3"
command -v $PYTHON >/dev/null 2>&1 || PYTHON="python"

# --------------------------------------------------------------------------
# 2. Dependencies (only installs what is missing; netron included)
# --------------------------------------------------------------------------
echo "[..] Checking Python dependencies (fastapi, uvicorn, pyserial, opencv, onnxruntime, netron)..."
$PYTHON - <<'EOF'
import importlib.util as u
missing = [m for m in ("fastapi", "uvicorn", "serial", "cv2", "numpy", "onnxruntime", "netron")
           if u.find_spec(m) is None]
if missing:
    print("[..] Installing missing packages:", ", ".join(missing))
    import sys, subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
else:
    print("[OK] All dependencies present.")
EOF

# --------------------------------------------------------------------------
# 3. Sanity: confirm the trained model exists (auto-loaded at backend startup)
# --------------------------------------------------------------------------
MODEL_FILE="$SCRIPT_DIR/Dataset_30/models/pickyv1.onnx"
if [ -f "$MODEL_FILE" ]; then
    echo "[OK] Policy model found: Dataset_30/models/pickyv1.onnx (auto-loads at startup)."
else
    echo "[WARN] pickyv1.onnx not found — the ONNX panel will list whatever is in Dataset_30/models."
fi

# --------------------------------------------------------------------------
# 4. Launch backend (port 8050) + on-demand Netron viewer (port 8088)
# --------------------------------------------------------------------------
cd "$BACKEND_DIR" || exit 1

echo ""
echo "[OK] Starting FULL STACK:"
echo "     - Dashboard + robot API : http://localhost:8050"
echo "     - Netron model graph    : http://localhost:8088 (starts on demand"
echo "       the first time you click 'Model Graph', then stays available)"
echo "     - Policy                : pickyv1.onnx (auto-loaded)"
echo ""
echo "Opening the dashboard in your browser..."
echo "Press Ctrl+C in this terminal to stop everything."
echo ""

# Open the dashboard in the default browser (background; failures are harmless)
(
  sleep 3
  if command -v open >/dev/null 2>&1; then open "http://localhost:8050" 2>/dev/null
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "http://localhost:8050" 2>/dev/null
  elif command -v start >/dev/null 2>&1; then start "http://localhost:8050" 2>/dev/null
  fi
) &

# Foreground: run the backend. On startup it auto-loads the ONNX policy; the
# local Netron viewer (8088) boots lazily from /api/onnx/graph/start when the
# Model Graph button is clicked, so ONE script truly runs everything at once.
exec $PYTHON main.py

