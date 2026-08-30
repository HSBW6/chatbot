@echo off
rem One-click launcher for the DeepSeek chatbot.
rem Double-click this file after you have set up .venv and .env once.
rem %~dp0 = 本脚本所在目录，避免硬编码路径导致换目录后失效。
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python chatbot.py
echo.
echo Chat exited. Press any key to close this window.
pause >nul
