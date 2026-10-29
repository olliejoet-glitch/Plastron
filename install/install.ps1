# Plastron one-time installer (Windows). Paste into PowerShell:
#
#   irm https://raw.githubusercontent.com/olliejoet-glitch/Plastron/main/install/install.ps1 | iex
#
# Installs into C:\Plastron: a private portable Blender (your normal Blender is
# untouched), Plastron itself, and Plastron shortcuts on the desktop and Start
# menu. Then starts Plastron. Updates happen automatically each time
# Plastron starts.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = "C:\Plastron"
$Launcher = Join-Path $Root "launch.ps1"

Write-Host "Installing Plastron into $Root ..."
New-Item -ItemType Directory $Root -Force | Out-Null
Invoke-WebRequest -UseBasicParsing -OutFile $Launcher `
    -Uri "https://raw.githubusercontent.com/olliejoet-glitch/Plastron/main/install/launch.ps1"

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Launcher -Root $Root -Install
if ($LASTEXITCODE -ne 0) {
    Write-Host "Something went wrong (see above). Running the same line again usually fixes it." -ForegroundColor Red
} else {
    Write-Host "Done. Plastron is starting, and has a shortcut on your desktop." -ForegroundColor Green
}
