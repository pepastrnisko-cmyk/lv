@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\setup.ps1" %*
pause
