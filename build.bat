@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo        BUILDING DOWNLOAD ORGANIZER WINDOWS EXECUTABLE
echo ============================================================
echo.

:: Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

echo [1/4] Checking and installing build dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements-lock.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo [2/4] Running automated test suite...
python -m pytest tests/
if %errorlevel% neq 0 (
    echo [ERROR] Unit tests failed! Aborting build to ensure reliability.
    pause
    exit /b 1
)
echo [OK] All tests passed!

echo [3/4] Building standalone Windows executable via PyInstaller...
python -m PyInstaller --clean --noconfirm DownloadOrganizer.spec
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed. Check logs above.
    pause
    exit /b 1
)

echo [4/4] Verifying build output...
if exist "dist\DownloadOrganizer.exe" (
    echo.
    echo ============================================================
    echo [SUCCESS] DownloadOrganizer.exe built successfully!
    echo Location: %~dp0dist\DownloadOrganizer.exe
    echo ============================================================
) else (
    echo [ERROR] dist\DownloadOrganizer.exe was not created!
    pause
    exit /b 1
)

echo.
pause
