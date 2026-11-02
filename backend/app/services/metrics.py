"""Citation counts per publication and per database.

Each database is reported separately. Non-self = total - self only when every citing
record is classified; otherwise the result is partial and flagged as incomplete.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from ..models import PROVIDERS

STATUS_LABEL_HE = {
    "not_checked": "לא נבדק",
    "not_indexed": "לא מאונדקס",
    "needs_verification": "דורש אימות",
    "found": "נמצא",
}
PROVIDER_LABEL = {"wos": "Web of Science", "scopus": "Scopus", "scholar": "Google Scholar"}


@dataclass
class ProviderMetrics:
    provider: str
    status: str
    status_label: str
    record_id: str = ""
    source_url: str = ""
    checked_at: str | None = None
    total: int | None = None
    citing_records: int = 0
    self_a: int = 0
    self_b: int = 0
    non_self_a: int = 0
    non_self_b: int = 0
    unresolved_a: int = 0
    unresolved_b: int = 0
    missing_records: int = 0  # total - records available for classification
    definition: str = "A"
    self_selected: int | None = None
    non_self_selected: int | None = None
    unresolved_selected: int | None = None
    non_self_formula: int | None = None  # total - self, only when complete
    complete: bool = False
    citing_list_status: str = "none"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _check(pub, provider):
    for c in pub.checks:
        if c.provider == provider:
            return c
    return None


def provider_metrics(pub, provider: str, definition: str) -> ProviderMetrics:
    chk = _check(pub, provider)
    status = chk.status if chk else "not_checked"
    m = ProviderMetrics(provider=provider, status=status, status_label=STATUS_LABEL_HE[status], definition=definition)
    if chk:
        m.checked_at = chk.checked_at.isoformat() if chk.checked_at else None
        m.citing_list_status = chk.citing_list_status
    if status != "found":
        return m
    rec = chk.selected_record
    if rec is None:
        m.status, m.status_label = "needs_verification", STATUS_LABEL_HE["needs_verification"]
        m.warnings.append("סומן כנמצא אך לא נבחרה רשומה")
        return m
    m.record_id, m.source_url, m.total = rec.record_id, rec.source_url, rec.total_citations
    recs = [c for c in pub.citing if c.provider == provider]
    m.citing_records = len(recs)
    for c in recs:
        fa, fb = c.final("A"), c.final("B")
        m.self_a += fa == "self"
        m.non_self_a += fa == "non_self"
        m.unresolved_a += fa == "needs_verification"
        m.self_b += fb == "self"
        m.non_self_b += fb == "non_self"
        m.unresolved_b += fb == "needs_verification"
    if m.total is None:
        m.warnings.append("מספר הציטוטים הכולל לא הוזן")
    else:
        m.missing_records = max(m.total - m.citing_records, 0)
        if m.citing_records > m.total:
            m.warnings.append(f"מספר רשומות המצטטים ({m.citing_records}) גדול מסך הציטוטים במאגר ({m.total}) — לבדוק עדכניות")
        if m.missing_records:
            m.warnings.append(f"{m.missing_records} מתוך {m.total} ציטוטים אינם זמינים לסיווג (רשימת מצטטים חלקית או חסרה)")
    sel = (m.self_a, m.non_self_a, m.unresolved_a) if definition == "A" else (m.self_b, m.non_self_b, m.unresolved_b)
    m.self_selected, m.non_self_selected = sel[0], sel[1]
    m.unresolved_selected = sel[2] + m.missing_records
    m.complete = m.total is not None and m.unresolved_selected == 0
    if m.complete:
        m.non_self_formula = m.total - m.self_selected if m.citing_records <= m.total else m.non_self_selected
    return m


def publication_metrics(pub, definition: str) -> dict[str, ProviderMetrics]:
    return {p: provider_metrics(pub, p, definition) for p in PROVIDERS}


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def dedup_key(c) -> str:
    if c.doi:
        return "doi:" + c.doi.lower().strip()
    return f"t:{_norm_title(c.title)}:{c.year or ''}"


@dataclass
class Summary:
    mode: str
    label: str
    non_self: int | None
    self: int | None
    complete: bool
    note: str


def summary(pub, metrics: dict[str, ProviderMetrics], mode: str, definition: str) -> Summary:
    found = [m for m in metrics.values() if m.status == "found"]
    if mode == "empty":
        return Summary(mode, "לא מחושב", None, None, False, "מדיניות הסיכום: עמודות H ו-I נשארות ריקות")
    if not found:
        return Summary(mode, "", None, None, False, "אין מאגר שבו הפרסום אותר")
    incomplete = [PROVIDER_LABEL[m.provider] for m in found if not m.complete]
    if mode in ("sum", "max"):
        vals = [(m.non_self_formula if m.complete else m.non_self_selected, m.self_selected) for m in found]
        vals = [(n or 0, s or 0) for n, s in vals]
        if mode == "sum":
            ns, s = sum(v[0] for v in vals), sum(v[1] for v in vals)
            label = "סכום המאגרים (לא ציטוטים ייחודיים — אותו מצטט עשוי להיספר יותר מפעם אחת)"
        else:
            best = max(vals, key=lambda v: v[0] + v[1])
            ns, s = best
            label = "המאגר עם מספר הציטוטים הגבוה (לא ייחודי)"
        note = "" if not incomplete else "תוצאה חלקית — סיווג לא הושלם ב: " + ", ".join(incomplete)
        return Summary(mode, label, ns, s, not incomplete, note)
    # unique (deduplicated across databases by DOI, else exact normalised title + year)
    if incomplete:
        return Summary(mode, "ציטוטים ייחודיים", None, None, False,
                       "לא ניתן לחשב ציטוטים ייחודיים: רשימות מצטטים חסרות או לא מסווגות ב: " + ", ".join(incomplete))
    groups: dict[str, set[str]] = {}
    for c in pub.citing:
        if metrics[c.provider].status != "found":
            continue
        groups.setdefault(dedup_key(c), set()).add(c.final(definition))
    conflicts = sum(1 for v in groups.values() if len(v) > 1)
    ns = sum(1 for v in groups.values() if v == {"non_self"})
    s = sum(1 for v in groups.values() if v == {"self"})
    unresolved = sum(1 for v in groups.values() if "needs_verification" in v) + conflicts
    note = f"הוסרו כפילויות לפי DOI או כותרת+שנה זהות ({len(groups)} מצטטים ייחודיים)"
    if conflicts:
        note += f"; {conflicts} מצטטים סווגו באופן שונה במאגרים שונים — דורש אימות"
    return Summary(mode, "ציטוטים ייחודיים (לאחר הסרת כפילויות)", ns, s, unresolved == 0, note)
