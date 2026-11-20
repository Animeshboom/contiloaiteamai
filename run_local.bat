@echo off
setlocal
cd /d "%~dp0"
echo ==========================================
echo       Starting StudioTrack AI Locally     
echo ==========================================
powershell -ExecutionPolicy Bypass -File "%~dp0run_local.ps1"
pause

