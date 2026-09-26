@echo off
setlocal enabledelayedexpansion

title Download Organizer - 1-Click Fast Sort

cd /d "%~dp0"
set "PYTHONPATH=%~dp0;%PYTHONPATH%"

echo ============================================================
echo           DOWNLOAD ORGANIZER - 1-CLICK INSTANT SORT
echo ============================================================
echo.
echo Scanning and sorting your Downloads folder...
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    if exist "dist\DownloadOrganizer.exe" (
        "dist\DownloadOrganizer.exe" --quick
        goto DONE
    )
    echo [ERROR] Python not found. Please run dist\DownloadOrganizer.exe instead.
    pause
    exit /b 1
)

python -m app.main --quick

:DONE
echo.
echo ============================================================
echo [DONE] All files sorted safely in seconds!
echo Every move is recorded in History and can be undone.
echo ============================================================
echo.
ping 127.0.0.1 -n 3 >nul
exit /b 0

