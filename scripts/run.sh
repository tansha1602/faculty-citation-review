#!/usr/bin/env bash
# Start the system at http://127.0.0.1:8000 (this computer only).
cd "$(dirname "$0")/../backend"
exec ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
