@echo off
:: ==============================================================================
::  LEETCODE-NVIDIA-AUTO PLAYWRIGHT BOT RUNNER (Windows)
:: ==============================================================================

echo ============================================
echo   LeetCode-NVIDIA-AUTO Playwright Bot
echo   Preparing environment... (Windows)
echo ============================================

:: Check for backend virtual environment
if not exist backend\venv (
    echo [ERROR] Python virtual environment 'backend/venv' not found.
    echo Please run 'start_backend.bat' first to initialize the environment!
    echo.
    pause
    exit /b 1
)

echo Activating virtual environment...
call backend\venv\Scripts\activate

echo.
echo Verifying Playwright system installation...
playwright install chromium

echo.
echo Starting Playwright auto solver bot...
echo ============================================
cd playwright_bot
python auto_solver.py
pause
