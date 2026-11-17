@echo off
cd /d "%~dp0"
title UnsubBot Automated Unsubscriber

:: 1. Check Python
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py"
if not "%PY_CMD%"=="" goto :py_found
where python >nul 2>nul && set "PY_CMD=python"
if not "%PY_CMD%"=="" goto :py_found

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY_CMD="%LOCALAPPDATA%\Programs\Python\Python311\python.exe""
    goto :py_found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY_CMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
    goto :py_found
)

echo [!] Python is not installed. Installing Python 3...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $installer = Join-Path $env:TEMP 'python_installer.exe'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile $installer; Start-Process $installer -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1' -Wait; Remove-Item $installer -Force -ErrorAction SilentlyContinue"

where py >nul 2>nul && set "PY_CMD=py"
if not "%PY_CMD%"=="" goto :py_found
where python >nul 2>nul && set "PY_CMD=python"
if not "%PY_CMD%"=="" goto :py_found

:py_found
if "%PY_CMD%"=="" (
    echo [!] Error: Python could not be installed automatically.
    echo Please install Python manually from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 2. Setup venv
if exist "..\venv\Scripts\activate.bat" (
    call ..\venv\Scripts\activate.bat
    set "RUN_PY=python"
    goto :venv_ready
)

if not exist "venv\Scripts\activate.bat" (
    echo [*] Initializing virtual environment...
    %PY_CMD% -m venv venv
)

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    set "RUN_PY=python"
) else (
    set "RUN_PY=%PY_CMD%"
)

:venv_ready
:: 3. Dependencies
if exist "requirements.txt" (
    %RUN_PY% -m pip install -q -r requirements.txt
) else if exist "..\requirements.txt" (
    %RUN_PY% -m pip install -q -r ..\requirements.txt
)

echo Starting UnsubBot on http://localhost:7891 ...
start http://localhost:7891
%RUN_PY% backend.py
pause
