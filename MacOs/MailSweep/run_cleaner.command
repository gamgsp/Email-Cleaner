#!/bin/bash
cd "$(dirname "$0")"
echo "Starting Email Cleaner..."
open "http://localhost:7890"
python3 backend.py
