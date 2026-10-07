$ErrorActionPreference="Stop"
Set-Location $PSScriptRoot
python --version
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip pyinstaller
& ".\.venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name "Zwart-AI-Router" "zwart_router_app.py"
Copy-Item "config.json" "dist\config.json" -Force
Write-Host "Built: dist\Zwart-AI-Router.exe"
