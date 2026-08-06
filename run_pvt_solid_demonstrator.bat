@echo off
setlocal
cd /d "%~dp0"
python "PVT-demonstrator\pvt_native_solid.py"
if errorlevel 1 pause
