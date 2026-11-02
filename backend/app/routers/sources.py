"""Screens 4-5: database lookups, manual Scholar input, citing records and classification."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..adapters import scholar as scholar_mod
from ..adapters import scopus as scopus_mod
from ..adapters import wos as wos_mod
from ..adapters.base import AdapterError, AdapterNotConfigured
from ..adapters.scholar import GoogleScholarAdapter
from ..adapters.scopus import ScopusAdapter
from ..adapters.wos import WebOfScienceAdapter
from ..audit import log
from ..auth import current_user, require_role
from ..config import get_settings
from ..db import get_db
from ..models import CLASSIFICATIONS, PROVIDERS, CitingRecord, Publication, SourceRecord, User
from ..serializers import citing_out, publication_out
from ..services.citing_import import parse_citing_file
from ..services.workflow import add_citing, get_check, get_policy, reclassify, search_provider
from .cases import _save_upload, load_case

router = APIRouter(prefix="/api", tags=["sources"])
EDIT = ("admin", "librarian")


def adapter_for(provider: str):
    s = get_settings()
    if provider == "scopus":
        return ScopusAdapter(s.scopus_api_key, s.scopus_inst_token, s.http_timeout)
    if provider == "wos":
        return WebOfScienceAdapter(s.wos_starter_api_key, s.wos_expanded_api_key, s.http_timeout)
    raise HTTPException(400, "Google Scholar אינו מחובר ל-API — יש להזין נתונים ידנית")


def _pub(db: Session, pub_id: int) -> Publication:
    p = db.get(Publication, pub_id)
    if not p:
        raise HTTPException(404, "פרסום לא נמצא")
    return p


def _provider(provider: str):
    if provider not in PROVIDERS:
        raise HTTPException(400, "מאגר לא מוכר")


@router.get("/providers")
def providers(_: User = Depends(current_user)):
    """What is configured, and which credentials are required before connecting to external services."""
    s = get_settings()
    return {
        "scopus": {"configured": bool(s.scopus_api_key), "inst_token": bool(s.scopus_inst_token),
                   "requirements": scopus_mod.REQUIREMENTS,
                   "env": ["SCOPUS_API_KEY", "SCOPUS_INST_TOKEN"]},
        "wos": {"configured": bool(s.wos_starter_api_key), "citing_api": bool(s.wos_expanded_api_key),
                "requirements": wos_mod.REQUIREMENTS, "env": ["WOS_STARTER_API_KEY", "WOS_EXPANDED_API_KEY"]},
        "scholar": {"configured": True, "manual_only": True, "requirements": scholar_mod.REQUIREMENTS, "env": []},
        "external_ai": {"enabled": False,
                        "note": "קורות החיים אינם נשלחים לשירותי AI חיצוניים. החילוץ מתבצע מקומית בלבד."},
    }


@router.post("/publications/{pub_id}/search/{provider}")
def search(pub_id: int, provider: str, db: Session = Depends(get_db), user: User = Depends(require_role(*EDIT))):
    _provider(provider)
    p = _pub(db, pub_id)
    try:
        search_provider(db, p, adapter_for(provider), user.username)
    except AdapterNotConfigured as e:
        raise HTTPException(412, f"המאגר אינו מוגדר. נדרש: {e}")
    except AdapterError as e:
        raise HTTPException(502, str(e))
    db.commit()
    db.refresh(p)
    return publication_out(p, get_policy(db, p.case), detail=True)


@router.post("/cases/{case_id}/search/{provider}")
def search_all(case_id: int, provider: str, db: Session = Depends(get_db), user: User = Depends(require_role(*EDIT))):
    """Search every included, not-yet-found publication. Stops on the first credential/quota error."""
    _provider(provider)
    from ..services.classify_pub import inclusion

    c = load_case(db, case_id)
    pol = get_policy(db, c)
    adapter = adapter_for(provider)
    done, errors = 0, []
    for p in c.publications:
        if not inclusion(p, pol)[0]:
            continue
        chk = next((x for x in p.checks if x.provider == provider), None)
        if chk and chk.status in ("found", "not_indexed"):
            continue
        try:
            search_provider(db, p, adapter, user.username)
            done += 1
            db.commit()
        except AdapterNotConfigured as e:
            raise HTTPException(412, f"המאגר אינו מוגדר. נדרש: {e}")
        except AdapterError as e:
            errors.append(f"פרסום {p.seq}: {e}")
            break
    return {"searched": done, "errors": errors}


class SelectIn(BaseModel):
    record_id: int


@router.post("/publications/{pub_id}/select/{provider}")
def select_record(pub_id: int, provider: str, data: SelectIn, db: Session = Depends(get_db),
                  user: User = Depends(require_role(*EDIT))):
    _provider(provider)
    p = _pub(db, pub_id)
    rec = db.get(SourceRecord, data.record_id)
    if not rec or rec.publication_id != p.id or rec.provider != provider:
        raise HTTPException(404, "רשומה לא נמצאה")
    for r in p.candidates:
        if r.provider == provider and r.record_status == "selected":
            r.record_status = "candidate"
    rec.record_status = "selected"
    chk = get_check(db, p, provider)
    chk.selected_record_id, chk.status = rec.id, "found"
    chk.checked_at, chk.checked_by = datetime.now(timezone.utc), user.username
    chk.notes = f"נבחר ידנית על ידי {user.username}"
    log(db, user.username, "provider_check", "select_record", p.id, p.case_id, provider=provider,
        record_id=rec.record_id, confidence=rec.confidence)
    reclassify(db, p.case, p, get_policy(db, p.case), provider)
    db.commit()
    db.refresh(p)
    return publication_out(p, get_policy(db, p.case), detail=True)


class StatusIn(BaseModel):
    status: str  # not_checked | not_indexed | needs_verification
    notes: str = ""


@router.post("/publications/{pub_id}/status/{provider}")
def set_status(pub_id: int, provider: str, data: StatusIn, db: Session = Depends(get_db),
               user: User = Depends(require_role(*EDIT))):
    _provider(provider)
    if data.status not in ("not_checked", "not_indexed", "needs_verification"):
        raise HTTPException(400, "סטטוס לא חוקי")
    p = _pub(db, pub_id)
    chk = get_check(db, p, provider)
    for r in p.candidates:
        if r.provider == provider and r.record_status == "selected":
            r.record_status = "candidate"
    chk.status, chk.selected_record_id, chk.notes = data.status, None, data.notes
    chk.checked_at = datetime.now(timezone.utc) if data.status != "not_checked" else None
    chk.checked_by = user.username
    log(db, user.username, "provider_check", "set_status", p.id, p.case_id, provider=provider, status=data.status, notes=data.notes)
    db.commit()
    db.refresh(p)
    return publication_out(p, get_policy(db, p.case), detail=True)


class ManualRecordIn(BaseModel):
    total_citations: int
    source_url: str = ""
    record_id: str = ""
    found_title: str = ""
    notes: str = ""


@router.post("/publications/{pub_id}/manual/{provider}")
def manual_record(pub_id: int, provider: str, data: ManualRecordIn, db: Session = Depends(get_db),
                  user: User = Depends(require_role(*EDIT))):
    """Manual entry of a verified record (required for Google Scholar; allowed as fallback for others)."""
    _provider(provider)
    if data.total_citations < 0:
        raise HTTPException(400, "מספר ציטוטים לא חוקי")
    p = _pub(db, pub_id)
    if provider == "scholar" and data.source_url and not GoogleScholarAdapter.is_scholar_url(data.source_url):
        raise HTTPException(400, "הקישור אינו לכתובת Google Scholar")
    rid = data.record_id or (GoogleScholarAdapter.cluster_id_from_url(data.source_url) if provider == "scholar" else "")
    for r in p.candidates:
        if r.provider == provider and r.record_status == "selected":
            r.record_status = "candidate"
    rec = SourceRecord(publication_id=p.id, provider=provider, record_id=rid, found_title=data.found_title or p.title,
                       found_authors=[], found_year=p.year, found_doi=p.doi, confidence=1.0,
                       confidence_explanation=f"אומת ידנית על ידי {user.username}", total_citations=data.total_citations,
                       source_url=data.source_url, method="manual", entered_by=user.username, record_status="selected")
    db.add(rec)
    db.flush()
    chk = get_check(db, p, provider)
    chk.selected_record_id, chk.status = rec.id, "found"
    chk.checked_at, chk.checked_by, chk.notes = datetime.now(timezone.utc), user.username, data.notes
    log(db, user.username, "provider_check", "manual_record", p.id, p.case_id, provider=provider,
        total=data.total_citations, url=data.source_url)
    db.commit()
    db.refresh(p)
    return publication_out(p, get_policy(db, p.case), detail=True)


class TotalIn(BaseModel):
    total_citations: int
    notes: str = ""


@router.post("/publications/{pub_id}/total/{provider}")
def update_total(pub_id: int, provider: str, data: TotalIn, db: Session = Depends(get_db),
                 user: User = Depends(require_role(*EDIT))):
    """Correct/refresh the total count of the selected record (keeps history in the log)."""
    p = _pub(db, pub_id)
    chk = get_check(db, p, provider)
    if not chk.selected_record:
        raise HTTPException(409, "אין רשומה נבחרת")
    old = chk.selected_record.total_citations
    chk.selected_record.total_citations = data.total_citations
    chk.checked_at, chk.checked_by = datetime.now(timezone.utc), user.username
    log(db, user.username, "provider_check", "update_total", p.id, p.case_id, provider=provider, old=old,
        new=data.total_citations, notes=data.notes)
    db.commit()
    db.refresh(p)
    return publication_out(p, get_policy(db, p.case), detail=True)


# ---------------------------------------------------------------- citing records

@router.post("/publications/{pub_id}/citing/{provider}/fetch")
def fetch_citing(pub_id: int, provider: str, db: Session = Depends(get_db), user: User = Depends(require_role(*EDIT))):
    _provider(provider)
    p = _pub(db, pub_id)
    chk = get_check(db, p, provider)
    if chk.status != "found" or not chk.selected_record:
        raise HTTPException(409, "יש לבחור רשומה מאומתת לפני משיכת המצטטים")
    adapter = adapter_for(provider)
    try:
        res = adapter.citing(chk.selected_record.record_id)
    except AdapterNotConfigured as e:
        raise HTTPException(412, f"המאגר אינו מוגדר. נדרש: {e}")
    except AdapterError as e:
        raise HTTPException(502, str(e))
    added, skipped = add_citing(db, p, provider, res.records, "api", res.note)
    chk.citing_list_status = res.status
    reclassify(db, p.case, p, get_policy(db, p.case), provider)
    log(db, user.username, "citing", "fetch_api", p.id, p.case_id, provider=provider, added=added,
        skipped=skipped, status=res.status, note=res.note)
    db.commit()
    return {"added": added, "skipped_duplicates": skipped, "status": res.status, "note": res.note}


@router.post("/publications/{pub_id}/citing/{provider}/import")
def import_citing(pub_id: int, provider: str, file: UploadFile = File(...), list_complete: bool = Form(False),
                  db: Session = Depends(get_db), user: User = Depends(require_role(*EDIT))):
    """Import a citing list (CSV/TSV/XLSX) for one publication in one database."""
    _provider(provider)
    p = _pub(db, pub_id)
    path, name, sha = _save_upload(file, get_settings().uploads_dir / f"case_{p.case_id}" / "citing",
                                   (".csv", ".txt", ".tsv", ".xlsx"))
    rows, warnings = parse_citing_file(path)
    if not rows and warnings:
        raise HTTPException(400, "; ".join(warnings))
    added, skipped = add_citing(db, p, provider, [r.__dict__ for r in rows], "import", f"{name} (sha256 {sha[:12]})")
    chk = get_check(db, p, provider)
    chk.citing_list_status = "complete" if list_complete else "partial"
    reclassify(db, p.case, p, get_policy(db, p.case), provider)
    log(db, user.username, "citing", "import_file", p.id, p.case_id, provider=provider, filename=name, sha256=sha,
        added=added, skipped=skipped, declared_complete=list_complete)
    db.commit()
    return {"added": added, "skipped_duplicates": skipped, "warnings": warnings}


@router.post("/cases/{case_id}/citing/{provider}/import")
def import_citing_bulk(case_id: int, provider: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                       user: User = Depends(require_role(*EDIT))):
    """Bulk import: each row names its publication in a 'publication' column (internal # or CV number)."""
    _provider(provider)
    c = load_case(db, case_id)
    path, name, sha = _save_upload(file, get_settings().uploads_dir / f"case_{c.id}" / "citing",
                                   (".csv", ".txt", ".tsv", ".xlsx"))
    rows, warnings = parse_citing_file(path)
    by_seq = {str(p.seq): p for p in c.publications}
    by_num = {}
    for p in c.publications:
        if p.original_number:
            by_num.setdefault(p.original_number, []).append(p)
    grouped: dict[int, list] = {}
    for r in rows:
        t = r.target.strip().lstrip("#")
        target = None
        if t.startswith("cv:"):
            m = by_num.get(t[3:])
            if m and len(m) == 1:
                target = m[0]
            elif m:
                warnings.append(f"שורה {r.row_number}: מספר {t[3:]} מופיע בכמה קטגוריות — יש להשתמש במספר פנימי")
        else:
            target = by_seq.get(t)
        if not target:
            warnings.append(f"שורה {r.row_number}: לא זוהה הפרסום המצוטט ('{r.target}') — השורה לא יובאה")
            continue
        grouped.setdefault(target.id, []).append(r.__dict__)
    total_added = 0
    pol = get_policy(db, c)
    for pid, items in grouped.items():
        p = db.get(Publication, pid)
        added, _ = add_citing(db, p, provider, items, "import", f"{name} (sha256 {sha[:12]})")
        total_added += added
        chk = get_check(db, p, provider)
        if chk.citing_list_status in ("none", "unavailable"):
            chk.citing_list_status = "partial"
        reclassify(db, c, p, pol, provider)
    log(db, user.username, "citing", "import_bulk", None, c.id, provider=provider, filename=name, sha256=sha,
        added=total_added, publications=len(grouped))
    db.commit()
    return {"added": total_added, "publications": len(grouped), "warnings": warnings}


class CitingIn(BaseModel):
    title: str
    doi: str = ""
    external_id: str = ""
    year: int | None = None
    authors: list[dict] = []
    authors_complete: bool = True
    source_url: str = ""


@router.post("/publications/{pub_id}/citing/{provider}")
def add_citing_manual(pub_id: int, provider: str, data: CitingIn, db: Session = Depends(get_db),
                      user: User = Depends(require_role(*EDIT))):
    _provider(provider)
    p = _pub(db, pub_id)
    added, skipped = add_citing(db, p, provider, [data.model_dump()], "manual", f"הוזן ידנית על ידי {user.username}")
    if skipped:
        raise HTTPException(409, "רשומת מצטט זהה כבר קיימת במאגר זה")
    reclassify(db, p.case, p, get_policy(db, p.case), provider)
    chk = get_check(db, p, provider)
    if chk.citing_list_status in ("none", "unavailable"):
        chk.citing_list_status = "partial"
    log(db, user.username, "citing", "add_manual", p.id, p.case_id, provider=provider, title=data.title)
    db.commit()
    return {"ok": True}


class ListStatusIn(BaseModel):
    citing_list_status: str


@router.post("/publications/{pub_id}/citing/{provider}/list-status")
def set_list_status(pub_id: int, provider: str, data: ListStatusIn, db: Session = Depends(get_db),
                    user: User = Depends(require_role(*EDIT))):
    if data.citing_list_status not in ("none", "partial", "complete", "unavailable"):
        raise HTTPException(400, "ערך לא חוקי")
    p = _pub(db, pub_id)
    chk = get_check(db, p, provider)
    chk.citing_list_status = data.citing_list_status
    log(db, user.username, "citing", "list_status", p.id, p.case_id, provider=provider, status=data.citing_list_status)
    db.commit()
    return {"ok": True}


@router.get("/publications/{pub_id}/citing")
def list_citing(pub_id: int, provider: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    p = _pub(db, pub_id)
    return [citing_out(c) for c in p.citing if not provider or c.provider == provider]


class CitingPatch(BaseModel):
    manual_a: str | None = None
    manual_b: str | None = None
    clear_a: bool = False
    clear_b: bool = False
    manual_note: str = ""
    confirm: bool | None = None
    authors: list[dict] | None = None
    authors_complete: bool | None = None


@router.patch("/citing/{citing_id}")
def patch_citing(citing_id: int, data: CitingPatch, db: Session = Depends(get_db), user: User = Depends(require_role(*EDIT, "reviewer"))):
    c = db.get(CitingRecord, citing_id)
    if not c:
        raise HTTPException(404, "רשומה לא נמצאה")
    for v in (data.manual_a, data.manual_b):
        if v is not None and v not in CLASSIFICATIONS:
            raise HTTPException(400, "סיווג לא חוקי")
    if (data.manual_a or data.manual_b) and not data.manual_note.strip():
        raise HTTPException(400, "יש לנמק שינוי סיווג ידני")
    changes = {}
    if data.authors is not None:
        changes["authors"] = [c.authors, data.authors]
        c.authors = data.authors
    if data.authors_complete is not None:
        changes["authors_complete"] = [c.authors_complete, data.authors_complete]
        c.authors_complete = data.authors_complete
    if data.authors is not None or data.authors_complete is not None:
        reclassify(db, c.publication.case, c.publication, get_policy(db, c.publication.case), c.provider)
    if data.manual_a is not None:
        changes["manual_a"] = [c.manual_a, data.manual_a]
        c.manual_a = data.manual_a
    if data.manual_b is not None:
        changes["manual_b"] = [c.manual_b, data.manual_b]
        c.manual_b = data.manual_b
    if data.clear_a:
        changes["manual_a"] = [c.manual_a, None]
        c.manual_a = None
    if data.clear_b:
        changes["manual_b"] = [c.manual_b, None]
        c.manual_b = None
    if data.manual_note:
        c.manual_note = data.manual_note
    if data.confirm is not None:
        c.manually_confirmed = data.confirm
        c.confirmed_by = user.username if data.confirm else ""
        c.confirmed_at = datetime.now(timezone.utc) if data.confirm else None
        changes["confirmed"] = data.confirm
    log(db, user.username, "citing", "classify", c.id, c.publication.case_id, changes=changes, note=data.manual_note)
    db.commit()
    return citing_out(c)


@router.delete("/citing/{citing_id}")
def delete_citing(citing_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(*EDIT))):
    c = db.get(CitingRecord, citing_id)
    if not c:
        raise HTTPException(404, "רשומה לא נמצאה")
    log(db, user.username, "citing", "delete", c.id, c.publication.case_id, title=c.title, provider=c.provider)
    db.delete(c)
    db.commit()
    return {"ok": True}
