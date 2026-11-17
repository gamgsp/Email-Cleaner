@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Email Suite Control Center (Windows - Outlook & IMAP)

:: Auto-detect Python launcher or executable
set "PY_CMD=python"
where py >nul 2>nul && set "PY_CMD=py"
if "%PY_CMD%"=="python" (
    where python >nul 2>nul || (
        if exist "%LOCALAPPDATA%\Programs\Python\Python315\python.exe" (
            set "PY_CMD="%LOCALAPPDATA%\Programs\Python\Python315\python.exe""
        )
    )
)

echo ===================================================
echo    EMAIL SUITE CONTROL CENTER (OUTLOOK & IMAP)
echo ===================================================
echo Using Python Command: %PY_CMD%
echo.
echo 1) Launch MailSweep (Cleaner - Port 7890)
echo 2) Launch UnsubBot (Auto-Unsubscriber - Port 7891)
echo 3) Launch Both Applications
echo ===================================================
set /p choice="Enter choice [1, 2, or 3]: "

if "%choice%"=="1" (
    start http://localhost:7890
    %PY_CMD% MailSweep\backend.py
    pause
) else if "%choice%"=="2" (
    start http://localhost:7891
    %PY_CMD% UnsubBot\backend.py
    pause
) else if "%choice%"=="3" (
    start "MailSweep Cleaner (Port 7890)" cmd /k "start http://localhost:7890 & %PY_CMD% MailSweep\backend.py"
    start "UnsubBot Unsubscriber (Port 7891)" cmd /k "start http://localhost:7891 & %PY_CMD% UnsubBot\backend.py"
) else (
    echo Invalid choice. Exiting.
    pause
)
