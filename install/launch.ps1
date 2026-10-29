# Plastron launcher (Windows). The desktop shortcut runs this.
#
# 1. Checks GitHub for a newer Plastron on the main branch and installs it.
# 2. Makes sure the pinned portable Blender (install/blender_version.txt) is present.
# 3. Starts Plastron.
# With no internet it just starts the copy already installed.

param(
    [string]$Root = "C:\Plastron",
    [string]$Branch = "main",
    [switch]$Install,        # first-time setup: also create the shortcuts
    [switch]$NoStart         # update only, don't start Plastron
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # makes downloads much faster in Windows PowerShell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo        = "olliejoet-glitch/Plastron"
$AppDir      = Join-Path $Root "app"
$BlenderDir  = Join-Path $Root "blender"
$TemplateDir = Join-Path $BlenderDir "portable\scripts\startup\bl_app_templates_user\plastron"

function Say($text) { Write-Host "Plastron: $text" }

# The shortcut runs this hidden, so anything important also gets a pop-up
# (it closes itself after $seconds).
function Notify($text, $seconds = 10) {
    if ($Install) { Say $text; return }
    (New-Object -ComObject WScript.Shell).Popup($text, $seconds, "Plastron", 64) | Out-Null
}

function Get-File($url, $dest, $label) {
    try {
        Start-BitsTransfer -Source $url -Destination $dest -DisplayName $label
    } catch {
        & curl.exe -L --fail -o $dest $url
        if ($LASTEXITCODE -ne 0) { Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing }
    }
}

function Get-LatestCommit {
    try {
        $headers = @{ Accept = "application/vnd.github.sha" }
        return (Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/commits/$Branch" `
                -Headers $headers -TimeoutSec 5).Trim()
    } catch {
        return $null    # offline or GitHub unreachable: keep the installed copy
    }
}

function Update-App {
    $latest = Get-LatestCommit
    $versionFile = Join-Path $AppDir "VERSION"
    $installed = if (Test-Path $versionFile) { (Get-Content $versionFile -Raw).Trim() } else { "" }
    if (-not $latest -or $latest -eq $installed) { return }

    Say "updating to $($latest.Substring(0, 7))..."
    $tmp = Join-Path $env:TEMP "plastron-update"
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    New-Item -ItemType Directory $tmp | Out-Null
    $zip = Join-Path $tmp "app.zip"
    Invoke-WebRequest -Uri "https://codeload.github.com/$Repo/zip/$latest" -OutFile $zip -UseBasicParsing
    Expand-Archive $zip -DestinationPath $tmp
    $top = Get-ChildItem $tmp -Directory | Select-Object -First 1

    if (Test-Path $AppDir) { Remove-Item $AppDir -Recurse -Force }
    Move-Item $top.FullName $AppDir
    Set-Content $versionFile $latest
    Remove-Item $tmp -Recurse -Force

    # Keep the launcher and icon at fixed paths (the shortcut points at them).
    Copy-Item (Join-Path $AppDir "install\launch.ps1") (Join-Path $Root "launch.ps1") -Force
    Copy-Item (Join-Path $AppDir "plastron\assets\plastron.ico") (Join-Path $Root "plastron.ico") -Force
}

function Install-Template {
    # Copy Plastron into the portable Blender as an app template.
    if (Test-Path $TemplateDir) { Remove-Item $TemplateDir -Recurse -Force }
    New-Item -ItemType Directory (Split-Path $TemplateDir) -Force | Out-Null
    Copy-Item (Join-Path $AppDir "plastron") $TemplateDir -Recurse
}

function Install-Blender {
    $want = (Get-Content (Join-Path $AppDir "install\blender_version.txt") -Raw).Trim()
    $marker = Join-Path $BlenderDir "PLASTRON_BLENDER_VERSION"
    $have = if (Test-Path $marker) { (Get-Content $marker -Raw).Trim() } else { "" }
    if ($want -eq $have -and (Test-Path (Join-Path $BlenderDir "blender.exe"))) { return }

    $series = ($want -split "\.")[0..1] -join "."
    $name = "blender-$want-windows-x64"
    $base = "https://download.blender.org/release/Blender$series"
    Notify "Downloading Blender $want for Plastron (about 400 MB). This takes a few minutes; Plastron opens when it's done."
    $tmp = Join-Path $Root "download"
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    New-Item -ItemType Directory $tmp | Out-Null
    $zip = Join-Path $tmp "$name.zip"
    Get-File "$base/$name.zip" $zip "Downloading Blender $want"

    $sums = (Invoke-WebRequest -Uri "$base/blender-$want.sha256" -UseBasicParsing).Content
    $expected = ($sums -split "`n" | Where-Object { $_ -match "$name\.zip" }) -split "\s+" | Select-Object -First 1
    $actual = (Get-FileHash $zip -Algorithm SHA256).Hash
    if ($actual -ne $expected.ToUpper()) { throw "Blender download is corrupt (checksum mismatch). Please run again." }

    Say "unpacking Blender..."
    try { tar.exe -xf $zip -C $tmp } catch { }
    if (-not (Test-Path (Join-Path $tmp "$name\blender.exe"))) { Expand-Archive $zip -DestinationPath $tmp -Force }

    # Keep Plastron's settings (portable\config) if Blender is being upgraded.
    $oldConfig = Join-Path $BlenderDir "portable\config"
    $keep = Join-Path $tmp "config-keep"
    if (Test-Path $oldConfig) { Move-Item $oldConfig $keep }
    if (Test-Path $BlenderDir) { Remove-Item $BlenderDir -Recurse -Force }
    Move-Item (Join-Path $tmp $name) $BlenderDir

    # A "portable" folder makes this Blender keep all its settings to itself.
    New-Item -ItemType Directory (Join-Path $BlenderDir "portable") -Force | Out-Null
    if (Test-Path $keep) { Move-Item $keep (Join-Path $BlenderDir "portable\config") }
    Set-Content $marker $want
    Remove-Item $tmp -Recurse -Force
}

function New-Shortcuts {
    $shell = New-Object -ComObject WScript.Shell
    $places = @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))
    foreach ($place in $places) {
        $lnk = $shell.CreateShortcut((Join-Path $place "Plastron.lnk"))
        $lnk.TargetPath = "powershell.exe"
        $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Root\launch.ps1`""
        $lnk.WorkingDirectory = $Root
        $lnk.IconLocation = "$Root\plastron.ico"
        $lnk.Description = "Plastron"
        $lnk.Save()
    }
}

function Start-Plastron {
    $exe = Join-Path $BlenderDir "blender-launcher.exe"   # starts Blender without a console window
    if (-not (Test-Path $exe)) { $exe = Join-Path $BlenderDir "blender.exe" }
    if (Test-Path $exe) {
        Start-Process $exe -ArgumentList "--app-template", "plastron" -WorkingDirectory $Root
    }
}

try {
    New-Item -ItemType Directory $Root -Force | Out-Null
    $versionFile = Join-Path $AppDir "VERSION"
    $before = if (Test-Path $versionFile) { Get-Content $versionFile -Raw } else { "" }
    Update-App
    if (-not (Test-Path $AppDir)) { throw "Couldn't download Plastron. Check the internet connection and try again." }
    Install-Blender                          # first: a new Blender replaces the whole folder
    $after = Get-Content $versionFile -Raw
    if ($after -ne $before -or -not (Test-Path $TemplateDir)) { Install-Template }
    if ($Install) { New-Shortcuts }
} catch {
    if ($Install) { throw }
    Notify "Plastron couldn't update: $($_.Exception.Message)`nStarting the installed version." 15
}

if (-not $NoStart) { Start-Plastron }
