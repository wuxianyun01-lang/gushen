# 股神顾问 一键恢复脚本
# 新电脑 clone 仓库后，双击或右键"使用 PowerShell 运行"本脚本即可完成恢复。
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "项目目录: $root" -ForegroundColor Cyan

# ============ 1/3 安装 Codex skills ============
Write-Host "`n[1/3] 安装 Codex skills ..." -ForegroundColor Yellow
$skillSrc = Join-Path $root 'skills'
$skillDst = Join-Path $env:USERPROFILE '.codex\skills'
if (Test-Path $skillSrc) {
  New-Item -ItemType Directory -Force -Path $skillDst | Out-Null
  foreach ($d in Get-ChildItem $skillSrc -Directory) {
    $target = Join-Path $skillDst $d.Name
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Copy-Item $d.FullName $target -Recurse -Force
    Write-Host "  已安装 skill: $($d.Name)"
  }
}

# ============ 2/3 安装 TradingAgents-CN ============
Write-Host "`n[2/3] 安装 TradingAgents-CN（多智能体，需联网，约10-20分钟）..." -ForegroundColor Yellow
$ta = Join-Path $root 'TradingAgents-CN'
if (-not (Test-Path $ta)) {
  Write-Host "  clone TradingAgents-CN ..."
  git clone https://github.com/hsliuping/TradingAgents-CN.git $ta
}
$py = Join-Path $ta '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
  Write-Host "  创建虚拟环境并安装依赖（耗时较长）..."
  $pyBase = Get-Command python -ErrorAction SilentlyContinue
  if ($pyBase) { python -m venv (Join-Path $ta '.venv') } else { throw "未找到 python，请先安装 Python 3.11+" }
  & $py -m pip install --upgrade pip
  & $py -m pip install -e $ta
  Write-Host "  TradingAgents-CN 依赖安装完成"
} else {
  Write-Host "  TradingAgents-CN 已存在，跳过安装"
}
# 复制 .env 模板（DeepSeek key 需用户自填）
$envTpl = Join-Path $ta '.env.example'
$envFile = Join-Path $ta '.env'
if ((Test-Path $envTpl) -and -not (Test-Path $envFile)) {
  Copy-Item $envTpl $envFile
  Write-Host "  已生成 $envFile，请填入 DEEPSEEK_API_KEY"
}

# ============ 3/3 恢复分析配置 ============
Write-Host "`n[3/3] 恢复分析配置 ..." -ForegroundColor Yellow
$cfg = Join-Path $root 'monitor\config.json'
if (-not (Test-Path $cfg)) {
  Copy-Item (Join-Path $root 'monitor\config.example.json') $cfg
  Write-Host "  已生成 config.json，请编辑填入持仓和 QQ 邮箱授权码" -ForegroundColor Green
} else {
  Write-Host "  config.json 已存在，跳过"
}

Write-Host "`n✅ 恢复完成！" -ForegroundColor Green
Write-Host "后续使用：在 Codex 里说"用股神顾问分析 XX"即可。"
