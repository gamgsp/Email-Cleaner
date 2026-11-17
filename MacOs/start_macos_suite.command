#!/bin/bash
cd "$(dirname "$0")"

echo "========================================"
echo "    📧 EMAIL SUITE FOR MACOS (APPLE MAIL)"
echo "========================================"
echo "1) Launch MailSweep (Cleaner - Port 7890)"
echo "2) Launch UnsubBot (Auto-Unsubscriber - Port 7891)"
echo "3) Launch Both"
echo "========================================"
read -p "Enter choice [1, 2, or 3]: " choice

if [ "$choice" == "1" ]; then
    open "http://localhost:7890"
    python3 MailSweep/backend.py
elif [ "$choice" == "2" ]; then
    open "http://localhost:7891"
    python3 UnsubBot/backend.py
elif [ "$choice" == "3" ]; then
    open "http://localhost:7890"
    python3 MailSweep/backend.py &
    open "http://localhost:7891"
    python3 UnsubBot/backend.py
else
    echo "Invalid choice. Exiting."
fi
