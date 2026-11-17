@echo off
title Stop Email Suite Servers
echo ========================================================
echo   Stopping MailSweep (7890) and UnsubBot (7891)...
echo ========================================================

set COUNT=0

:: Terminate process listening on 7890 (MailSweep)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :7890 ^| findstr LISTENING') do (
    echo Stopping process PID %%a on port 7890...
    taskkill /F /PID %%a >nul 2>&1
    set /a COUNT+=1
)

:: Terminate process listening on 7891 (UnsubBot)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :7891 ^| findstr LISTENING') do (
    echo Stopping process PID %%a on port 7891...
    taskkill /F /PID %%a >nul 2>&1
    set /a COUNT+=1
)

echo.
echo Servers successfully stopped.
echo You can close this window now.
pause
