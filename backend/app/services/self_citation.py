"""Self-citation classification (procedure stage C/D).

Definition A: the evaluated researcher appears in both the cited and the citing publication.
Definition B: at least one author is shared by the cited and the citing publication.

Records with missing author data are never classified as non-self by default.
"""
from __future__ import annotations

from dataclasses import dataclass

from .names import DIFFERENT, SAME, UNCERTAIN, compare_authors, compare_person_to_author, parse_name

SELF, NON_SELF, VERIFY = "self", "non_self", "needs_verification"


@dataclass
class Classification:
    result: str
    explanation: str


def researcher_variants(name_en: str, variants: list[str], orcid: str = "", scopus_id: str = "", researcher_id: str = "") -> list[dict]:
    ids = {"orcid": orcid, "scopus_id": scopus_id, "researcher_id": researcher_id}
    names = [name_en] + [v for v in (variants or []) if v and v.strip()]
    return [{"name": n, **ids} for n in names]


def _author_label(a: dict) -> str:
    return a.get("name") or "(ללא שם)"


def _usable_authors(authors: list[dict]) -> list[dict]:
    return [a for a in (authors or []) if (a.get("name") or "").strip() or any(a.get(k) for k in ("orcid", "scopus_id", "researcher_id"))]


def classify_a(researcher: list[dict], citing_authors: list[dict], authors_complete: bool, strict_names: bool) -> Classification:
    citing = _usable_authors(citing_authors)
    if not citing:
        return Classification(VERIFY, "לרשומת המצטט אין פרטי מחברים — לא ניתן לסווג")
    uncertain, id_diff = [], []
    for ca in citing:
        c = compare_person_to_author(researcher, ca, full_name_match_is_self=not strict_names)
        if c.result == SAME:
            return Classification(SELF, f"החוקר הנבדק מופיע במצטט: {c.explanation}")
        if c.result == UNCERTAIN:
            uncertain.append(c.explanation)
        elif c.basis == "identifier" and parse_name(ca.get("name", "")).surname in {
                parse_name(v["name"]).surname for v in researcher}:
            id_diff.append(f"{_author_label(ca)}: {c.explanation}")
    if uncertain:
        return Classification(VERIFY, "התאמה לא ודאית לחוקר הנבדק: " + "; ".join(uncertain))
    if not authors_complete:
        return Classification(VERIFY, "רשימת המחברים של המצטט חלקית; החוקר לא זוהה ברשומות הזמינות")
    extra = f" (שם דומה עם מזהה שונה — {'; '.join(id_diff)})" if id_diff else ""
    return Classification(NON_SELF, f"החוקר הנבדק לא נמצא בין {len(citing)} מחברי המצטט{extra}")


def classify_b(researcher: list[dict], original_authors: list[dict], citing_authors: list[dict],
               authors_complete: bool, strict_names: bool) -> Classification:
    citing = _usable_authors(citing_authors)
    if not citing:
        return Classification(VERIFY, "לרשומת המצטט אין פרטי מחברים — לא ניתן לסווג")
    full = not strict_names
    uncertain = []
    # the evaluated researcher (with all identifiers / name variants)
    for ca in citing:
        c = compare_person_to_author(researcher, ca, full_name_match_is_self=full)
        if c.result == SAME:
            return Classification(SELF, f"מחבר משותף (החוקר הנבדק): {c.explanation}")
        if c.result == UNCERTAIN:
            uncertain.append(c.explanation)
    originals = _usable_authors(original_authors)
    for oa in originals:
        # skip original authors that are the evaluated researcher (already handled above)
        if compare_person_to_author(researcher, oa, full_name_match_is_self=True).result == SAME:
            continue
        for ca in citing:
            c = compare_authors(oa, ca, full_name_match_is_self=full)
            if c.result == SAME:
                return Classification(SELF, f"מחבר משותף ({_author_label(oa)}): {c.explanation}")
            if c.result == UNCERTAIN:
                uncertain.append(c.explanation)
    if uncertain:
        return Classification(VERIFY, "התאמה לא ודאית למחבר של הפרסום המקורי: " + "; ".join(uncertain))
    if not originals:
        return Classification(VERIFY, "רשימת המחברים של הפרסום המקורי חסרה — לא ניתן לבדוק מחברים שותפים")
    if not authors_complete:
        return Classification(VERIFY, "רשימת המחברים של המצטט חלקית; לא זוהה מחבר משותף ברשומות הזמינות")
    return Classification(NON_SELF, f"אין מחבר משותף בין {len(originals)} מחברי המקור ל-{len(citing)} מחברי המצטט")


def classify(researcher: list[dict], original_authors: list[dict], citing_authors: list[dict],
             authors_complete: bool = True, strict_names: bool = False) -> tuple[Classification, Classification]:
    return (
        classify_a(researcher, citing_authors, authors_complete, strict_names),
        classify_b(researcher, original_authors, citing_authors, authors_complete, strict_names),
    )


__all__ = ["classify", "classify_a", "classify_b", "researcher_variants", "SELF", "NON_SELF", "VERIFY", "DIFFERENT"]
