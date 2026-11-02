"""Import citing-publication lists from CSV / TSV / Excel files.

Supported layouts (auto-detected by column names):
* The system's own template (see sample_data/citing_import_template.csv).
* Scopus "Export" CSV of a "Cited by" list (Authors, Author full names, Author(s) ID, Title, Year, DOI, EID, Link).
* Web of Science tab-delimited export (AU, AF, TI, PY, DI, UT, OI, RI).
* Publish or Perish / Google Scholar exports obtained lawfully (Authors, Title, Year, DOI, ArticleURL / CitesURL).

Only data present in the file is used — nothing is invented. Rows without author
names are imported with an empty author list and will be classified "needs verification".
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CitingRow:
    title: str
    doi: str = ""
    external_id: str = ""
    year: int | None = None
    authors: list[dict] = field(default_factory=list)
    authors_complete: bool = True
    source_url: str = ""
    target: str = ""  # publication reference from the file (internal id or CV number), optional
    row_number: int = 0


def _norm_key(k: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (k or "").strip().lower().lstrip("﻿"))


ALIASES = {
    "title": ["title", "citingtitle", "documenttitle", "ti", "articletitle", "כותרת"],
    "doi": ["doi", "citingdoi", "di"],
    "external_id": ["eid", "ut", "uniquewosid", "citingid", "externalid", "accessionnumber", "id", "cid"],
    "year": ["year", "py", "publicationyear", "שנה"],
    "authors": ["authorfullnames", "af", "authors", "au", "author", "citingauthors", "מחברים"],
    "orcids": ["authororcids", "orcids", "oi"],
    "scopus_ids": ["authorsid", "authorids", "authorscopusids", "scopusauthorids"],
    "researcher_ids": ["authorresearcherids", "researcherids", "ri"],
    "url": ["link", "url", "articleurl", "sourceurl", "citesurl"],
    "authors_complete": ["authorscomplete"],
    "target": ["publication", "publicationid", "cvnumber", "citedpublication", "פרסום"],
}


def _read_table(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if not rows:
            return []
        header = [str(h or "") for h in rows[0]]
        return [{header[i]: ("" if v is None else str(v)) for i, v in enumerate(r) if i < len(header)} for r in rows[1:]]
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1255", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    first = text.splitlines()[0] if text else ""
    delim = "\t" if first.count("\t") > first.count(",") else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delim))


def _get(row: dict, keymap: dict, field_name: str) -> str:
    col = keymap.get(field_name)
    return (row.get(col) or "").strip() if col else ""


def _split_list(value: str) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in re.split(r";|\|", value) if v.strip() != ""]


def _scopus_full_names(value: str) -> tuple[list[str], list[str]]:
    """Scopus 'Author full names': 'Example, Dana (57190000001); Other, A. (57190000002)'."""
    names, ids = [], []
    for part in _split_list(value):
        m = re.match(r"^(.*?)\s*\((\d+)\)\s*$", part)
        if m:
            names.append(m.group(1).strip())
            ids.append(m.group(2))
        else:
            names.append(part)
            ids.append("")
    return names, ids


def _wos_id_map(value: str) -> dict[str, str]:
    """WoS OI/RI fields: 'Example, Dana/0000-0001-...; Other, A/...'"""
    out = {}
    for part in _split_list(value):
        if "/" in part:
            name, ident = part.rsplit("/", 1)
            out[re.sub(r"\W", "", name.lower())] = ident.strip()
    return out


def parse_citing_file(path: Path) -> tuple[list[CitingRow], list[str]]:
    rows = _read_table(Path(path))
    warnings: list[str] = []
    if not rows:
        return [], ["הקובץ ריק או שלא ניתן לקרוא אותו"]
    keymap: dict[str, str] = {}
    cols = {_norm_key(c): c for c in rows[0].keys() if c}
    for field_name, aliases in ALIASES.items():
        for a in aliases:
            if a in cols:
                keymap[field_name] = cols[a]
                break
    if "title" not in keymap:
        return [], ["לא נמצאה עמודת כותרת (Title). בדקו את מבנה הקובץ."]
    is_wos = "af" in cols or "ut" in cols
    out: list[CitingRow] = []
    for idx, row in enumerate(rows, start=2):
        title = _get(row, keymap, "title")
        if not title:
            continue
        authors_raw = _get(row, keymap, "authors")
        scopus_ids = _split_list(_get(row, keymap, "scopus_ids"))
        if "(" in authors_raw and re.search(r"\(\d{6,}\)", authors_raw):
            names, scopus_ids = _scopus_full_names(authors_raw)
        else:
            names = _split_list(authors_raw)
            if len(names) == 1 and "," in names[0] and not is_wos and names[0].count(",") > 1 and " and " in names[0].lower():
                names = [n.strip() for n in re.split(r",| and ", names[0]) if n.strip()]
        orcids = _split_list(_get(row, keymap, "orcids"))
        rids = _split_list(_get(row, keymap, "researcher_ids"))
        oi_map, ri_map = ({}, {})
        if is_wos:
            oi_map, ri_map = _wos_id_map(_get(row, keymap, "orcids")), _wos_id_map(_get(row, keymap, "researcher_ids"))
            orcids, rids = [], []
        authors = []
        for i, n in enumerate(names):
            a = {"name": n}
            if is_wos:
                key = re.sub(r"\W", "", n.lower())
                if key in oi_map:
                    a["orcid"] = oi_map[key]
                if key in ri_map:
                    a["researcher_id"] = ri_map[key]
            else:
                if i < len(orcids) and orcids[i] not in ("", "-"):
                    a["orcid"] = orcids[i]
                if i < len(rids) and rids[i] not in ("", "-"):
                    a["researcher_id"] = rids[i]
            if i < len(scopus_ids) and scopus_ids[i] not in ("", "-"):
                a["scopus_id"] = scopus_ids[i]
            authors.append(a)
        complete_val = _get(row, keymap, "authors_complete").lower()
        complete = bool(authors) and complete_val not in ("0", "false", "no", "לא")
        if any(re.search(r"\bet\s+al\b|\.\.\.|…", n, re.I) for n in names):
            complete = False
        year_s = _get(row, keymap, "year")
        ym = re.search(r"\d{4}", year_s)
        out.append(CitingRow(
            title=title,
            doi=_get(row, keymap, "doi").replace("https://doi.org/", "").strip(),
            external_id=_get(row, keymap, "external_id"),
            year=int(ym.group(0)) if ym else None,
            authors=authors,
            authors_complete=complete,
            source_url=_get(row, keymap, "url"),
            target=_get(row, keymap, "target"),
            row_number=idx,
        ))
        if not authors:
            warnings.append(f"שורה {idx}: אין פרטי מחברים — תסווג 'דורש אימות'")
    return out, warnings
