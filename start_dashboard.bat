@echo off
REM ==============================================================================
REM DASHBOARD FULL STACK STARTUP SCRIPT (Windows)
REM ==============================================================================
REM Project:  Vision-Based Autonomous Robotic Arm
REM Location: <repo>\start_dashboard.bat
REM
REM PURPOSE:
REM   ONE-COMBINED launcher that starts EVERYTHING the dashboard needs at once:
REM     1. Python dependency check (installs requirements.txt if missing)
REM     2. FastAPI backend server  ->  http://localhost:8050  (dashboard UI,
REM        robot API, WebSocket, camera feeds, AUTO-LOADS pickyv1.onnx)
REM     3. Local Netron model-graph viewer  ->  http://localhost:8088
REM        (boots lazily the first time you click "Model Graph", then stays up)
REM     4. Opens the dashboard in your default browser
REM
REM USAGE: double-click this file, or run:  start_dashboard.bat
REM ==============================================================================

title Vision-Based Autonomous Robotic Arm - Full Stack

echo ================================================================
echo   Vision-Based Autonomous Robotic Arm - FULL STACK STARTUP
echo ================================================================

set "SCRIPT_DIR=%~dp0"
set "BACKEND_DIR=%SCRIPT_DIR%dashboard\backend"

REM --------------------------------------------------------------------------
REM 1. Find Python (prefer venv if present)
REM --------------------------------------------------------------------------
if exist "%BACKEND_DIR%venv\Scripts\python.exe" (
    set "PYTHON=%BACKEND_DIR%venv\Scripts\python.exe"
    echo [OK] Using backend venv Python.
) else (
    set "PYTHON=python"
    echo [INFO] No venv found - using system Python.
)

REM --------------------------------------------------------------------------
REM 2. Dependencies (only installs what is missing; netron included)
REM --------------------------------------------------------------------------
echo [..] Checking Python dependencies...
%PYTHON% -c "import importlib.util as u, sys; missing=[m for m in ('fastapi','uvicorn','serial','cv2','numpy','onnxruntime','netron') if u.find_spec(m) is None]; print('[..] Installing missing: '+', '.join(missing)) if missing else print('[OK] All dependencies present.'); sys.exit(1 if missing else 0)"
if errorlevel 1 (
    %PYTHON% -m pip install -r "%BACKEND_DIR%requirements.txt"
    if errorlevel 1 (
        echo [ERROR] Dependency install failed - see messages above.
        pause
        exit /b 1
    )
)

REM --------------------------------------------------------------------------
REM 3. Sanity: confirm the trained model exists (auto-loads at backend startup)
REM --------------------------------------------------------------------------
if exist "%SCRIPT_DIR%Dataset_30\models\pickyv1.onnx" (
    echo [OK] Policy model found: Dataset_30\models\pickyv1.onnx ^(auto-loads at startup^).
) else (
    echo [WARN] pickyv1.onnx not found - the ONNX panel will list whatever is in Dataset_30\models.
)

REM --------------------------------------------------------------------------
REM 4. Launch backend (port 8050) + on-demand Netron viewer (port 8088)
REM --------------------------------------------------------------------------
echo.
echo [OK] Starting FULL STACK:
echo      - Dashboard + robot API : http://localhost:8050
echo      - Netron model graph    : http://localhost:8088 ^(starts on demand the
echo        first time you click 'Model Graph', then stays available^)
echo      - Policy                : pickyv1.onnx ^(auto-loaded^)
echo.
echo Opening the dashboard in your browser...
echo Close this window or press Ctrl+C to stop everything.
echo.

REM Open the dashboard in the default browser once the server is up
start "" /min cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8050"

REM Foreground: run the backend (Ctrl+C or closing this window stops all).
cd /d "%BACKEND_DIR%"
%PYTHON% main.py
pause
