@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo The project environment is not installed.
    echo Run setup_windows.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "PVT-demonstrator\pvt_native_azel.py"
if errorlevel 1 pause
endlocal

