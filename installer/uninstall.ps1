# Removes the app environment, shortcuts and Resolve menu script. Keeps your history and project copies
# in %LOCALAPPDATA%\EditingCopilot\data unless -RemoveData is given. Never touches your media.
param([switch]$RemoveData)
$Root = Join-Path $env:LOCALAPPDATA "EditingCopilot"
Remove-Item -Recurse -Force "$Root\app", "$Root\integration" -ErrorAction SilentlyContinue
Remove-Item -Force "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Editing Copilot.lnk", "$([Environment]::GetFolderPath('Desktop'))\Editing Copilot.lnk" -ErrorAction SilentlyContinue
Remove-Item -Force "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Editing Copilot Quick Start.lnk", "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Editing Copilot.lnk" -ErrorAction SilentlyContinue
Remove-Item -Force "$env:APPDATA\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\Editing Copilot.py" -ErrorAction SilentlyContinue
if ($RemoveData) { Remove-Item -Recurse -Force "$Root\data" -ErrorAction SilentlyContinue }
Write-Host "Editing Copilot removed." -ForegroundColor Green
