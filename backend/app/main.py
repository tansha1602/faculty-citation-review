"""Faculty Citation Review — FastAPI application.

Run:  uvicorn app.main:app --host 127.0.0.1 --port 8000   (from the backend folder)
The built React UI (frontend/dist) is served from the same address.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import ensure_initial_admin
from .config import PROJECT_ROOT, get_settings
from .db import init_engine, new_session
from .routers import auth_users, cases, report, sources


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    for d in (s.data_dir, s.uploads_dir, s.exports_dir, s.backups_dir):
        d.mkdir(parents=True, exist_ok=True)
    init_engine()
    with new_session() as db:
        ensure_initial_admin(db)
    yield


app = FastAPI(title="Faculty Citation Review", version="1.0.0", lifespan=lifespan)
for r in (auth_users.router, cases.router, sources.router, report.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True}


DIST = PROJECT_ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
