"""Author name normalisation and comparison.

Comparison order:
1. Unique identifiers (ORCID, Scopus Author ID, ResearcherID). If both sides carry the
   same kind of identifier, the identifier decides.
2. Normalised names. A shared surname alone is never enough to call two authors the same.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

ID_KEYS = ("orcid", "scopus_id", "researcher_id")
ID_LABELS = {"orcid": "ORCID", "scopus_id": "Scopus Author ID", "researcher_id": "ResearcherID"}
PARTICLES = {"van", "von", "der", "den", "de", "del", "della", "di", "da", "du", "le", "la", "ben", "bar", "al", "el", "ter", "ten"}

SAME, UNCERTAIN, DIFFERENT = "same", "uncertain", "different"
_RANK = {SAME: 2, UNCERTAIN: 1, DIFFERENT: 0}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _clean_token(t: str) -> str:
    return re.sub(r"[^a-z]", "", strip_accents(t).lower())


def _looks_like_initials(tok: str) -> bool:
    t = tok.strip()
    return bool(re.fullmatch(r"(?:[A-Z]\.?-?){1,4}", t)) or bool(re.fullmatch(r"(?:[A-Z]\.\s?)+", t))


@dataclass
class ParsedName:
    raw: str
    surname: str  # normalised, no spaces/hyphens
    given: list[str] = field(default_factory=list)  # normalised given-name tokens (may be single letters)

    @property
    def first_given(self) -> str:
        return self.given[0] if self.given else ""

    @property
    def has_full_first(self) -> bool:
        return len(self.first_given) > 1


def normalize_identifier(key: str, value: str | None) -> str:
    if not value:
        return ""
    v = str(value).strip().lower()
    if key == "orcid":
        v = v.replace("https://orcid.org/", "").replace("http://orcid.org/", "")
        v = re.sub(r"[^0-9x]", "", v)
    else:
        v = re.sub(r"\s", "", v)
    return v


def _split_initials(tok: str) -> list[str]:
    letters = re.findall(r"[A-Za-z]", tok)
    return [l.lower() for l in letters]


def parse_name(raw: str) -> ParsedName:
    s = re.sub(r"\s+", " ", (raw or "").replace("*", "").strip()).strip(" ,;.")
    s = re.sub(r"\(.*?\)", "", s).strip()  # drop "(corresponding)" etc.
    if not s:
        return ParsedName(raw=raw or "", surname="")
    if "," in s:
        sur, given = s.split(",", 1)
        given_tokens = given.replace(".", ". ").split()
    else:
        toks = s.split()
        if len(toks) == 1:
            return ParsedName(raw=raw, surname=_clean_token(toks[0]))
        if _looks_like_initials(toks[-1]) and not _looks_like_initials(toks[0]):
            # Scopus style "Eizenberg E." / "Eizenberg E.A."
            sur, given_tokens = " ".join(toks[:-1]), [toks[-1]]
        else:
            i = len(toks) - 1
            while i - 1 > 0 and toks[i - 1].lower() in PARTICLES:
                i -= 1
            sur, given_tokens = " ".join(toks[i:]), toks[:i]
    given: list[str] = []
    for tok in given_tokens:
        if _looks_like_initials(tok):
            given.extend(_split_initials(tok))
        else:
            for part in re.split(r"[-\s]", tok):
                c = _clean_token(part)
                if c:
                    given.append(c)
    return ParsedName(raw=raw, surname=_clean_token(sur.replace("-", "").replace(" ", "")), given=given)


@dataclass
class Comparison:
    result: str  # same | uncertain | different
    basis: str  # identifier | full_name | initials | surname_only | name_mismatch | missing
    explanation: str


def compare_authors(a: dict, b: dict, full_name_match_is_self: bool = True) -> Comparison:
    """a, b: {name, orcid?, scopus_id?, researcher_id?}"""
    for key in ID_KEYS:
        va, vb = normalize_identifier(key, a.get(key)), normalize_identifier(key, b.get(key))
        if va and vb:
            if va == vb:
                return Comparison(SAME, "identifier", f"{ID_LABELS[key]} זהה ({va})")
            return Comparison(DIFFERENT, "identifier", f"{ID_LABELS[key]} שונה ({va} ≠ {vb})")
    na, nb = parse_name(a.get("name", "")), parse_name(b.get("name", ""))
    if not na.surname or not nb.surname:
        return Comparison(UNCERTAIN, "missing", "חסר שם מחבר להשוואה")
    if na.surname != nb.surname:
        return Comparison(DIFFERENT, "name_mismatch", f"שם משפחה שונה: {a.get('name')} / {b.get('name')}")
    if not na.given or not nb.given:
        return Comparison(UNCERTAIN, "surname_only", f"רק שם משפחה זהה ({a.get('name')} / {b.get('name')}) — אין די מידע")
    if na.has_full_first and nb.has_full_first:
        if na.first_given != nb.first_given:
            return Comparison(DIFFERENT, "name_mismatch", f"שם פרטי שונה: {a.get('name')} / {b.get('name')}")
        if full_name_match_is_self:
            return Comparison(SAME, "full_name", f"שם מלא זהה ללא מזהה ייחודי: {a.get('name')} / {b.get('name')}")
        return Comparison(UNCERTAIN, "full_name", f"שם מלא זהה ללא מזהה ייחודי (נדרש אימות): {a.get('name')} / {b.get('name')}")
    if na.first_given[0] != nb.first_given[0]:
        return Comparison(DIFFERENT, "name_mismatch", f"אות ראשונה של השם הפרטי שונה: {a.get('name')} / {b.get('name')}")
    return Comparison(UNCERTAIN, "initials", f"התאמה לפי ראשי תיבות בלבד: {a.get('name')} / {b.get('name')}")


def best(comparisons: list[Comparison]) -> Comparison | None:
    if not comparisons:
        return None
    return max(comparisons, key=lambda c: _RANK[c.result])


def compare_person_to_author(person_variants: list[dict], author: dict, full_name_match_is_self: bool = True) -> Comparison:
    """A person may have several name variants that share the same identifiers.
    A conflicting identifier on any variant rules the author out."""
    comps = [compare_authors(v, author, full_name_match_is_self) for v in person_variants]
    for c in comps:
        if c.basis == "identifier":
            return c
    return best(comps) or Comparison(UNCERTAIN, "missing", "אין נתוני מחבר")
