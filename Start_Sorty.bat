@echo off
cd /d "%~dp0"
if exist "%~dp0dist\Sorty.exe" (
    start "" "%~dp0dist\Sorty.exe" %*
) else (
    start "" pythonw "%~dp0app\main.py" %*
)
exit /b 0
