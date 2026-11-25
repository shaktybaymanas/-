@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime\python.exe" (
    echo Portable runtime not found. Extract the whole ZIP before opening start.cmd.
    pause
    exit /b 1
)
"%~dp0runtime\python.exe" -B app.py --port 0 --open
if errorlevel 1 pause
