@echo off
REM Build Nersiti.exe (Windows). ASCII only.
setlocal
cd /d "%~dp0"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet pyinstaller PySide6 telethon httpx pyyaml
pyinstaller --noconfirm --windowed --name Nersiti --collect-all PySide6 -p . app.py
echo.
echo Done. EXE: dist\Nersiti\Nersiti.exe
echo Note: keep .env and login session; archive stays in %USERPROFILE%\NersitiArchive
pause
