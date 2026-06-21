@echo off
title Stop Accident Detection System

echo.
echo  ============================================
echo   Stopping AI Accident Detection System...
echo  ============================================
echo.

:: Kill Flask on port 5000
echo [1/2] Stopping Flask backend (port 5000)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5000"') do (
    taskkill /PID %%a /F >nul 2>&1
)

:: Kill React on port 3000
echo [2/2] Stopping React frontend (port 3000)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000"') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo.
echo  ✅ All servers stopped.
echo.
pause
