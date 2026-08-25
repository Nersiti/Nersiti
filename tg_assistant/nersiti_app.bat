@echo off
REM Nersiti desktop app (Windows). ASCII only. Run from this folder.
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.11+ from https://www.python.org/downloads/ (check "Add to PATH")
  pause & exit /b 1
)
echo Installing dependencies (PySide6, telethon, httpx)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet PySide6 telethon httpx pyyaml
echo.
echo IMPORTANT: close the run_telegram window first (one Telegram session at a time).
echo Starting Nersiti. Password: Logingood123337
echo.
python app.py
pause
