@echo off
rem Run the bot directly on this PC (if you don't use a server).
rem Requires Python 3.11+ (winget install Python.Python.3.12) and a filled .env in the project root.
cd /d %~dp0\..\..
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)
.venv\Scripts\python -m app
pause
