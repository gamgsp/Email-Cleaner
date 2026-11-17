@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Email Suite Control Center (Windows)

echo ========================================================
echo    EMAIL SUITE CONTROL CENTER (THUNDERBIRD ^& OUTLOOK)
echo ========================================================
echo.

:: 1. Check Python
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py"
if "%PY_CMD%"=="" (
    where python >nul 2>nul && set "PY_CMD=python"
)
if "%PY_CMD%"=="" (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PY_CMD="%LOCALAPPDATA%\Programs\Python\Python311\python.exe""
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PY_CMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
    )
)

if "%PY_CMD%"=="" (
    echo [!] Python is not installed or not found on PATH.
    echo [*] Downloading and installing Python 3 for Windows...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Write-Host 'Downloading Python Installer...'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe', '$env:TEMP\python_installer.exe'); Start-Process '$env:TEMP\python_installer.exe' -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1' -Wait; Remove-Item '$env:TEMP\python_installer.exe' -ErrorAction SilentlyContinue"
    where py >nul 2>nul && set "PY_CMD=py"
    if "%PY_CMD%"=="" (
        where python >nul 2>nul && set "PY_CMD=python"
    )
)

:: 2. Setup Virtual Environment (venv)
if not exist "venv\Scripts\activate.bat" (
    echo [*] Creating local Python virtual environment (venv)...
    %PY_CMD% -m venv venv
)

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    set "RUN_PY=python"
) else (
    set "RUN_PY=%PY_CMD%"
)

:: 3. Install Required Dependencies
echo [*] Checking and installing dependencies...
%RUN_PY% -m pip install --quiet --upgrade pip 2>nul
if exist "Windows\requirements.txt" (
    %RUN_PY% -m pip install -r Windows\requirements.txt
) else if exist "requirements.txt" (
    %RUN_PY% -m pip install -r requirements.txt
)

echo.
echo ========================================================
echo 1) Launch MailSweep (Email Cleaner - Port 7890)
echo 2) Launch UnsubBot (Auto-Unsubscriber - Port 7891)
echo 3) Launch Both Applications
echo ========================================================
set /p choice="Enter choice [1, 2, or 3]: "

if "%choice%"=="1" (
    start http://localhost:7890
    %RUN_PY% Windows\MailSweep\backend.py
    pause
) else if "%choice%"=="2" (
    start http://localhost:7891
    %RUN_PY% Windows\UnsubBot\backend.py
    pause
) else if "%choice%"=="3" (
    start "MailSweep Cleaner (Port 7890)" cmd /k "cd /d "%~dp0" & if exist "venv\Scripts\activate.bat" call venv\Scripts\activate.bat & start http://localhost:7890 & python Windows\MailSweep\backend.py"
    start "UnsubBot Unsubscriber (Port 7891)" cmd /k "cd /d "%~dp0" & if exist "venv\Scripts\activate.bat" call venv\Scripts\activate.bat & start http://localhost:7891 & python Windows\UnsubBot\backend.py"
) else (
    echo Invalid choice. Exiting.
    pause
)
