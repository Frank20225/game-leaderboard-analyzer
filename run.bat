@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Running setup.bat first...
    call setup.bat
    if errorlevel 1 exit /b 1
)

echo ==================================================
echo  Game Leaderboard Analyzer - Starting Local Web UI
echo  URL: http://127.0.0.1:8765
echo  Press Ctrl+C to stop the server.
echo ==================================================

".venv\Scripts\python.exe" -m src.main
pause
