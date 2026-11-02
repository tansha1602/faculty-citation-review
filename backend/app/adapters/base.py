"""Common adapter interface and match scoring.

Adapters return candidates only. A record is selected automatically only when the
match is unambiguous; otherwise the librarian chooses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ..services.names import parse_name


class AdapterNotConfigured(Exception):
    """Raised when credentials are missing. Message lists what is required."""


class AdapterError(Exception):
    pass


@dataclass
class Candidate:
    provider: str
    record_id: str
    title: str
    authors: list[dict] = field(default_factory=list)
    year: int | None = None
    doi: str = ""
    total_citations: int | None = None
    source_url: str = ""
    confidence: float = 0.0
    confidence_explanation: str = ""


@dataclass
class CitingResult:
    records: list[dict]  # {title, doi, external_id, year, authors, authors_complete, source_url}
    status: str  # complete | partial | unavailable
    note: str = ""


@dataclass
class PubQuery:
    title: str
    authors: list[str]
    year: int | None
    doi: str


def norm_title(t: str) -> str:
    t = re.sub(r"<[^>]+>", "", t or "").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def title_similarity(a: str, b: str) -> float:
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def score(q: PubQuery, c: Candidate) -> tuple[float, str]:
    parts = []
    if q.doi and c.doi and q.doi.lower().strip() == c.doi.lower().strip():
        return 1.0, "DOI זהה"
    if q.doi and c.doi:
        parts.append("DOI שונה")
        penalty = 0.4
    else:
        penalty = 0.0
    ts = title_similarity(q.title, c.title)
    parts.append(f"דמיון כותרת {ts:.0%}")
    s = ts * 0.7
    if q.year and c.year:
        if q.year == c.year:
            s += 0.15
            parts.append("שנה זהה")
        elif abs(q.year - c.year) == 1:
            s += 0.07
            parts.append("הפרש שנה אחת")
        else:
            parts.append("שנה שונה")
    q_sur = {parse_name(a).surname for a in q.authors if a}
    c_sur = {parse_name(a.get("name", "")).surname for a in c.authors if a.get("name")}
    if q_sur and c_sur:
        inter = q_sur & c_sur
        if inter:
            s += 0.15 * min(1.0, len(inter) / max(1, min(len(q_sur), len(c_sur))))
            parts.append(f"{len(inter)} שמות משפחה משותפים")
        else:
            parts.append("אין שם משפחה משותף")
    return max(0.0, min(0.99, s - penalty)), ", ".join(parts)


AUTO_SELECT_THRESHOLD = 0.95
AMBIGUITY_MARGIN = 0.10


def rank(q: PubQuery, cands: list[Candidate]) -> tuple[list[Candidate], Candidate | None, str]:
    """Score candidates; return (sorted, auto_selected_or_None, reason)."""
    for c in cands:
        c.confidence, c.confidence_explanation = score(q, c)
    cands.sort(key=lambda c: c.confidence, reverse=True)
    if not cands:
        return cands, None, "לא נמצאו רשומות"
    top = cands[0]
    if top.confidence >= 1.0:
        others = [c for c in cands[1:] if c.confidence >= 1.0]
        if others:
            return cands, None, "נמצאו כמה רשומות עם אותו DOI — נדרשת בחירה ידנית"
        return cands, top, "התאמת DOI חד-משמעית"
    if top.confidence >= AUTO_SELECT_THRESHOLD:
        if len(cands) > 1 and cands[1].confidence >= top.confidence - AMBIGUITY_MARGIN:
            return cands, None, "שתי רשומות או יותר דומות — נדרשת בחירה ידנית"
        return cands, top, "התאמה גבוהה בכותרת, שנה ומחברים"
    return cands, None, "התאמה לא חד-משמעית — נדרשת בחירה ידנית"
