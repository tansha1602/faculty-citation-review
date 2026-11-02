from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.base import Candidate, PubQuery, rank
from ..audit import log
from ..models import CitingRecord, Policy, ProviderCheck, Publication, SourceRecord
from .cv_parser import ExtractionResult
from .self_citation import classify, researcher_variants


def default_policy(db: Session) -> Policy:
    p = db.scalar(select(Policy).where(Policy.case_id.is_(None)))
    if not p:
        p = Policy(case_id=None)
        db.add(p)
        db.flush()
    return p


def get_policy(db: Session, case) -> Policy:
    p = db.scalar(select(Policy).where(Policy.case_id == case.id))
    if not p:
        d = default_policy(db)
        p = Policy(case_id=case.id, included_languages=list(d.included_languages),
                   included_statuses=list(d.included_statuses), included_types=list(d.included_types),
                   self_citation_definition=d.self_citation_definition,
                   full_name_match_is_self=d.full_name_match_is_self, summary_mode=d.summary_mode,
                   updated_by="(ברירת מחדל)")
        db.add(p)
        db.flush()
    return p


def apply_extraction(db: Session, case, result: ExtractionResult, username: str) -> int:
    for p in list(case.publications):
        db.delete(p)
    db.flush()
    for i, ep in enumerate(result.publications, start=1):
        db.add(Publication(
            case_id=case.id, seq=i, original_number=ep.original_number, raw_text=ep.raw_text, section=ep.section,
            subsection=ep.subsection, title=ep.title, authors=ep.authors, year=ep.year, venue=ep.venue,
            pub_type=ep.pub_type, language=ep.language, language_evidence=ep.language_evidence, doi=ep.doi,
            cv_page=ep.cv_page, pub_status=ep.pub_status, status_evidence=ep.status_evidence,
        ))
    case.extraction_confirmed = False
    log(db, username, "case", "extract_publications", case.id, case.id, count=len(result.publications),
        section_found=result.section_found, warnings=result.warnings)
    db.flush()
    db.refresh(case)
    return len(result.publications)


def get_check(db: Session, pub: Publication, provider: str) -> ProviderCheck:
    for c in pub.checks:
        if c.provider == provider:
            return c
    c = ProviderCheck(publication_id=pub.id, provider=provider)
    db.add(c)
    pub.checks.append(c)
    db.flush()
    return c


def original_authors(pub: Publication, provider: str) -> list[dict]:
    """Authors of the cited publication: the selected database record (with identifiers) if available,
    otherwise the names extracted from the CV."""
    for c in pub.checks:
        if c.provider == provider and c.selected_record and c.selected_record.found_authors:
            return c.selected_record.found_authors
    return [{"name": a} for a in (pub.authors or [])]


def reclassify(db: Session, case, pub: Publication, policy: Policy, provider: str | None = None) -> int:
    researcher = researcher_variants(case.researcher_name_en, case.name_variants, case.orcid,
                                     case.scopus_author_id, case.wos_researcher_id)
    n = 0
    for c in pub.citing:
        if provider and c.provider != provider:
            continue
        a, b = classify(researcher, original_authors(pub, c.provider), c.authors, c.authors_complete,
                        strict_names=not policy.full_name_match_is_self)
        c.class_a, c.explain_a, c.class_b, c.explain_b = a.result, a.explanation, b.result, b.explanation
        n += 1
    db.flush()
    return n


def store_candidates(db: Session, pub: Publication, provider: str, cands: list[Candidate], username: str,
                     auto: Candidate | None, reason: str) -> ProviderCheck:
    for old in [c for c in pub.candidates if c.provider == provider and c.record_status == "candidate" and c.method == "api"]:
        db.delete(old)
    db.flush()
    chk = get_check(db, pub, provider)
    chk.checked_at, chk.checked_by = datetime.now(timezone.utc), username
    selected = None
    for c in cands:
        rec = SourceRecord(publication_id=pub.id, provider=provider, record_id=c.record_id, found_title=c.title,
                           found_authors=c.authors, found_year=c.year, found_doi=c.doi, confidence=c.confidence,
                           confidence_explanation=c.confidence_explanation, total_citations=c.total_citations,
                           source_url=c.source_url, method="api", entered_by=username)
        db.add(rec)
        db.flush()
        if auto is c:
            selected = rec
    if selected:
        selected.record_status = "selected"
        chk.selected_record_id, chk.status = selected.id, "found"
        chk.notes = f"נבחר אוטומטית: {reason}"
    elif cands:
        chk.selected_record_id, chk.status = None, "needs_verification"
        chk.notes = reason
    else:
        # no automatic "not indexed": the librarian confirms it explicitly
        chk.selected_record_id, chk.status = None, "needs_verification"
        chk.notes = "לא נמצאו רשומות בחיפוש האוטומטי — יש לוודא ולסמן 'לא מאונדקס' ידנית"
    log(db, username, "provider_check", "search", pub.id, pub.case_id, provider=provider,
        candidates=len(cands), auto_selected=bool(selected), reason=reason)
    db.flush()
    return chk


def search_provider(db: Session, pub: Publication, adapter, username: str) -> ProviderCheck:
    q = PubQuery(title=pub.title, authors=pub.authors or [], year=pub.year, doi=pub.doi)
    cands = adapter.find(q)
    cands, auto, reason = rank(q, cands)
    return store_candidates(db, pub, adapter.provider, cands, username, auto, reason)


def add_citing(db: Session, pub: Publication, provider: str, rows: list[dict], origin: str, origin_detail: str) -> tuple[int, int]:
    """Insert citing records, skipping duplicates within the same database (each citing work counts once)."""
    existing = {(c.doi.lower() if c.doi else "") or (c.external_id or "") or c.title.lower().strip()
                for c in pub.citing if c.provider == provider}
    added = skipped = 0
    for r in rows:
        key = (r.get("doi") or "").lower() or (r.get("external_id") or "") or (r.get("title") or "").lower().strip()
        if key in existing:
            skipped += 1
            continue
        existing.add(key)
        rec = CitingRecord(publication_id=pub.id, provider=provider, title=r.get("title", ""), doi=r.get("doi", ""),
                           external_id=r.get("external_id", ""), year=r.get("year"), authors=r.get("authors", []),
                           authors_complete=bool(r.get("authors_complete", True)) and bool(r.get("authors")),
                           source_url=r.get("source_url", ""), origin=origin, origin_detail=origin_detail)
        db.add(rec)
        pub.citing.append(rec)
        added += 1
    db.flush()
    return added, skipped
