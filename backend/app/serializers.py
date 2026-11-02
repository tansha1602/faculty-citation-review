from __future__ import annotations

from .adapters.scholar import GoogleScholarAdapter
from .services.classify_pub import inclusion
from .services.metrics import publication_metrics, summary


def iso(dt):
    return dt.isoformat() if dt else None


def user_out(u):
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role, "active": u.active}


def policy_out(p):
    return {"id": p.id, "case_id": p.case_id, "included_languages": p.included_languages,
            "included_statuses": p.included_statuses, "included_types": p.included_types,
            "self_citation_definition": p.self_citation_definition,
            "full_name_match_is_self": p.full_name_match_is_self, "summary_mode": p.summary_mode,
            "updated_at": iso(p.updated_at), "updated_by": p.updated_by}


def case_out(c, with_counts=True):
    d = {"id": c.id, "researcher_name_en": c.researcher_name_en, "researcher_name_he": c.researcher_name_he,
         "name_variants": c.name_variants or [], "orcid": c.orcid, "scopus_author_id": c.scopus_author_id,
         "wos_researcher_id": c.wos_researcher_id, "notes": c.notes, "cv_filename": c.cv_filename,
         "cv_sha256": c.cv_sha256, "cv_uploaded_at": iso(c.cv_uploaded_at), "template_filename": c.template_filename,
         "extraction_confirmed": c.extraction_confirmed, "created_by": c.created_by, "created_at": iso(c.created_at),
         "prepared_by": c.prepared_by, "prepared_at": iso(c.prepared_at), "reviewed_by": c.reviewed_by,
         "reviewed_at": iso(c.reviewed_at), "review_note": c.review_note}
    if with_counts:
        d["publication_count"] = len(c.publications)
    return d


def source_record_out(r):
    return {"id": r.id, "provider": r.provider, "record_id": r.record_id, "found_title": r.found_title,
            "found_authors": r.found_authors, "found_year": r.found_year, "found_doi": r.found_doi,
            "confidence": r.confidence, "confidence_explanation": r.confidence_explanation,
            "total_citations": r.total_citations, "retrieved_at": iso(r.retrieved_at), "record_status": r.record_status,
            "source_url": r.source_url, "method": r.method, "entered_by": r.entered_by}


def check_out(c):
    return {"provider": c.provider, "status": c.status, "selected_record_id": c.selected_record_id,
            "checked_at": iso(c.checked_at), "checked_by": c.checked_by, "citing_list_status": c.citing_list_status,
            "notes": c.notes}


def citing_out(c):
    return {"id": c.id, "publication_id": c.publication_id, "provider": c.provider, "title": c.title, "doi": c.doi,
            "external_id": c.external_id, "year": c.year, "authors": c.authors, "authors_complete": c.authors_complete,
            "source_url": c.source_url, "origin": c.origin, "origin_detail": c.origin_detail,
            "class_a": c.class_a, "explain_a": c.explain_a, "class_b": c.class_b, "explain_b": c.explain_b,
            "manual_a": c.manual_a, "manual_b": c.manual_b, "manual_note": c.manual_note,
            "final_a": c.final("A"), "final_b": c.final("B"),
            "manually_confirmed": c.manually_confirmed, "confirmed_by": c.confirmed_by,
            "confirmed_at": iso(c.confirmed_at)}


def publication_out(p, policy, detail=False):
    inc, reason = inclusion(p, policy)
    d = {"id": p.id, "seq": p.seq, "original_number": p.original_number, "raw_text": p.raw_text,
         "section": p.section, "subsection": p.subsection, "title": p.title, "authors": p.authors or [],
         "year": p.year, "venue": p.venue, "pub_type": p.pub_type, "language": p.language,
         "language_evidence": p.language_evidence, "doi": p.doi, "cv_page": p.cv_page, "pub_status": p.pub_status,
         "status_evidence": p.status_evidence, "manual_include": p.manual_include,
         "manual_include_reason": p.manual_include_reason, "manually_edited": p.manually_edited, "notes": p.notes,
         "included": inc, "exclusion_reason": reason,
         "scholar_search_url": GoogleScholarAdapter.search_url(p.title, (p.authors or [""])[0], p.year)}
    if detail:
        ms = publication_metrics(p, policy.self_citation_definition)
        d["metrics"] = {k: v.to_dict() for k, v in ms.items()}
        sm = summary(p, ms, policy.summary_mode, policy.self_citation_definition)
        d["summary"] = sm.__dict__
        d["checks"] = {c.provider: check_out(c) for c in p.checks}
        d["candidates"] = [source_record_out(r) for r in p.candidates]
        d["citing_count"] = {prov: sum(1 for c in p.citing if c.provider == prov) for prov in ("wos", "scopus", "scholar")}
    return d
