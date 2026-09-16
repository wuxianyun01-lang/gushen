$ErrorActionPreference = 'SilentlyContinue'
$p = Get-NetTCPConnection -LocalPort 8765 -State Listen
if (-not $p) {
  $root = Split-Path -Parent $MyInvocation.MyCommand.Path
  $root = Split-Path -Parent $root
  $env:PYTHONUTF8 = '1'
  $env:PYTHONIOENCODING = 'utf-8'
  Start-Process -FilePath (Join-Path $root 'TradingAgents-CN\.venv\Scripts\pythonw.exe') -ArgumentList '-m','monitor.main' -WorkingDirectory $root -WindowStyle Hidden
}

