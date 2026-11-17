@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title UnsubBot Automated Unsubscriber

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
    echo [!] Python is not installed. Installing Python 3...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe', '$env:TEMP\python_installer.exe'); Start-Process '$env:TEMP\python_installer.exe' -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1' -Wait; Remove-Item '$env:TEMP\python_installer.exe' -ErrorAction SilentlyContinue"
    where py >nul 2>nul && set "PY_CMD=py"
    if "%PY_CMD%"=="" where python >nul 2>nul && set "PY_CMD=python"
)

:: 2. Setup venv
if not exist "..\venv\Scripts\activate.bat" (
    if not exist "venv\Scripts\activate.bat" (
        echo [*] Initializing virtual environment...
        %PY_CMD% -m venv venv
    )
)

if exist "..\venv\Scripts\activate.bat" (
    call ..\venv\Scripts\activate.bat
    set "RUN_PY=python"
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    set "RUN_PY=python"
) else (
    set "RUN_PY=%PY_CMD%"
)

:: 3. Dependencies
if exist "requirements.txt" (
    %RUN_PY% -m pip install -q -r requirements.txt
) else if exist "..\requirements.txt" (
    %RUN_PY% -m pip install -q -r ..\requirements.txt
)

start http://localhost:7891
%RUN_PY% backend.py
pause
