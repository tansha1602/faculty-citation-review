@echo off
REM Start the system at http://127.0.0.1:8000 (this computer only).
cd /d %~dp0\..\backend
start "" http://127.0.0.1:8000
..\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
