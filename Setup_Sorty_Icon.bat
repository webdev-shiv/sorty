@echo off
setlocal enabledelayedexpansion
title Sorty - Setup Desktop Shortcut and Background Service
cd /d "%~dp0"

echo =======================================================
echo          SORTY - AUTOMATIC FILE ORGANIZER
echo =======================================================
echo.
echo [1/3] Detecting Sorty executable...

set "ICON_FILE=%~dp0assets\icon.ico"
set "APP_DIR=%~dp0"
set "EXE_FILE=%~dp0dist\Sorty.exe"

if exist "%EXE_FILE%" (
    set "TARGET_RUN=%EXE_FILE%"
) else (
    set "TARGET_RUN=pythonw.exe \"%~dp0app\main.py\""
)

echo [2/3] Creating Windows Desktop icon with custom 3D folder art...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $d = [System.Environment]::GetFolderPath('Desktop'); $s = $ws.CreateShortcut(\"$d\Sorty.lnk\"); $s.TargetPath = '%TARGET_RUN%'; $s.WorkingDirectory = '%APP_DIR%'; $s.IconLocation = '%ICON_FILE%'; $s.Description = 'Sorty - Automatic File Organizer'; $s.Save(); Write-Host '   Shortcut successfully created at:' $d\Sorty.lnk"

echo [3/3] Starting Sorty in the background...
if exist "%EXE_FILE%" (
    start "" "%EXE_FILE%"
) else (
    start "" pythonw "%~dp0app\main.py"
)

echo.
echo =======================================================
echo [SUCCESS] Sorty icon has been added to your Windows Desktop!
echo.
echo - Double click the Sorty icon on your Desktop anytime.
echo - Sorty is running in the background and monitoring your files.
echo - Low CPU and memory usage (deterministic, local, zero AI).
echo =======================================================
echo.
ping 127.0.0.1 -n 3 >nul
exit /b 0
