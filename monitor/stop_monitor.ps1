$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $root
$python = Join-Path $root 'TradingAgents-CN\.venv\Scripts\python.exe'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
& $python -m monitor.daily_summary
$targets = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*monitor.main*' }
foreach ($proc in $targets) {
  Stop-Process -Id $proc.ProcessId -Force
}
