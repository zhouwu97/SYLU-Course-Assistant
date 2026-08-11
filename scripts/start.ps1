# SYLU Course Assistant - 启动脚本
# 用法: .\scripts\start.ps1
# 启动后浏览器访问 http://localhost:8765

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
    Write-Host "[setup] 创建虚拟环境 .venv ..." -ForegroundColor Cyan
    py -m venv .venv
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    & ".venv\Scripts\python.exe" -m playwright install chromium
}

Write-Host "[start] 启动 SYLU Course Assistant backend (http://localhost:8765)" -ForegroundColor Green
& ".venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8765
