@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo The project environment is not installed.
    echo Run setup_windows.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "boiler_furnace_simulator\suite_main.py"
if errorlevel 1 pause
endlocal
