<#
Editing Copilot 1.0.0 - one-shot Windows installer (no admin rights needed).
 * Installs Python 3.12 per-user if missing (winget, else python.org silent installer)
 * Creates a private virtual environment in %LOCALAPPDATA%\EditingCopilot\app
 * Installs Editing Copilot + Vosk + sounddevice (+ faster-whisper with -Whisper)
 * Downloads the free English Vosk model (~40 MB)
 * Installs the DaVinci Resolve Workspace > Scripts menu entry
 * Creates Start-menu and Desktop shortcuts
 Optional: -GroqKey / -GeminiKey store your FREE API key as a user environment variable.
#>
[CmdletBinding()]
param(
    [switch]$Whisper,
    [string]$GroqKey = "",
    [string]$GeminiKey = "",
    [ValidateSet("auto","local","online")][string]$Mode = "auto",
    [switch]$NoShortcuts,
    [switch]$StartWithWindows
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Source   = Split-Path -Parent $PSScriptRoot           # package root (contains pyproject.toml)
$Root     = Join-Path $env:LOCALAPPDATA "EditingCopilot"
$Venv     = Join-Path $Root "app"
$Data     = Join-Path $Root "data"
$Models   = Join-Path $Data "models"
$LogFile  = Join-Path $Root "install.log"
New-Item -ItemType Directory -Force -Path $Root, $Data, $Models | Out-Null
Start-Transcript -Path $LogFile -Append | Out-Null

function Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }

function Find-Python {
    foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                     "$env:ProgramFiles\Python312\python.exe")) { if (Test-Path $c) { return $c } }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { $p = & py.exe -3.12 -c "import sys;print(sys.executable)" 2>$null; if ($LASTEXITCODE -eq 0 -and $p) { return $p.Trim() } }
    return $null
}

try {
    Step "Checking for Python 3.12"
    $Python = Find-Python
    if (-not $Python) {
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if ($winget) {
            Step "Installing Python 3.12 with winget (per-user)"
            & winget.exe install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
            $Python = Find-Python
        }
        if (-not $Python) {
            Step "Downloading Python 3.12 from python.org"
            $exe = Join-Path $env:TEMP "python-3.12.10-amd64.exe"
            Invoke-WebRequest "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" -OutFile $exe
            Start-Process $exe -Wait -ArgumentList "/quiet","InstallAllUsers=0","PrependPath=0","Include_launcher=1","Include_tcltk=1","Include_test=0"
            $Python = Find-Python
        }
        if (-not $Python) { throw "Python 3.12 could not be installed automatically. Install it from python.org and run Install.cmd again." }
    }
    Write-Host "Python: $Python"

    Step "Creating private environment"
    if (-not (Test-Path "$Venv\Scripts\python.exe")) { & $Python -m venv $Venv; if ($LASTEXITCODE) { throw "venv failed" } }
    $VPy = "$Venv\Scripts\python.exe"
    & $VPy -m pip install --disable-pip-version-check -q --upgrade pip | Out-Host
    $target = if ($Whisper) { "$($Source)[whisper]" } else { "$Source" }
    & $VPy -m pip install --disable-pip-version-check -q --upgrade "$target"
    if ($LASTEXITCODE) { throw "pip install failed (see $LogFile)" }
    # always refresh the app itself so an in-place upgrade from the same version picks up new files
    & $VPy -m pip install --disable-pip-version-check -q --force-reinstall --no-deps "$Source"
    if ($LASTEXITCODE) { throw "pip reinstall failed (see $LogFile)" }

    Step "Downloading free English speech model (Vosk small en-us)"
    $ModelDir = Join-Path $Models "vosk-model-small-en-us-0.15"
    if (-not (Test-Path "$ModelDir\am")) {
        $zip = Join-Path $env:TEMP "vosk-en.zip"
        Invoke-WebRequest "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip" -OutFile $zip
        Expand-Archive $zip -DestinationPath $Models -Force
        Remove-Item $zip -Force
    }

    Step "Copying resources (demo project, Resolve integration)"
    Remove-Item -Recurse -Force "$Root\resources" -ErrorAction SilentlyContinue
    Copy-Item -Recurse -Force "$Source\resources" "$Root\resources"

    Step "Writing configuration"
    & $VPy -c "from pathlib import Path;import json;from editing_copilot.config import load_config,save_config;d=Path(r'$Data');c,_=load_config(d);c['mode']='$Mode';save_config(d,c)"
    if ($GroqKey)   { [Environment]::SetEnvironmentVariable("GROQ_API_KEY",   $GroqKey,   "User"); $env:GROQ_API_KEY = $GroqKey }
    if ($GeminiKey) { [Environment]::SetEnvironmentVariable("GEMINI_API_KEY", $GeminiKey, "User"); $env:GEMINI_API_KEY = $GeminiKey
                      & $VPy -c "from pathlib import Path;from editing_copilot.config import load_config,save_config;d=Path(r'$Data');c,_=load_config(d);c['online']['provider']='gemini' if not '$GroqKey' else c['online']['provider'];save_config(d,c)" }

    Step "Installing DaVinci Resolve menu script"
    & $VPy -c "from editing_copilot.install import install_resolve_menu;from editing_copilot.__main__ import resource_dir;print(install_resolve_menu(resource_dir())['message'])"

    if (-not $NoShortcuts) {
        Step "Creating shortcuts"
        $sh = New-Object -ComObject WScript.Shell
        $targets = @("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Editing Copilot.lnk", "$([Environment]::GetFolderPath('Desktop'))\Editing Copilot.lnk")
        foreach ($t in $targets) {
            $l = $sh.CreateShortcut($t)
            $l.TargetPath = "$Venv\Scripts\pythonw.exe"
            $l.Arguments = "-m editing_copilot"
            $l.WorkingDirectory = $Root
            $l.Description = "Voice-controlled editing companion for Kdenlive and DaVinci Resolve"
            $l.Save()
        }
    }

    Copy-Item -Force "$Source\QUICKSTART.pdf", "$Source\QUICKSTART.md", "$Source\README.md" $Root -ErrorAction SilentlyContinue
    if (-not $NoShortcuts) {
        $sh = New-Object -ComObject WScript.Shell
        $q = $sh.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Editing Copilot Quick Start.lnk")
        $q.TargetPath = "$Root\QUICKSTART.pdf"; $q.Save()
    }
    if ($StartWithWindows) {
        $sh = New-Object -ComObject WScript.Shell
        $s2 = $sh.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Editing Copilot.lnk")
        $s2.TargetPath = "$Venv\Scripts\pythonw.exe"; $s2.Arguments = "-m editing_copilot --minimized"; $s2.WorkingDirectory = $Root; $s2.Save()
    }

    Step "Self-check"
    & $VPy -m editing_copilot --voice-check | Out-Host
    Write-Host ""
    Write-Host "Editing Copilot is installed. Start it from the Start menu or Desktop shortcut." -ForegroundColor Green
    Write-Host "Restart DaVinci Resolve to see Workspace > Scripts > Utility > Editing Copilot."
}
catch {
    Write-Host "INSTALL FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Log: $LogFile"
    exit 1
}
finally { Stop-Transcript | Out-Null }
