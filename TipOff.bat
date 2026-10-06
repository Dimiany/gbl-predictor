@echo off
rem Double-click launcher: updates the data if stale, then opens the dashboard
rem with a working Refresh button. Keep the window open while using the page.
chcp 65001 >nul
title TipOff
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python from python.org and try again.
  pause
  exit /b 1
)

python -u scripts\serve.py
if errorlevel 1 pause
