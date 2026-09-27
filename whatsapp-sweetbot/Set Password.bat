@echo off
title Sweetbot - set the control panel password
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is not installed. Download the LTS version from https://nodejs.org, install it, then try again.
  pause
  exit /b 1
)

node set-password.js
echo.
pause
