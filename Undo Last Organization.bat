@echo off
setlocal enabledelayedexpansion

title Download Organizer - 1-Click Undo

cd /d "%~dp0"
set "PYTHONPATH=%~dp0;%PYTHONPATH%"

echo ============================================================
echo           DOWNLOAD ORGANIZER - 1-CLICK INSTANT UNDO
echo ============================================================
echo.
echo Reverting last file organization back to Downloads...
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    if exist "dist\DownloadOrganizer.exe" (
        "dist\DownloadOrganizer.exe" --undo
        goto DONE
    )
    echo [ERROR] Python not found. Please run dist\DownloadOrganizer.exe instead.
    pause
    exit /b 1
)

python -m app.main --undo

:DONE
echo.
echo ============================================================
echo [DONE] Undo complete! Files restored safely.
echo ============================================================
echo.
ping 127.0.0.1 -n 3 >nul
exit /b 0
