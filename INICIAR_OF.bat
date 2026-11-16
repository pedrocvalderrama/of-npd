@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente Python ausente. Siga a instalacao em README_INTERFACE.md.
    pause
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -u "%~dp0iniciar_of.py"
if errorlevel 1 pause
