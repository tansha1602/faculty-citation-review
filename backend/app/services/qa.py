"""Quality-control checks before the report is delivered (procedure stage F)."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .classify_pub import inclusion
from .metrics import PROVIDER_LABEL, publication_metrics
from .names import SAME, compare_person_to_author
from .self_citation import researcher_variants


def _issue(level, code, message, publication_id=None, provider=None):
    return {"level": level, "code": code, "message": message, "publication_id": publication_id, "provider": provider}


def run_qa(case, policy) -> dict:
    issues = []
    pubs = list(case.publications)
    researcher = researcher_variants(case.researcher_name_en, case.name_variants, case.orcid,
                                     case.scopus_author_id, case.wos_researcher_id)
    if not pubs:
        issues.append(_issue("error", "no_publications", "לא חולצו פרסומים מקורות החיים"))
    if not case.extraction_confirmed:
        issues.append(_issue("error", "extraction_not_confirmed", "רשימת הפרסומים שחולצה טרם אושרה (מסך 2)"))
    included = [p for p in pubs if inclusion(p, policy)[0]]
    stats = {"publications": len(pubs), "included": len(included), "excluded": len(pubs) - len(included),
             "complete_cells": 0, "partial_cells": 0, "not_checked": 0, "needs_verification": 0, "not_indexed": 0}

    for p in pubs:
        if not p.raw_text.strip():
            issues.append(_issue("error", "empty_text", f"פרסום {p.seq}: טקסט ריק", p.id))
        if not inclusion(p, policy)[0] and p.manual_include is None and p.pub_status == "accepted":
            issues.append(_issue("info", "accepted_excluded", f"פרסום {p.seq} במצב Accepted הוחרג — ייתכן שכבר זמין ומצוטט", p.id))

    for p in included:
        label = f"פרסום {p.original_number or p.seq}"
        if p.authors and not any(compare_person_to_author(researcher, {"name": a}).result == SAME or
                                 compare_person_to_author(researcher, {"name": a}).basis in ("initials",)
                                 for a in p.authors):
            issues.append(_issue("warning", "researcher_not_author",
                                 f"{label}: החוקר/ת לא זוהה/תה ברשימת המחברים שחולצה — לוודא שייכות", p.id))
        if not p.title:
            issues.append(_issue("warning", "missing_title", f"{label}: חסרה כותרת", p.id))
        if not p.doi:
            issues.append(_issue("info", "missing_doi", f"{label}: אין DOI — זיהוי לפי כותרת, מחבר ושנה", p.id))
        ms = publication_metrics(p, policy.self_citation_definition)
        for prov, m in ms.items():
            name = PROVIDER_LABEL[prov]
            if m.status == "not_checked":
                stats["not_checked"] += 1
                issues.append(_issue("error", "not_checked", f"{label}: לא נבדק ב-{name}", p.id, prov))
            elif m.status == "needs_verification":
                stats["needs_verification"] += 1
                issues.append(_issue("error", "record_unverified", f"{label}: הרשומה ב-{name} דורשת אימות", p.id, prov))
            elif m.status == "not_indexed":
                stats["not_indexed"] += 1
            else:
                if not m.checked_at:
                    issues.append(_issue("warning", "missing_date", f"{label}: חסר תאריך איסוף ב-{name}", p.id, prov))
                if m.complete:
                    stats["complete_cells"] += 1
                    if m.citing_records == m.total and m.self_selected + m.non_self_selected != m.total:
                        issues.append(_issue("error", "sum_mismatch",
                                             f"{label}: ב-{name} עצמיים+לא עצמיים ≠ סך הציטוטים", p.id, prov))
                else:
                    stats["partial_cells"] += 1
                    issues.append(_issue("warning", "incomplete",
                                         f"{label}: ב-{name} הבדיקה לא הושלמה — {m.unresolved_selected} ציטוטים לא מסווגים", p.id, prov))
                for w in m.warnings:
                    if "גדול מסך" in w:
                        issues.append(_issue("warning", "count_drift", f"{label}: {name}: {w}", p.id, prov))
        # same record selected for two publications in the same database
    seen: dict[tuple[str, str], int] = {}
    for p in included:
        for c in p.checks:
            if c.selected_record and c.selected_record.record_id:
                key = (c.provider, c.selected_record.record_id)
                if key in seen and seen[key] != p.id:
                    issues.append(_issue("error", "duplicate_record",
                                         f"אותה רשומה ב-{PROVIDER_LABEL[c.provider]} ({key[1]}) נבחרה לשני פרסומים", p.id, c.provider))
                seen[key] = p.id

    # possible duplicate publications (warned, never merged automatically)
    for i, a in enumerate(included):
        for b in included[i + 1:]:
            if a.doi and b.doi and a.doi.lower() == b.doi.lower():
                issues.append(_issue("warning", "duplicate_doi", f"פרסומים {a.seq} ו-{b.seq} בעלי אותו DOI — לבדוק כפילות", a.id))
            elif a.title and b.title:
                s = SequenceMatcher(None, re.sub(r"\W", "", a.title.lower()), re.sub(r"\W", "", b.title.lower())).ratio()
                if s > 0.9:
                    issues.append(_issue("warning", "similar_titles",
                                         f"פרסומים {a.seq} ו-{b.seq} בעלי כותרות דומות ({s:.0%}) — לא אוחדו; לבדוק ידנית", a.id))

    manual_changes = sum(1 for p in pubs for c in p.citing if c.manual_a or c.manual_b)
    manual_changes += sum(1 for p in pubs if p.manual_include is not None)
    if manual_changes:
        issues.append(_issue("info", "manual_changes", f"{manual_changes} החלטות ידניות (הכללה/סיווג) — דורשות אישור עובד נוסף"))
    errors = sum(1 for i in issues if i["level"] == "error")
    warnings = sum(1 for i in issues if i["level"] == "warning")
    return {"issues": issues, "stats": stats, "errors": errors, "warnings": warnings,
            "ready": errors == 0, "manual_changes": manual_changes}
