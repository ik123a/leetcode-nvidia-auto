#!/bin/bash
# ==============================================================================
#  LEETCODE-NVIDIA-AUTO BACKEND SERVER RUNNER (macOS & Linux)
# ==============================================================================

echo "============================================"
echo "  LeetCode-NVIDIA-AUTO Backend Server"
echo "  Preparing environment... (macOS/Linux)"
echo "============================================"

# Navigate to backend
cd "$(dirname "$0")/backend" || exit 1

# Check for Python virtual environment
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv || { echo "Failed to create venv. Is python3-venv installed?"; exit 1; }
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate || { echo "Failed to activate virtual environment."; exit 1; }

# Install required dependencies
echo "Installing/verifying python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt || { echo "Failed to install dependencies."; exit 1; }

# Check for .env file
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "Creating .env template. Please fill in your API keys in backend/.env!"
        cp .env.example .env
    else
        echo "WARNING: .env file and .env.example not found! Please create backend/.env with your API keys."
    fi
fi

echo ""
echo "Starting backend Flask server on port 5050..."
echo "============================================"
python main.py
