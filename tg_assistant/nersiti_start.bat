@echo off
REM ============================================================
REM  Nersiti — запуск в один клик (Windows)
REM  Ставит окружение, спрашивает api_id/api_hash (один раз),
REM  логинит Telegram и запускает архивацию всего в папку.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python не найден. Установи Python 3.11+ с https://www.python.org/downloads/
  echo     При установке ОБЯЗАТЕЛЬНО отметь "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist .venv (
  echo [*] Создаю виртуальное окружение...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [*] Ставлю зависимости (telethon)...
python -m pip install --quiet --upgrade pip
pip install --quiet telethon

if not exist .env (
  echo.
  echo Нужны api_id и api_hash с https://my.telegram.org  (раздел API development tools)
  set /p AID=Вставь api_id:
  set /p AHASH=Вставь api_hash:
  > .env echo TG_API_ID=!AID!
  >> .env echo TG_API_HASH=!AHASH!
  echo [*] Файл .env создан.
)

echo.
echo [*] Запускаю Telegram-коннектор. Введи номер (с +7...) и код из Telegram.
echo     Архив будет в папке %USERPROFILE%\NersitiArchive
echo.
python run_telegram.py --backfill 300

echo.
echo Готово. Окно можно закрыть.
pause
