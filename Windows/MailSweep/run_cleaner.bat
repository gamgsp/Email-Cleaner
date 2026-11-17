@echo off
cd /d "%~dp0"
set "PY_CMD=python"
where py >nul 2>nul && set "PY_CMD=py"
if "%PY_CMD%"=="python" (
    where python >nul 2>nul || (
        if exist "%LOCALAPPDATA%\Programs\Python\Python315\python.exe" (
            set "PY_CMD="%LOCALAPPDATA%\Programs\Python\Python315\python.exe""
        )
    )
)
start http://localhost:7890
%PY_CMD% backend.py
pause
