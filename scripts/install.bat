@echo off
REM One-time installation (Windows). Requires Python 3.11+ and Node.js 18+.
cd /d %~dp0\..
py -3 -m venv .venv || python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
cd frontend
call npm install
call npm run build
cd ..
.venv\Scripts\python sample_data\generate_samples.py
if not exist .env copy .env.example .env
echo Installed. Start with scripts\run.bat
pause
