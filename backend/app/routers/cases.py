"""Screens 1-3: case, CV upload, extraction review, policy."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import log
from ..auth import current_user, require_role
from ..config import get_settings
from ..db import get_db
from ..models import LANGUAGES, PUB_STATUSES, PUB_TYPES, Case, Publication, User
from ..serializers import case_out, policy_out, publication_out
from ..services.cv_parser import extract_publications
from ..services.workflow import apply_extraction, default_policy, get_policy, reclassify

router = APIRouter(prefix="/api", tags=["cases"])
MAX_UPLOAD = 25 * 1024 * 1024


class CaseIn(BaseModel):
    researcher_name_en: str
    researcher_name_he: str = ""
    name_variants: list[str] = []
    orcid: str = ""
    scopus_author_id: str = ""
    wos_researcher_id: str = ""
    notes: str = ""


class PublicationPatch(BaseModel):
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    venue: str | None = None
    pub_type: str | None = None
    language: str | None = None
    doi: str | None = None
    cv_page: int | None = None
    pub_status: str | None = None
    original_number: str | None = None
    subsection: str | None = None
    manual_include: bool | None = None
    clear_manual_include: bool = False
    manual_include_reason: str | None = None
    notes: str | None = None


class PublicationNew(BaseModel):
    raw_text: str
    after_seq: int | None = None
    subsection: str = ""
    original_number: str = ""


class PolicyIn(BaseModel):
    included_languages: list[str]
    included_statuses: list[str]
    included_types: list[str]
    self_citation_definition: str
    full_name_match_is_self: bool
    summary_mode: str


def load_case(db: Session, case_id: int) -> Case:
    c = db.get(Case, case_id)
    if not c:
        raise HTTPException(404, "תיק לא נמצא")
    return c


def _save_upload(file: UploadFile, folder: Path, allowed: tuple[str, ...]) -> tuple[Path, str, str]:
    name = Path(file.filename or "upload").name
    suffix = Path(name).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"סוג קובץ לא נתמך. מותר: {', '.join(allowed)}")
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(400, "הקובץ גדול מדי (מעל 25MB)")
    sha = hashlib.sha256(data).hexdigest()
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-]", "_", name)
    path = folder / f"{datetime.now(timezone.utc):%Y%m%d%H%M%S}_{sha[:8]}_{safe}"
    path.write_bytes(data)
    return path, name, sha


@router.get("/cases")
def list_cases(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [case_out(c) for c in db.scalars(select(Case).order_by(Case.created_at.desc()))]


@router.post("/cases")
def create_case(data: CaseIn, db: Session = Depends(get_db), user: User = Depends(require_role("admin", "librarian"))):
    c = Case(**data.model_dump(), created_by=user.username)
    db.add(c)
    db.flush()
    get_policy(db, c)
    log(db, user.username, "case", "create", c.id, c.id, researcher=data.researcher_name_en)
    db.commit()
    return case_out(c)


@router.get("/cases/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return case_out(load_case(db, case_id))


@router.put("/cases/{case_id}")
def update_case(case_id: int, data: CaseIn, db: Session = Depends(get_db), user: User = Depends(require_role("admin", "librarian"))):
    c = load_case(db, case_id)
    before = case_out(c, with_counts=False)
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    changed = {k: [before[k], v] for k, v in data.model_dump().items() if before.get(k) != v}
    log(db, user.username, "case", "update", c.id, c.id, changes=changed)
    # identity data changed -> re-run self-citation classification
    pol = get_policy(db, c)
    for p in c.publications:
        reclassify(db, c, p, pol)
    db.commit()
    return case_out(c)


@router.delete("/cases/{case_id}")
def delete_case(case_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))):
    c = load_case(db, case_id)
    log(db, user.username, "case", "delete", c.id, c.id, researcher=c.researcher_name_en)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/cases/{case_id}/cv")
def upload_cv(case_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
              user: User = Depends(require_role("admin", "librarian"))):
    c = load_case(db, case_id)
    path, name, sha = _save_upload(file, get_settings().uploads_dir / f"case_{c.id}", (".pdf", ".docx"))
    try:
        result = extract_publications(path)
    except Exception as e:  # corrupt file etc.
        raise HTTPException(400, f"לא ניתן לקרוא את הקובץ: {e}")
    c.cv_filename, c.cv_path, c.cv_sha256, c.cv_uploaded_at = name, str(path), sha, datetime.now(timezone.utc)
    n = apply_extraction(db, c, result, user.username)
    log(db, user.username, "case", "upload_cv", c.id, c.id, filename=name, sha256=sha)
    db.commit()
    return {"count": n, "section_found": result.section_found, "section_heading": result.section_heading,
            "warnings": result.warnings}


@router.post("/cases/{case_id}/template")
def upload_template(case_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                    user: User = Depends(require_role("admin", "librarian"))):
    c = load_case(db, case_id)
    path, name, sha = _save_upload(file, get_settings().uploads_dir / f"case_{c.id}", (".xlsx",))
    import openpyxl
    try:
        openpyxl.load_workbook(path).close()
    except Exception as e:
        raise HTTPException(400, f"קובץ Excel לא תקין: {e}")
    c.template_filename, c.template_path = name, str(path)
    log(db, user.username, "case", "upload_template", c.id, c.id, filename=name, sha256=sha)
    db.commit()
    return case_out(c)


@router.get("/cases/{case_id}/publications")
def list_publications(case_id: int, detail: bool = False, db: Session = Depends(get_db), _: User = Depends(current_user)):
    c = load_case(db, case_id)
    pol = get_policy(db, c)
    db.commit()
    return [publication_out(p, pol, detail=detail) for p in c.publications]


@router.get("/publications/{pub_id}")
def get_publication(pub_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    p = db.get(Publication, pub_id)
    if not p:
        raise HTTPException(404, "פרסום לא נמצא")
    return publication_out(p, get_policy(db, p.case), detail=True)


@router.patch("/publications/{pub_id}")
def patch_publication(pub_id: int, data: PublicationPatch, db: Session = Depends(get_db),
                      user: User = Depends(require_role("admin", "librarian"))):
    p = db.get(Publication, pub_id)
    if not p:
        raise HTTPException(404, "פרסום לא נמצא")
    vals = data.model_dump(exclude_unset=True)
    for key, allowed in (("pub_type", PUB_TYPES), ("language", LANGUAGES), ("pub_status", PUB_STATUSES)):
        if key in vals and vals[key] not in allowed:
            raise HTTPException(400, f"ערך לא חוקי: {key}")
    if "manual_include" in vals and vals["manual_include"] is not None and not (vals.get("manual_include_reason") or p.manual_include_reason):
        raise HTTPException(400, "יש לציין סיבה להכללה/החרגה ידנית")
    changes = {}
    clear = vals.pop("clear_manual_include", False)
    for k, v in vals.items():
        old = getattr(p, k)
        if old != v:
            changes[k] = [old, v]
            setattr(p, k, v)
    if clear:
        changes["manual_include"] = [p.manual_include, None]
        p.manual_include, p.manual_include_reason = None, ""
    if changes:
        p.manually_edited = True
        if "language" in changes:
            p.language_evidence = f"תוקן ידנית על ידי {user.username}"
        if "pub_status" in changes:
            p.status_evidence = f"תוקן ידנית על ידי {user.username}"
        log(db, user.username, "publication", "edit", p.id, p.case_id, changes=changes)
        if "authors" in changes:
            reclassify(db, p.case, p, get_policy(db, p.case))
    db.commit()
    return publication_out(p, get_policy(db, p.case))


@router.post("/cases/{case_id}/publications")
def add_publication(case_id: int, data: PublicationNew, db: Session = Depends(get_db),
                    user: User = Depends(require_role("admin", "librarian"))):
    """Add an entry the parser missed (e.g. a scanned page)."""
    from ..services.classify_pub import detect_language, detect_status, detect_type
    from ..services.cv_parser import extract_fields

    c = load_case(db, case_id)
    pos = data.after_seq if data.after_seq is not None else len(c.publications)
    for p in c.publications:
        if p.seq > pos:
            p.seq += 1
    f = extract_fields(data.raw_text)
    sec = c.publications[0].section if c.publications else "PUBLICATIONS"
    lang, lev = detect_language(data.raw_text, f["title"], f["venue"], sec, data.subsection)
    st, sev = detect_status(data.raw_text, sec, data.subsection)
    p = Publication(case_id=c.id, seq=pos + 1, raw_text=data.raw_text, section=sec, subsection=data.subsection,
                    original_number=data.original_number, pub_type=detect_type(sec, data.subsection, data.raw_text),
                    language=lang, language_evidence=lev, pub_status=st, status_evidence=sev, manually_edited=True, **f)
    db.add(p)
    db.flush()
    log(db, user.username, "publication", "add_manual", p.id, c.id, raw_text=data.raw_text[:300])
    db.commit()
    db.refresh(c)
    return publication_out(p, get_policy(db, c))


@router.delete("/publications/{pub_id}")
def delete_publication(pub_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("admin", "librarian"))):
    """Only for parser errors (e.g. a heading extracted as an entry). Exclusions use manual_include=False."""
    p = db.get(Publication, pub_id)
    if not p:
        raise HTTPException(404, "פרסום לא נמצא")
    if p.citing or any(ch.status != "not_checked" for ch in p.checks):
        raise HTTPException(409, "לפרסום יש נתוני בדיקה. יש להחריג אותו (עם סיבה) במקום למחוק.")
    case = p.case
    log(db, user.username, "publication", "delete_parse_error", p.id, p.case_id, raw_text=p.raw_text[:300])
    db.delete(p)
    db.flush()
    for i, q in enumerate(sorted(case.publications, key=lambda x: x.seq), start=1):
        q.seq = i
    db.commit()
    return {"ok": True}


@router.post("/cases/{case_id}/confirm-extraction")
def confirm_extraction(case_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("admin", "librarian"))):
    c = load_case(db, case_id)
    c.extraction_confirmed = True
    log(db, user.username, "case", "confirm_extraction", c.id, c.id, count=len(c.publications))
    db.commit()
    return case_out(c)


# ---------------------------------------------------------------- policy

def _validate_policy(data: PolicyIn):
    if not set(data.included_languages) <= set(LANGUAGES) or not set(data.included_statuses) <= set(PUB_STATUSES) \
            or not set(data.included_types) <= set(PUB_TYPES):
        raise HTTPException(400, "ערכי מדיניות לא חוקיים")
    if data.self_citation_definition not in ("A", "B") or data.summary_mode not in ("sum", "unique", "max", "empty"):
        raise HTTPException(400, "ערכי מדיניות לא חוקיים")


@router.get("/policy/default")
def get_default_policy(db: Session = Depends(get_db), _: User = Depends(current_user)):
    p = default_policy(db)
    db.commit()
    return policy_out(p)


@router.put("/policy/default")
def put_default_policy(data: PolicyIn, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))):
    _validate_policy(data)
    p = default_policy(db)
    before = policy_out(p)
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    p.updated_by = user.username
    log(db, user.username, "policy", "update_default", p.id, None, before=before, after=data.model_dump())
    db.commit()
    return policy_out(p)


@router.get("/cases/{case_id}/policy")
def get_case_policy(case_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    p = get_policy(db, load_case(db, case_id))
    db.commit()
    return policy_out(p)


@router.put("/cases/{case_id}/policy")
def put_case_policy(case_id: int, data: PolicyIn, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))):
    """Only an administrator may change the inclusion / self-citation policy."""
    _validate_policy(data)
    c = load_case(db, case_id)
    p = get_policy(db, c)
    before = policy_out(p)
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    p.updated_by = user.username
    log(db, user.username, "policy", "update_case", p.id, c.id, before=before, after=data.model_dump())
    if before["full_name_match_is_self"] != data.full_name_match_is_self:
        for pub in c.publications:
            reclassify(db, c, pub, p)
    db.commit()
    return policy_out(p)
