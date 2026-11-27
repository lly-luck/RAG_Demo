# 便携包构建入口（PowerShell 包装器）
# 用法：
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 --skip-kb
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$BuildArgs
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = $env:EDU_RAG_PYTHON
if (-not $Py -and $env:CONDA_PREFIX) {
    $Py = Join-Path $env:CONDA_PREFIX "python.exe"
}
if (-not $Py) {
    throw "请先 conda activate edu_rag，或设置环境变量 EDU_RAG_PYTHON 指向 edu_rag 的 python.exe。"
}
if (-not (Test-Path $Py)) {
    throw "未找到 edu_rag Python：$Py。请检查 EDU_RAG_PYTHON。"
}

$env:PYTHONUTF8 = "1"
Write-Host "使用 Python: $Py"
& $Py (Join-Path $PSScriptRoot "build.py") @BuildArgs
exit $LASTEXITCODE
