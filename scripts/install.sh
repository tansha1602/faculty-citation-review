#!/usr/bin/env bash
# One-time installation (Linux/macOS). Requires Python 3.11+ and Node.js 18+.
set -e
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm install && npm run build)
.venv/bin/python sample_data/generate_samples.py
[ -f .env ] || cp .env.example .env
echo "Installed. Start with: scripts/run.sh"
