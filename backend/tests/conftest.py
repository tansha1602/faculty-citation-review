import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
SAMPLES = ROOT / "sample_data"


@pytest.fixture(scope="session", autouse=True)
def _samples():
    """Make sure the (fictional) sample files exist."""
    if not (SAMPLES / "sample_cv.docx").exists():
        import runpy
        runpy.run_path(str(SAMPLES / "generate_samples.py"), run_name="__main__")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FCR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("FCR_DATABASE_URL", raising=False)
    for k in ("SCOPUS_API_KEY", "SCOPUS_INST_TOKEN", "WOS_STARTER_API_KEY", "WOS_EXPANDED_API_KEY", "FCR_ADMIN_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    from fastapi.testclient import TestClient

    from app import db
    from app.main import app

    db.init_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    with TestClient(app) as c:
        yield c
    db._engine.dispose()


def login(client, username="admin", password="admin-pass-123", role=None):
    r = client.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def admin(client):
    r = client.post("/api/setup", json={"username": "admin", "password": "admin-pass-123", "display_name": "Admin"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
