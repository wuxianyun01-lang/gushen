@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\stop_monitor.ps1"
timeout /t 2 /nobreak >nul
call ".\start_monitor.bat"
