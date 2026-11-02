"""Heuristics for publication language, status and type.

Language is decided from explicit markers, section headings, script and vocabulary —
never from the title language alone. Every decision records its evidence so the
librarian can review and correct it.
"""
from __future__ import annotations

import re

HEBREW_CHARS = re.compile(r"[֐-׿]")

_LANG_MARKERS = [
    ("hebrew", re.compile(r"\b(?:in\s+hebrew|hebrew(?:\s+with\s+english\s+abstract)?)\b|\[hebrew\]|בעברית", re.I)),
    ("german", re.compile(r"\b(?:in\s+german|german|deutsch)\b|\[german\]|בגרמנית", re.I)),
    ("other", re.compile(r"\b(?:in\s+(?:french|spanish|italian|arabic|russian|chinese|japanese|portuguese|dutch))\b", re.I)),
]

_GERMAN_WORDS = {
    "und", "der", "die", "das", "des", "dem", "den", "für", "fur", "zur", "zum", "im", "von", "mit", "einer", "eine",
    "ein", "über", "uber", "zwischen", "stadt", "städte", "raum", "planung", "architektur", "zeitschrift", "verlag",
    "heft", "jahrgang", "herausgegeben", "hrsg", "wohnen", "gesellschaft", "öffentlichen", "nicht", "auf",
}
_ENGLISH_WORDS = {
    "the", "of", "and", "in", "on", "for", "to", "a", "an", "with", "from", "journal", "urban", "planning", "city",
    "studies", "review", "space", "public", "between", "towards", "case", "design", "research", "housing",
}

_STATUS_RULES = [
    ("unpublished", re.compile(r"\b(?:unpublished|in\s+preparation|manuscript\s+in\s+preparation)\b", re.I)),
    ("submitted", re.compile(r"\b(?:submitted|under\s+review|in\s+review|revise\s+and\s+resubmit|r&r)\b", re.I)),
    ("online_first", re.compile(r"\b(?:online\s+first|published\s+online|early\s+view|advance\s+online|ahead\s+of\s+print|epub\s+ahead)\b", re.I)),
    ("accepted", re.compile(r"\b(?:accepted(?:\s+for\s+publication)?|in\s+press|forthcoming)\b", re.I)),
]

_TYPE_RULES = [
    ("book_chapter", re.compile(r"chapter|contributions?\s+to\s+(?:collective|edited)|in\s+edited\s+books?|פרקים?\s+בספר", re.I)),
    ("book", re.compile(r"\bbooks?\b|monograph|ספרים", re.I)),
    ("conference", re.compile(r"conference|proceedings|symposi|congress|כנס", re.I)),
    ("report", re.compile(r"\breports?\b|working\s+papers?|technical|דוחות|דו\"חות", re.I)),
    ("journal_article", re.compile(r"journal|refereed\s+articles?|articles?|papers?|מאמרים", re.I)),
]


def detect_language(raw_text: str, title: str, venue: str, section: str, subsection: str) -> tuple[str, str]:
    heading = f"{section} {subsection}"
    for lang, rx in _LANG_MARKERS:
        if rx.search(heading):
            return lang, f"כותרת הפרק בקורות החיים: \"{subsection or section}\""
    for lang, rx in _LANG_MARKERS:
        m = rx.search(raw_text)
        if m:
            return lang, f"סימון מפורש בטקסט: \"{m.group(0)}\""
    letters = re.findall(r"[^\W\d_]", raw_text)
    heb = len(HEBREW_CHARS.findall(raw_text))
    if letters and heb / len(letters) > 0.3:
        return "hebrew", "רוב הטקסט באותיות עבריות"
    words = [w.lower() for w in re.findall(r"[A-Za-zÄÖÜäöüß]+", f"{title} {venue}")]
    if re.search(r"[äöüß]", f"{title} {venue}", re.I):
        g = sum(1 for w in words if w in _GERMAN_WORDS)
        if g >= 1:
            return "german", "אותיות ומילים גרמניות בכותרת או במקום הפרסום"
    g = sum(1 for w in words if w in _GERMAN_WORDS)
    e = sum(1 for w in words if w in _ENGLISH_WORDS)
    if g >= 2 and g > e:
        return "german", f"מילים גרמניות בכותרת/במקום הפרסום ({g} לעומת {e} באנגלית)"
    if not words and not re.findall(r"[A-Za-z]{3,}", raw_text):
        return "other", "לא זוהה טקסט לטיני — שפה לא ברורה"
    return "english", "טקסט לטיני ללא סימון שפה אחרת (ברירת מחדל — לבדיקה)"


def detect_status(raw_text: str, section: str, subsection: str) -> tuple[str, str]:
    """An explicit marker in the entry itself is more specific than the section heading."""
    heading = f"{section} {subsection}"
    for status, rx in _STATUS_RULES:
        m = rx.search(raw_text)
        if m:
            return status, f"סימון בטקסט: \"{m.group(0)}\""
    for status, rx in _STATUS_RULES:
        if rx.search(heading):
            return status, f"כותרת הפרק: \"{subsection or section}\""
    return "published", "לא נמצא סימון סטטוס — הוגדר כפורסם"


def detect_type(section: str, subsection: str, raw_text: str = "") -> str:
    heading = f"{subsection} {section}"
    for t, rx in _TYPE_RULES:
        if rx.search(subsection or ""):
            return t
    for t, rx in _TYPE_RULES:
        if rx.search(heading):
            return t
    if re.search(r"\bproceedings\b|\bconference\b", raw_text, re.I):
        return "conference"
    if re.search(r"\bIn:?\s.*\(eds?\.?\)", raw_text, re.I):
        return "book_chapter"
    if re.search(r"\bjournal\b|\breview\b|\bquarterly\b", raw_text, re.I):
        return "journal_article"
    return "other"


LANG_HE = {"english": "אנגלית", "hebrew": "עברית", "german": "גרמנית", "other": "אחר"}
STATUS_HE = {"published": "פורסם", "online_first": "פורסם מקוון (Online first)", "accepted": "התקבל (Accepted)",
             "submitted": "הוגש (Submitted)", "unpublished": "לא פורסם"}
TYPE_HE = {"journal_article": "מאמר בכתב עת", "book": "ספר", "book_chapter": "פרק בספר", "conference": "כנס",
           "report": "דוח", "other": "אחר"}


def inclusion(pub, policy) -> tuple[bool, str]:
    """Return (included, reason). Excluded records are kept with a reason."""
    if pub.manual_include is True:
        return True, f"נכלל ידנית: {pub.manual_include_reason}".strip(": ")
    if pub.manual_include is False:
        return False, f"הוחרג ידנית: {pub.manual_include_reason}".strip(": ")
    reasons = []
    if pub.language not in policy.included_languages:
        reasons.append(f"שפה: {LANG_HE.get(pub.language, pub.language)}")
    if pub.pub_status not in policy.included_statuses:
        reasons.append(f"סטטוס: {STATUS_HE.get(pub.pub_status, pub.pub_status)}")
    if pub.pub_type not in policy.included_types:
        reasons.append(f"סוג פרסום: {TYPE_HE.get(pub.pub_type, pub.pub_type)}")
    if reasons:
        return False, "הוחרג לפי המדיניות — " + ", ".join(reasons)
    return True, ""
