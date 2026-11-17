#!/bin/bash
cd "$(dirname "$0")"

# 1. Check Python
PY_CMD=""
if command -v python3 &>/dev/null; then
    PY_CMD="python3"
elif command -v python &>/dev/null; then
    PY_CMD="python"
fi

if [ -z "$PY_CMD" ]; then
    echo "[!] Python 3 is not installed. Please install Python via Homebrew: brew install python"
    exit 1
fi

# 2. Virtual Environment Setup
if [ ! -d "../venv" ] && [ ! -d "venv" ]; then
    $PY_CMD -m venv venv
fi

if [ -f "../venv/bin/activate" ]; then
    source ../venv/bin/activate
    RUN_PY="python"
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    RUN_PY="python"
else
    RUN_PY="$PY_CMD"
fi

# 3. Dependencies
if [ -f "requirements.txt" ]; then
    $RUN_PY -m pip install -q -r requirements.txt
elif [ -f "../requirements.txt" ]; then
    $RUN_PY -m pip install -q -r ../requirements.txt
fi

echo "Starting UnsubBot Unsubscriber..."
open "http://localhost:7891"
$RUN_PY backend.py
