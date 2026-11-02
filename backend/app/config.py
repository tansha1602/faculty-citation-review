"""Settings come from environment variables (optionally loaded from a local .env file).

API keys are never stored in code, in the database or in exported reports.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines). Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    scopus_api_key: str | None
    scopus_inst_token: str | None
    wos_starter_api_key: str | None
    wos_expanded_api_key: str | None
    http_timeout: float
    allow_external_ai: bool

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"


def get_settings() -> Settings:
    data_dir = Path(os.environ.get("FCR_DATA_DIR", PROJECT_ROOT / "data")).resolve()
    db_url = os.environ.get("FCR_DATABASE_URL") or f"sqlite:///{data_dir / 'fcr.sqlite3'}"
    return Settings(
        data_dir=data_dir,
        database_url=db_url,
        scopus_api_key=os.environ.get("SCOPUS_API_KEY") or None,
        scopus_inst_token=os.environ.get("SCOPUS_INST_TOKEN") or None,
        wos_starter_api_key=os.environ.get("WOS_STARTER_API_KEY") or None,
        wos_expanded_api_key=os.environ.get("WOS_EXPANDED_API_KEY") or None,
        http_timeout=float(os.environ.get("FCR_HTTP_TIMEOUT", "30")),
        # CVs are never sent to external AI services. There is no such integration;
        # this flag exists only so the policy is explicit and visible in the UI.
        allow_external_ai=False,
    )
