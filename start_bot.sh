#!/bin/bash
# ==============================================================================
#  LEETCODE-NVIDIA-AUTO PLAYWRIGHT BOT RUNNER (macOS & Linux)
# ==============================================================================

echo "============================================"
echo "  LeetCode-NVIDIA-AUTO Playwright Bot"
echo "  Preparing environment... (macOS/Linux)"
echo "============================================"

# Navigate to workspace root
cd "$(dirname "$0")" || exit 1

# Check for backend virtual environment
if [ ! -d "backend/venv" ]; then
    echo "[ERROR] Python virtual environment 'backend/venv' not found."
    echo "Please run './start_backend.sh' first to initialize the environment!"
    exit 1
fi

echo "Activating virtual environment..."
source backend/venv/bin/activate || { echo "Failed to activate virtual environment."; exit 1; }

echo ""
echo "Verifying Playwright system installation..."
python3 -m playwright install chromium || { echo "Failed to install Playwright browser binary."; exit 1; }

echo ""
echo "Starting Playwright auto solver bot..."
echo "============================================"
cd playwright_bot || exit 1
python3 auto_solver.py
