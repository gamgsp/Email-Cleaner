#!/bin/bash
cd "$(dirname "$0")"

echo "========================================================"
echo "    📧 EMAIL SUITE CONTROL CENTER (macOS)"
echo "========================================================"
echo ""

# 1. Check Python
PY_CMD=""
if command -v python3 &>/dev/null; then
    PY_CMD="python3"
elif command -v python &>/dev/null; then
    PY_CMD="python"
fi

if [ -z "$PY_CMD" ]; then
    echo "[!] Python 3 is not installed."
    echo "[*] Attempting to install Python via Homebrew or Xcode Tools..."
    if command -v brew &>/dev/null; then
        brew install python
        PY_CMD="python3"
    else
        echo "[*] Triggering Apple Command Line Tools installer..."
        xcode-select --install
        echo "Please complete the Apple installation prompt and re-run this script."
        exit 1
    fi
fi

# 2. Virtual Environment Setup
if [ ! -d "venv" ]; then
    echo "[*] Creating local Python virtual environment (venv)..."
    $PY_CMD -m venv venv
fi

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    RUN_PY="python"
else
    RUN_PY="$PY_CMD"
fi

# 3. Dependencies
echo "[*] Checking and installing dependencies..."
$RUN_PY -m pip install --quiet --upgrade pip 2>/dev/null
if [ -f "requirements.txt" ]; then
    $RUN_PY -m pip install -r requirements.txt
fi

echo ""
echo "========================================================"
echo "1) Launch MailSweep (Cleaner - Port 7890)"
echo "2) Launch UnsubBot (Auto-Unsubscriber - Port 7891)"
echo "3) Launch Both Applications"
echo "========================================================"
read -p "Enter choice [1, 2, or 3]: " choice

if [ "$choice" == "1" ]; then
    open "http://localhost:7890"
    $RUN_PY MailSweep/backend.py
elif [ "$choice" == "2" ]; then
    open "http://localhost:7891"
    $RUN_PY UnsubBot/backend.py
elif [ "$choice" == "3" ]; then
    open "http://localhost:7890"
    $RUN_PY MailSweep/backend.py &
    open "http://localhost:7891"
    $RUN_PY UnsubBot/backend.py
else
    echo "Invalid choice. Exiting."
fi
