@echo off
title Sweetbot - keep this window open (minimise it)
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is not installed. Download the LTS version from https://nodejs.org, install it, then try again.
  start "" https://nodejs.org
  pause
  exit /b 1
)

if not exist node_modules (
  echo First run: installing, this takes a couple of minutes...
  call npm install --no-audit --no-fund
)

echo Starting Sweetbot. The control panel opens in your browser.
echo Keep this window open - minimise it. Closing it stops the bot.

:run
node index.js %*
if errorlevel 1 (
  echo.
  echo Sweetbot stopped unexpectedly - starting it again in 10 seconds...
  timeout /t 10 /nobreak >nul
  goto run
)

echo.
echo Sweetbot has stopped.
if "%~1"=="" pause
