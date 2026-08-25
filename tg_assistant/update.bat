@echo off
REM Update Nersiti to latest (needs git). Run from the git-cloned folder.
setlocal
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 ( echo Git not installed. Get it: https://git-scm.com/download/win & pause & exit /b 1 )
git pull
echo.
echo Updated. Now run nersiti_app.bat
pause
