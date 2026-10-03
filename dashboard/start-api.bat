@echo off
REM Real-Time Police Health API Startup Script for Windows

echo.
echo ============================================================================
echo  Police Health API - Real-Time CSV Data Integration
echo ============================================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.8+ and add it to PATH
    pause
    exit /b 1
)

echo [1/3] Installing/Updating required packages...
pip install -q fastapi uvicorn requests python-dotenv

if %errorlevel% neq 0 (
    echo ERROR: Failed to install packages
    pause
    exit /b 1
)

echo [2/3] Checking CSV data...
if exist "..\police-personnel-data-realtime" (
    echo   ✓ CSV directory found: ..\police-personnel-data-realtime
) else (
    echo   ⚠ WARNING: CSV directory not found at ..\police-personnel-data-realtime
    echo   (The API will fall back to random data)
)

echo.
echo [3/3] Starting API on http://localhost:8000/docs
echo.
echo The API will:
echo   - Load CSV files from police-personnel-data-realtime directory
echo   - Provide real-time data via /api/telemetry/current and /api/telemetry/history
echo   - Update every API call with the next CSV row
echo.
echo Press CTRL+C to stop the server
echo.

REM Start the API with auto-reload
uvicorn police_health_api:app --reload --port 8000

pause
