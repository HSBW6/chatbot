@echo off
rem One-click launcher for the DeepSeek chatbot.
rem Double-click this file after you have set up .venv and .env once.
cd /d D:\Deepseek\chatbot
call .venv\Scripts\activate.bat
python chatbot.py
echo.
echo Chat exited. Press any key to close this window.
pause >nul
