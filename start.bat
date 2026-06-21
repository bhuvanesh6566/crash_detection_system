@echo off
title AI Accident Detection System

echo.
echo  ============================================
echo   AI Accident Detection System - Starting...
echo  ============================================
echo.

:: ── Check Python ──────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b
)

:: ── Check Node ────────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js
    pause
    exit /b
)

:: ── Install Python dependencies if needed ─────
echo [1/3] Checking Python dependencies...
pip install -r "%~dp0backend\requirements.txt" -q

:: ── Install Node dependencies if needed ───────
echo [2/3] Checking Node dependencies...
if not exist "%~dp0frontend\node_modules" (
    echo       Installing npm packages, please wait...
    cd /d "%~dp0frontend"
    npm install --silent
)

echo [3/3] Launching servers...
echo.

:: ── Start Flask backend in new window ─────────
start "Flask Backend - Port 5000" cmd /k "cd /d "%~dp0backend" && echo  Starting Flask Backend... && python app.py"

:: wait 3 seconds for Flask to boot
timeout /t 3 /nobreak >nul

:: ── Start React frontend in new window ────────
start "React Frontend - Port 3000" cmd /k "cd /d "%~dp0frontend" && echo  Starting React Frontend... && npm start"

echo.
echo  ✅ Both servers are starting in separate windows:
echo.
echo     Backend  →  http://localhost:5000
echo     Frontend →  http://localhost:3000
echo.
echo  The browser will open automatically at http://localhost:3000
echo  Close the server windows to stop the system.
echo.
pause
