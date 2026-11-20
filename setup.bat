@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==================================================
echo  Game Leaderboard Analyzer - Environment Setup
echo ==================================================

set "PY_CMD="
where py >nul 2>&1 && (
    py -3.11 --version >nul 2>&1 && set "PY_CMD=py -3.11"
)
if not defined PY_CMD (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    ) else (
        set "PY_CMD=python"
    )
)

echo [1/3] Using Python: %PY_CMD%
if not exist ".venv\Scripts\python.exe" (
    echo [2/3] Creating virtual environment .venv ...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv. Please ensure Python 3.11 is installed.
        pause
        exit /b 1
    )
) else (
    echo [2/3] Virtual environment .venv already exists.
)

echo [3/3] Upgrading pip and installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed.
    pause
    exit /b 1
)

echo.
echo [DONE] Setup completed successfully! You can now run run.bat.
pause
