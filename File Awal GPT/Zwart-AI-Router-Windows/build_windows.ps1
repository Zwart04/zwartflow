$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Checking Python..."
python --version

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pyinstaller

& ".\.venv\Scripts\python.exe" -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "Zwart-AI-Router" `
    "zwart_ai_router.py"

Copy-Item "config.json" "dist\config.json" -Force

Write-Host ""
Write-Host "Build selesai:"
Write-Host (Resolve-Path ".\dist\Zwart-AI-Router.exe")
