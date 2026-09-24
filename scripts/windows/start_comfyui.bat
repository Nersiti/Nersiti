@echo off
rem Start ComfyUI listening on the network (the bot on the server connects via Tailscale).
cd /d C:\AI\ComfyUI_windows_portable
.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --listen 0.0.0.0 --port 8188
pause
