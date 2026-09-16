@echo off
cd /d "%~dp0.."
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
start "" ".\TradingAgents-CN\.venv\Scripts\pythonw.exe" -m monitor.main
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8765"

