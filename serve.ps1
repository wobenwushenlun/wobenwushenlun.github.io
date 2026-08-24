$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$environmentPath = Join-Path $projectRoot ".conda"

if (-not (Test-Path -LiteralPath $environmentPath)) {
  throw "Conda 环境不存在。请先按照 README.md 的说明创建 .conda 环境。"
}

Set-Location -LiteralPath $projectRoot
conda run --prefix $environmentPath python build.py --serve --host 127.0.0.1 --port 4000
