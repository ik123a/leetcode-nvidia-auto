@echo off
echo ============================================
echo   LeetCode-NVIDIA-AUTO Backend Server
echo ============================================
cd backend
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
echo Activating virtual environment...
call venv\Scripts\activate
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting backend server on port 5050...
echo ============================================
python main.py
pause
