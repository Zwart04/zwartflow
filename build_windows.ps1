$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python --version
python gen_icon.py

if (-not (Test-Path ".venv")) { python -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install --quiet pyinstaller

& ".\.venv\Scripts\python.exe" -m PyInstaller `
    --noconfirm --clean --onefile --windowed `
    --icon "assets\icon.ico" `
    --name "ZwartFlow" `
    "zwart_router.py"

Copy-Item "config.json" "dist\config.json" -Force
Write-Host ""
Write-Host "Build selesai: dist\ZwartFlow.exe"
