@echo off
REM Nersiti desktop app launcher for Windows. ASCII only.
setlocal enabledelayedexpansion
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.11+ from https://www.python.org/downloads/  Check "Add to PATH".
  pause & exit /b 1
)

echo Installing dependencies. First run may take a few minutes...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet PySide6 telethon httpx pyyaml anthropic

if not exist ".env" (
  echo.
  echo Paste your keys from https://my.telegram.org
  set /p AID=api_id:
  set /p AHASH=api_hash:
  > .env echo TG_API_ID=!AID!
  >> .env echo TG_API_HASH=!AHASH!
  echo .env created.
)

echo.
echo IMPORTANT: close the run_telegram window first if it is open.
echo Starting Nersiti. Password: Logingood123337
echo.
python app.py
pause
