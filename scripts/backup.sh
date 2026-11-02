#!/usr/bin/env bash
# Create a backup zip in data/backups (suitable for a daily cron / Task Scheduler job).
cd "$(dirname "$0")/../backend" && ../.venv/bin/python -m app.backup
