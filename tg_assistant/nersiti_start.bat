@echo off
REM Nersiti - one-click launcher (Windows). ASCII only to avoid codepage issues.
setlocal enabledelayedexpansion
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python not found. Install Python 3.11+ from https://www.python.org/downloads/
  echo IMPORTANT: check "Add python.exe to PATH" during install, then run this again.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Creating virtual environment...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"

echo Installing dependencies...
python -m pip install --quiet --upgrade pip
pip install --quiet telethon

if not exist ".env" (
  echo.
  echo Get api_id and api_hash from https://my.telegram.org
  set /p AID=api_id:
  set /p AHASH=api_hash:
  > .env echo TG_API_ID=!AID!
  >> .env echo TG_API_HASH=!AHASH!
  echo .env created.
)

echo.
echo Starting Telegram connector.
echo Enter phone (+7...) and the code from Telegram when asked.
echo Archive folder: %USERPROFILE%\NersitiArchive
echo.
python run_telegram.py --backfill 300

echo.
echo Done. You can close this window.
pause
