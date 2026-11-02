"""Screens 6-7: quality control, approval, Excel export; plus audit log and backups."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import log
from ..auth import current_user, require_role
from ..backup import make_backup
from ..config import get_settings
from ..db import get_db
from ..models import AuditLog, User
from ..serializers import case_out, iso
from ..services.excel_export import export_report
from ..services.qa import run_qa
from ..services.workflow import get_policy
from .cases import load_case

router = APIRouter(prefix="/api", tags=["report"])


@router.get("/cases/{case_id}/qa")
def qa(case_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    c = load_case(db, case_id)
    res = run_qa(c, get_policy(db, c))
    db.commit()
    return res


class ApproveIn(BaseModel):
    note: str = ""
    acknowledge_warnings: bool = False


@router.post("/cases/{case_id}/prepare")
def mark_prepared(case_id: int, data: ApproveIn, db: Session = Depends(get_db), user: User = Depends(require_role("admin", "librarian"))):
    c = load_case(db, case_id)
    res = run_qa(c, get_policy(db, c))
    if res["errors"]:
        raise HTTPException(409, f"יש {res['errors']} שגיאות בבקרת האיכות שיש לטפל בהן לפני סימון 'הוכן'")
    c.prepared_by, c.prepared_at = user.username, datetime.now(timezone.utc)
    c.reviewed_by, c.reviewed_at = "", None  # any new preparation needs a fresh review
    log(db, user.username, "case", "prepared", c.id, c.id, warnings=res["warnings"], note=data.note)
    db.commit()
    return case_out(c)


@router.post("/cases/{case_id}/review")
def review(case_id: int, data: ApproveIn, db: Session = Depends(get_db), user: User = Depends(require_role("admin", "reviewer"))):
    """Second-person approval (procedure: exceptions are checked and approved by another employee)."""
    c = load_case(db, case_id)
    if not c.prepared_by:
        raise HTTPException(409, "התיק טרם סומן כמוכן על ידי העובד המכין")
    if c.prepared_by == user.username:
        raise HTTPException(409, "האישור חייב להינתן על ידי עובד אחר מזה שהכין את התיק")
    res = run_qa(c, get_policy(db, c))
    if res["errors"]:
        raise HTTPException(409, "קיימות שגיאות בבקרת האיכות")
    if res["warnings"] and not data.acknowledge_warnings:
        raise HTTPException(409, "יש לאשר במפורש שהאזהרות נבדקו")
    c.reviewed_by, c.reviewed_at, c.review_note = user.username, datetime.now(timezone.utc), data.note
    log(db, user.username, "case", "reviewed", c.id, c.id, warnings=res["warnings"], note=data.note)
    db.commit()
    return case_out(c)


@router.post("/cases/{case_id}/export")
def export(case_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = load_case(db, case_id)
    pol = get_policy(db, c)
    audit_rows = list(db.scalars(select(AuditLog).where(AuditLog.case_id == c.id).order_by(AuditLog.ts)))
    safe = re.sub(r"[^\w\-]", "_", c.researcher_name_en)[:60]
    status = "final" if c.reviewed_by else "draft"
    out = get_settings().exports_dir / f"case_{c.id}" / f"citations_{safe}_{datetime.now():%Y%m%d_%H%M%S}_{status}.xlsx"
    tpl = Path(c.template_path) if c.template_path else None
    info = export_report(c, pol, tpl, out, audit_rows, user.username)
    log(db, user.username, "case", "export", c.id, c.id, file=out.name, status=status,
        partial_cells=info["partial_cells"], mode=info["mode"])
    db.commit()
    info["filename"] = out.name
    info["status"] = status
    return info


@router.get("/cases/{case_id}/exports")
def list_exports(case_id: int, _: User = Depends(current_user)):
    folder = get_settings().exports_dir / f"case_{case_id}"
    files = sorted(folder.glob("*.xlsx"), reverse=True) if folder.exists() else []
    return [{"filename": f.name, "size": f.stat().st_size,
             "created": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat()} for f in files]


@router.get("/cases/{case_id}/exports/{filename}")
def download(case_id: int, filename: str, _: User = Depends(current_user)):
    folder = (get_settings().exports_dir / f"case_{case_id}").resolve()
    path = (folder / filename).resolve()
    if path.parent != folder or not path.exists():
        raise HTTPException(404, "קובץ לא נמצא")
    return FileResponse(path, filename=filename,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/audit")
def audit(case_id: int | None = None, limit: int = 500, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(AuditLog).order_by(AuditLog.ts.desc()).limit(min(limit, 5000))
    if case_id is not None:
        q = q.where(AuditLog.case_id == case_id)
    return [{"id": a.id, "ts": iso(a.ts), "username": a.username, "case_id": a.case_id, "entity": a.entity,
             "entity_id": a.entity_id, "action": a.action, "details": a.details} for a in db.scalars(q)]


@router.post("/admin/backup")
def backup(db: Session = Depends(get_db), user: User = Depends(require_role("admin"))):
    path = make_backup()
    log(db, user.username, "system", "backup", None, None, file=path.name)
    db.commit()
    return {"file": path.name}
