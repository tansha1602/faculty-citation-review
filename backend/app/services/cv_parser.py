"""Extract the publication list from a CV (PDF via PyMuPDF, DOCX via python-docx).

The raw bibliographic text of every entry is kept exactly as it appears in the CV.
Structured fields (title, authors, year, venue, DOI) are heuristic and are presented
to the librarian for correction before any database lookup.
Nothing is sent to external services.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .classify_pub import detect_language, detect_status, detect_type


@dataclass
class Line:
    text: str
    page: int | None
    para_start: bool = True
    auto_number: str = ""  # Word auto-numbering (not part of the paragraph text)


@dataclass
class ExtractedPublication:
    original_number: str
    raw_text: str
    section: str
    subsection: str
    cv_page: int | None
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    pub_type: str = "other"
    language: str = "english"
    language_evidence: str = ""
    pub_status: str = "published"
    status_evidence: str = ""


@dataclass
class ExtractionResult:
    publications: list[ExtractedPublication]
    section_found: bool
    section_heading: str
    warnings: list[str]
    page_numbers_approximate: bool


# ------------------------------------------------------------------ reading files

def read_pdf(path: Path) -> list[Line]:
    import pymupdf

    lines: list[Line] = []
    with pymupdf.open(path) as doc:
        for pno, page in enumerate(doc, start=1):
            blocks = page.get_text("blocks", sort=True)
            for b in blocks:
                if b[6] != 0:  # image block
                    continue
                first = True
                for t in b[4].splitlines():
                    if t.strip():
                        lines.append(Line(text=t.rstrip(), page=pno, para_start=first))
                        first = False
    return _drop_running_headers(lines)


def _numbering_map(document):
    """numId -> {ilvl: (numFmt, start)} for Word auto-numbering."""
    from docx.oxml.ns import qn

    result: dict[str, dict[str, tuple[str, int]]] = {}
    try:
        numbering = document.part.numbering_part.element
    except Exception:  # no numbering part
        return result
    abstract: dict[str, dict[str, tuple[str, int]]] = {}
    for an in numbering.findall(qn("w:abstractNum")):
        levels = {}
        for lvl in an.findall(qn("w:lvl")):
            fmt_el, start_el = lvl.find(qn("w:numFmt")), lvl.find(qn("w:start"))
            levels[lvl.get(qn("w:ilvl"))] = (
                fmt_el.get(qn("w:val")) if fmt_el is not None else "decimal",
                int(start_el.get(qn("w:val"))) if start_el is not None else 1,
            )
        abstract[an.get(qn("w:abstractNumId"))] = levels
    for num in numbering.findall(qn("w:num")):
        an_id = num.find(qn("w:abstractNumId"))
        if an_id is not None:
            result[num.get(qn("w:numId"))] = abstract.get(an_id.get(qn("w:val")), {})
    return result


def read_docx(path: Path) -> list[Line]:
    import docx
    from docx.oxml.ns import qn

    document = docx.Document(str(path))
    nummap = _numbering_map(document)
    counters: dict[tuple[str, str], int] = {}
    page = 1
    lines: list[Line] = []
    body = document.element.body
    for p in body.iter(qn("w:p")):
        xml_breaks = len(p.findall(".//" + qn("w:lastRenderedPageBreak")))
        xml_breaks += sum(1 for br in p.findall(".//" + qn("w:br")) if br.get(qn("w:type")) == "page")
        text = "".join(t.text or "" for t in p.iter(qn("w:t")))
        auto = ""
        numpr = p.find("./" + qn("w:pPr") + "/" + qn("w:numPr"))
        if numpr is not None:
            nid_el, ilvl_el = numpr.find(qn("w:numId")), numpr.find(qn("w:ilvl"))
            nid = nid_el.get(qn("w:val")) if nid_el is not None else None
            ilvl = ilvl_el.get(qn("w:val")) if ilvl_el is not None else "0"
            if nid and nid != "0":
                fmt, start = nummap.get(nid, {}).get(ilvl, ("decimal", 1))
                key = (nid, ilvl)
                counters[key] = counters.get(key, start - 1) + 1
                for k in list(counters):  # reset deeper levels
                    if k[0] == nid and int(k[1]) > int(ilvl):
                        del counters[k]
                if fmt == "decimal" and text.strip():
                    auto = str(counters[key])
        if text.strip():
            lines.append(Line(text=text, page=page, para_start=True, auto_number=auto))
        page += xml_breaks
    return lines


def _drop_running_headers(lines: list[Line]) -> list[Line]:
    pages = {l.page for l in lines}
    out = []
    counts = Counter(l.text.strip() for l in lines)
    for l in lines:
        t = l.text.strip()
        if re.fullmatch(r"(?:page\s*)?\d{1,3}(?:\s*(?:of|/|מתוך)\s*\d{1,3})?|-\s*\d{1,3}\s*-", t, re.I):
            continue
        if len(pages) >= 3 and counts[t] >= max(3, len(pages) // 2) and len(t) < 100:
            continue  # repeated running header/footer
        out.append(l)
    return out


# ------------------------------------------------------------------ structure

PUB_HEADING = re.compile(
    r"^\s*(?:[IVXLC]+[\.\)]|\d{1,2}[\.\)]|[A-Z][\.\)])?\s*(?:list\s+of\s+)?(?:scientific\s+|academic\s+|research\s+)?publications\b\s*:?\s*(?:\(.*\))?\s*$|^\s*רשימת\s+פרסומים",
    re.I,
)
SUB_KEYWORDS = re.compile(
    r"articles?|papers?|books?|chapters?|conference|proceedings|reports?|refereed|reviewed|submitted|accepted|"
    r"in\s+press|preparation|published|hebrew|german|theses|thesis|edited|journals?|monographs?|publications|"
    r"contributions|patents|reviews|catalogues?|exhibitions?|working|מאמרים|ספרים|פרקים|כנסים|דוחות",
    re.I,
)
END_HEADINGS = re.compile(
    r"^\s*(?:[IVXLC]+[\.\)]|\d{1,2}[\.\)])?\s*(?:teaching|courses|grants|research\s+grants|funding|awards|honou?rs|prizes|"
    r"academic\s+activit|professional\s+activit|public\s+activit|supervision|graduate\s+students|students|"
    r"membership|committees|service|lectures|invited\s+talks|presentations|personal|education|employment|"
    r"references|languages|skills)\b",
    re.I,
)
ENTRY_NUM = re.compile(r"^\s*\[?\(?(\d{1,3})[\.\)\]]\s*(?=\S)")


def _is_entry_start(line: Line) -> str | None:
    if line.auto_number:
        return line.auto_number
    m = ENTRY_NUM.match(line.text)
    if m and not re.match(r"^\s*\d{4}", line.text):  # "2012 ..." is a year, not a number
        return m.group(1)
    return None


def _is_subheading(line: Line) -> bool:
    t = line.text.strip()
    if not t or len(t) > 110 or not line.para_start:
        return False
    if _is_entry_start(line) and not re.match(r"^\s*\d{1,2}\.\d", t):
        return False
    letter_enum = re.match(r"^\s*(?:\(?[A-Za-z]{1,2}[\.\)]|[IVX]{1,4}\.)\s+\S", t)
    has_kw = bool(SUB_KEYWORDS.search(t))
    years = re.findall(r"\b(?:19|20)\d{2}\b", t)
    if has_kw and (t.endswith(":") or letter_enum or t.isupper() or (len(t) < 70 and len(years) <= 1 and not re.search(r"[\"“”]", t))):
        # a short line with a keyword — but not a short bibliographic entry ("..., Journal, 2012.")
        return not (len(years) == 1 and "," in t and len(t) > 50)
    return False


def _is_end_heading(line: Line) -> bool:
    t = line.text.strip()
    if not t or len(t) > 70 or SUB_KEYWORDS.search(t):
        return False
    if END_HEADINGS.match(t):
        return True
    letters = re.sub(r"[^A-Za-z]", "", t)
    return len(letters) >= 4 and letters.isupper() and not _is_entry_start(line)


def _find_section(lines: list[Line]) -> tuple[int | None, str]:
    for i, l in enumerate(lines):
        if PUB_HEADING.match(l.text.strip()):
            window = lines[i + 1:i + 60]
            if any(_is_entry_start(w) for w in window) or len(window) > 3:
                return i, l.text.strip()
    return None, ""


# ------------------------------------------------------------------ fields

DOI_RX = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)


def extract_doi(text: str) -> str:
    m = DOI_RX.search(text.replace("doi: ", "doi:").replace("\n", " "))
    if not m:
        return ""
    return m.group(1).rstrip(".,;)]}").strip()


def _split_authors(s: str) -> list[str]:
    s = re.sub(r"\s+", " ", s).strip(" ,;:")
    s = re.sub(r",?\s*\bet\s+al\.?", "", s, flags=re.I).strip(" ,;:")
    if not s:
        return []
    if ";" in s:
        return [a.strip(" .,") + ("." if re.search(r"\b[A-Z]$", a.strip(" .,")) else "") for a in s.split(";") if a.strip(" .,")]
    s = re.sub(r",?\s*(?:&|\band\b|\bו-)\s*", ", ", s)
    toks = [t.strip() for t in s.split(",") if t.strip()]
    initials = re.compile(r"^(?:[A-Z]\.?\s?-?){1,4}$")
    authors: list[str] = []
    i = 0
    if len(toks) >= 2 and initials.match(toks[1]):
        # "Surname, I., Surname2, I." pairs
        while i < len(toks):
            if i + 1 < len(toks) and initials.match(toks[i + 1]):
                authors.append(f"{toks[i]}, {toks[i + 1]}")
                i += 2
            else:
                authors.append(toks[i])
                i += 1
    else:
        authors = toks
    return [a for a in authors if len(a) > 1]


def extract_fields(text: str) -> dict:
    flat = unicodedata.normalize("NFKC", text)  # PDF ligatures (ﬁ, ﬀ) -> plain letters
    flat = re.sub(r"-\n(?=[a-z])", "", flat)
    flat = re.sub(r"\s+", " ", flat).strip()
    flat = ENTRY_NUM.sub("", flat, count=1).strip()
    doi = extract_doi(flat)
    year = None
    authors_part, rest = "", flat

    m = re.search(r"\((\d{4})[a-z]?(?:,[^)]*)?\)", flat)
    m2 = re.search(r"(?:^|[\s,.])((?:19[5-9]|20[0-4])\d)[a-z]?(?=[\s.,;:)])", flat)
    if m:
        year = int(m.group(1))
        authors_part, rest = flat[:m.start()], flat[m.end():]
    elif m2:
        year = int(m2.group(1))

    title, venue = "", ""
    q = re.search(r"[\"“”‘']([^\"“”’]{8,})[\"“”’']", flat)
    if q:
        title = q.group(1).strip().rstrip(",.")
        if not authors_part:
            authors_part = flat[:q.start()]
            if year and m2 and m2.start() < q.start():
                authors_part = flat[:m2.start()]
        rest_after = flat[q.end():]
    else:
        if not m and m2 and m2.start() < len(flat) * 0.6:
            authors_part, rest = flat[:m2.start()], flat[m2.end():]
        elif not m:
            # "Authors. Title. Venue" — authors end at the first ". " after an initial
            am = re.search(r"\b[A-Z]\.\s+(?=[A-Z][a-z]+\s+[a-z])", flat)
            if am:
                authors_part, rest = flat[:am.end()], flat[am.end():]
        rest = rest.lstrip(" .,:")
        tm = re.search(r"(?<=[a-z0-9\)\]?!])[.?!]\s+(?=[A-Z(])", rest)
        if tm:
            title, rest_after = rest[:tm.start() + (1 if rest[tm.start()] in "?!" else 0)], rest[tm.end():]
        else:
            title, rest_after = rest, ""
    rest_after = rest_after.lstrip(" .,:")
    rest_after = re.sub(r"^In:?\s+", "", rest_after)
    vm = re.split(r",\s*(?=\d)|\(\d|\.\s+(?i:doi|https?:)|,\s*(?i:pp?)\.|\.\s*$|\s+\d+\s*[(:]|\.\s+(?=[A-Z][a-z]+\s+[a-z])",
                  rest_after, maxsplit=1)
    venue = (vm[0] if vm else "").strip(" .,")
    if doi and doi in venue:
        venue = venue.split(doi)[0].strip(" .,")
    venue = re.sub(r"\s*(?:doi:?|https?://\S*)\s*$", "", venue, flags=re.I)
    return {
        "title": title.strip(" ."),
        "authors": _split_authors(authors_part),
        "year": year,
        "venue": venue[:300],
        "doi": doi,
    }


# ------------------------------------------------------------------ main

def extract_publications(path: Path) -> ExtractionResult:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        lines, approx = read_pdf(path), False
    elif suffix == ".docx":
        lines, approx = read_docx(path), True
    else:
        raise ValueError("נתמכים רק קובצי PDF או DOCX")
    return extract_from_lines(lines, approx)


def extract_from_lines(lines: list[Line], page_numbers_approximate: bool = False) -> ExtractionResult:
    warnings: list[str] = []
    start, heading = _find_section(lines)
    if start is None:
        warnings.append("לא נמצא פרק PUBLICATIONS — נסרק כל המסמך. יש לבדוק את הרשימה בקפידה.")
        region = lines
        heading = ""
    else:
        region = []
        for l in lines[start + 1:]:
            if _is_end_heading(l) and not _is_subheading(l):
                break
            region.append(l)

    # group into subsections
    groups: list[tuple[str, list[Line]]] = [("", [])]
    for l in region:
        if _is_subheading(l):
            groups.append((unicodedata.normalize("NFKC", l.text.strip().rstrip(":").strip()), []))
        else:
            groups[-1][1].append(l)

    pubs: list[ExtractedPublication] = []
    for sub, glines in groups:
        if not glines:
            continue
        numbered = any(_is_entry_start(l) for l in glines)
        entries: list[tuple[str, list[Line]]] = []
        for l in glines:
            num = _is_entry_start(l)
            if num is not None or (not numbered and l.para_start) or not entries:
                if numbered and num is None and not entries:
                    # text between heading and first numbered item — treat as a note, keep visible
                    warnings.append(f"טקסט ללא מספור בתחילת \"{sub or heading}\": {l.text.strip()[:80]}")
                    continue
                entries.append((num or "", [l]))
            else:
                entries[-1][1].append(l)
        for num, elines in entries:
            raw = "\n".join(
                (f"{el.auto_number}. " if el.auto_number and idx == 0 else "") + el.text for idx, el in enumerate(elines)
            )
            if len(raw.strip()) < 15:
                continue
            fields = extract_fields(raw)
            lang, lang_ev = detect_language(raw, fields["title"], fields["venue"], heading, sub)
            status, status_ev = detect_status(raw, heading, sub)
            pubs.append(ExtractedPublication(
                original_number=num,
                raw_text=raw,
                section=heading or "PUBLICATIONS",
                subsection=sub,
                cv_page=elines[0].page,
                pub_type=detect_type(heading, sub, raw),
                language=lang,
                language_evidence=lang_ev,
                pub_status=status,
                status_evidence=status_ev,
                **fields,
            ))
    if not pubs:
        warnings.append("לא חולצו פרסומים. ייתכן שהקובץ סרוק (תמונה) — יש להזין ידנית או להמיר לטקסט.")
    if page_numbers_approximate:
        warnings.append("במסמכי Word מספרי העמודים משוערים (לפי מעברי עמוד שנשמרו בקובץ).")
    return ExtractionResult(pubs, start is not None, heading, warnings, page_numbers_approximate)
