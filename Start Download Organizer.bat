@echo off
setlocal

title Download Organizer Launcher

:: Set current directory to project root
cd /d "%~dp0"
set "PYTHONPATH=%~dp0;%PYTHONPATH%"

:: Step 1: Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://python.org
    powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Python is not installed or not added to your system PATH.\nPlease install Python 3.10+ from python.org and check \"Add Python to PATH\".', 'Download Organizer Setup', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)" >nul 2>&1
    pause
    exit /b 1
)

:: Step 2: Check Python version (>= 3.10)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10 or newer is required.
    powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Download Organizer requires Python 3.10 or newer.', 'Download Organizer Setup', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)" >nul 2>&1
    pause
    exit /b 1
)

:: Step 3: Check if dependencies are already installed in active Python
python -c "import watchdog, pystray, PIL" >nul 2>&1
if %errorlevel% equ 0 (
    set "RUNNER=pythonw"
    goto LAUNCH
)

:: Step 4: If not installed globally, set up local .venv
if not exist ".venv\Scripts\python.exe" (
    echo Setting up local virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

set "RUNNER=.venv\Scripts\pythonw.exe"
set "VENV_PIP=.venv\Scripts\pip.exe"

.venv\Scripts\python.exe -c "import watchdog, pystray, PIL" >nul 2>&1
if errorlevel 1 (
    echo Installing lightweight dependencies...
    %VENV_PIP% install --quiet --upgrade pip
    %VENV_PIP% install --quiet -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

:LAUNCH
echo Launching Download Organizer...
start "" "%RUNNER%" -m app.main
exit /b 0
