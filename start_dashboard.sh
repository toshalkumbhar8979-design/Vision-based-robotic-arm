#!/bin/bash
# ==============================================================================
# DASHBOARD STARTUP SCRIPT
# ==============================================================================
# Project:  Vision-Based Autonomous Robotic Arm
# Location: /Users/sohambhavsar/Desktop/Autonomoous arm/start_dashboard.sh
# 
# PURPOSE:
#   One-click startup script for the Web Dashboard.
#   Navigates to backend, activates virtual environment (venv), and launches main.py.
# 
# USAGE:
#   1. Open Terminal and run:  ./start_dashboard.sh
#   OR
#   2. Double-click `start_dashboard.sh` in macOS Finder.
# ==============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
BACKEND_DIR="$SCRIPT_DIR/dashboard/backend"

echo "========================================================"
echo "  Starting Robotic Arm Control Dashboard (Port 8050)   "
echo "========================================================"

if [ ! -d "$BACKEND_DIR/venv" ]; then
    echo "[Error] Virtual environment not found. Please setup backend venv first."
    exit 1
fi

cd "$BACKEND_DIR"
source venv/bin/activate

echo "[OK] Activated Python Virtual Environment."
echo "[OK] Launching Dashboard Server at http://localhost:8050"
echo "Press Ctrl+C in this terminal to stop the server."
echo ""

python3 main.py
