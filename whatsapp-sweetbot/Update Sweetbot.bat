@echo off
title Update Sweetbot
cd /d "%~dp0"
echo Getting the latest version...
git pull
if errorlevel 1 (
  echo.
  echo Update failed - see the message above.
  pause
  exit /b 1
)
call npm install --no-audit --no-fund
echo.
echo Updated. If Sweetbot is running, click "Stop bot" in the control panel and start it again.
pause
