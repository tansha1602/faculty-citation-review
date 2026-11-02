"""Backups: a zip with a consistent SQLite snapshot plus uploaded files and exports.

Run manually:  python -m app.backup   (from the backend folder)
For PostgreSQL use pg_dump instead; this zips only the files.
"""
from __future__ import annotations

import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from .config import get_settings

KEEP = 30


def make_backup() -> Path:
    s = get_settings()
    s.backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = s.backups_dir / f"fcr_backup_{stamp}.zip"
    snapshot = s.backups_dir / f"_snapshot_{stamp}.sqlite3"
    if s.database_url.startswith("sqlite:///"):
        src = sqlite3.connect(s.database_url.removeprefix("sqlite:///"))
        dst = sqlite3.connect(snapshot)
        src.backup(dst)  # consistent online copy
        dst.close()
        src.close()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        if snapshot.exists():
            z.write(snapshot, "fcr.sqlite3")
        for folder in (s.uploads_dir, s.exports_dir):
            if folder.exists():
                for f in folder.rglob("*"):
                    if f.is_file():
                        z.write(f, f.relative_to(s.data_dir))
    snapshot.unlink(missing_ok=True)
    backups = sorted(s.backups_dir.glob("fcr_backup_*.zip"))
    for old in backups[:-KEEP]:
        old.unlink()
    return out


if __name__ == "__main__":
    print(make_backup())
