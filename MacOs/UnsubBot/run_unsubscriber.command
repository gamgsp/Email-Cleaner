#!/bin/bash
cd "$(dirname "$0")"
echo "Starting Email Auto-Unsubscriber..."
open "http://localhost:7891"
python3 backend.py
