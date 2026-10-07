$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# compiler C# bawaan Windows (.NET Framework 4.8) - tanpa SDK, tanpa install apa pun
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe" }
if (-not (Test-Path $csc)) { throw "csc.exe (.NET Framework 4.x) tidak ditemukan" }

if (-not (Test-Path "dist")) { New-Item -ItemType Directory "dist" | Out-Null }

& $csc /nologo /target:winexe /platform:anycpu `
    /win32icon:"assets\icon.ico" `
    /out:"dist\ZwartFlow.exe" `
    /r:System.dll /r:System.Core.dll /r:System.Drawing.dll `
    /r:System.Windows.Forms.dll /r:System.Web.Extensions.dll `
    "Program.cs"

if ($LASTEXITCODE -ne 0) { throw "Build gagal (exit $LASTEXITCODE)" }

Copy-Item "config.json" "dist\config.json" -Force
Write-Host ""
Write-Host "Build selesai: dist\ZwartFlow.exe"
