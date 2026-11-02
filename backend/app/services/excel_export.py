"""Fill the faculty Excel template and add an "Audit Trail" sheet.

Column mapping (main sheet):
A publication | B WoS non-self | C WoS self | D Scopus non-self | E Scopus self |
F Scholar non-self | G Scholar self | H, I summary per approved policy.

Missing values are never written as zero: the procedure labels are used instead
("לא נבדק", "לא מאונדקס", "דורש אימות"), and partial results are marked "זמני".
"""
from __future__ import annotations

import re
from copy import copy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .classify_pub import LANG_HE, STATUS_HE, TYPE_HE, inclusion
from .metrics import PROVIDER_LABEL, STATUS_LABEL_HE, publication_metrics, summary

PROVIDER_COLS = {"wos": (2, 3), "scopus": (4, 5), "scholar": (6, 7)}
SUMMARY_COLS = (8, 9)
PARTIAL_FILL = PatternFill("solid", fgColor="FFF2CC")
MISSING_FILL = PatternFill("solid", fgColor="EDEDED")
HEADER_FILL = PatternFill("solid", fgColor="D9E1F2")
CAT_FILL = PatternFill("solid", fgColor="F2F2F2")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CLASS_HE = {"self": "עצמי", "non_self": "לא עצמי", "needs_verification": "דורש אימות"}


def build_default_template(path: Path) -> Path:
    """A template with the column structure described in the specification."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "דוח ציטוטים"
    ws.sheet_view.rightToLeft = True
    ws["A1"] = "דוח ציטוטים לתיק קידום — הפקולטה לארכיטקטורה ובינוי ערים"
    ws["A1"].font = Font(bold=True, size=14)
    groups = [("A", "A", "הפרסום"), ("B", "C", "Web of Science"), ("D", "E", "Scopus"),
              ("F", "G", "Google Scholar"), ("H", "I", "סיכום")]
    for c1, c2, label in groups:
        ws[f"{c1}3"] = label
        if c1 != c2:
            ws.merge_cells(f"{c1}3:{c2}3")
    ws.merge_cells("A3:A4")
    for col in "BDFH":
        ws[f"{col}4"] = "ציטוטים לא עצמיים"
    for col in "CEGI":
        ws[f"{col}4"] = "ציטוטים עצמיים"
    for row in (3, 4):
        for col in "ABCDEFGHI":
            cell = ws[f"{col}{row}"]
            cell.font = Font(bold=True)
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = BORDER
    ws.column_dimensions["A"].width = 90
    for col in "BCDEFGHI":
        ws.column_dimensions[col].width = 14
    ws.freeze_panes = "B5"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _row_text(ws, r: int) -> str:
    v = ws.cell(r, 1).value
    return str(v).strip() if v is not None else ""


def _row_empty_bi(ws, r: int) -> bool:
    return all(ws.cell(r, c).value in (None, "") for c in range(2, 10))


def detect_header_row(ws) -> int:
    last = 0
    for r in range(1, min(ws.max_row, 20) + 1):
        vals = " ".join(str(ws.cell(r, c).value or "") for c in range(2, 10)).lower()
        if "עצמי" in vals or "self" in vals or ("scopus" in vals and "scholar" in vals):
            last = r
    return last or 1


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^\s*\d{1,3}[.)]\s*", "", s or "").lower())


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _write_provider(cell_ns, cell_s, m):
    """Write one provider's pair of cells. Returns a short status string."""
    if m.status != "found":
        for c in (cell_ns, cell_s):
            c.value = STATUS_LABEL_HE[m.status]
            c.fill = MISSING_FILL
        return m.status
    if m.total is None:
        for c in (cell_ns, cell_s):
            c.value = "חסר סך ציטוטים"
            c.fill = PARTIAL_FILL
        return "missing_total"
    if m.complete:
        cell_ns.value = m.non_self_formula
        cell_s.value = m.self_selected
        return "complete"
    cell_ns.value = f"≥{m.non_self_selected} (זמני; {m.unresolved_selected} לא מסווגים)"
    cell_s.value = f"≥{m.self_selected} (זמני)"
    for c in (cell_ns, cell_s):
        c.fill = PARTIAL_FILL
    cell_ns.comment = Comment(
        f"{PROVIDER_LABEL[m.provider]}: סך {m.total}, סווגו {m.citing_records - (m.unresolved_a if m.definition == 'A' else m.unresolved_b)}, "
        f"לא מסווגים {m.unresolved_selected}. בדיקה לא הושלמה.", "FCR")
    return "partial"


def export_report(case, policy, template_path: Path | None, out_path: Path, audit_rows: list, exported_by: str) -> dict:
    definition = policy.self_citation_definition
    if template_path and Path(template_path).exists():
        wb = openpyxl.load_workbook(template_path)
        template_note = f"תבנית: {Path(template_path).name}"
    else:
        tmp = out_path.parent / "_default_template.xlsx"
        build_default_template(tmp)
        wb = openpyxl.load_workbook(tmp)
        template_note = "תבנית ברירת מחדל של המערכת (לא הועלתה תבנית)"
    ws = wb.worksheets[0]
    header_row = detect_header_row(ws)
    pubs = list(case.publications)
    included = [(p, inclusion(p, policy)) for p in pubs]
    report_pubs = [p for p, (inc, _) in included if inc]
    metrics = {p.id: publication_metrics(p, definition) for p in pubs}
    summaries = {p.id: summary(p, metrics[p.id], policy.summary_mode, definition) for p in pubs}

    # style to reuse for data rows (first data row of the template, if any)
    sample_style = None
    for r in range(header_row + 1, ws.max_row + 1):
        if _row_text(ws, r):
            sample_style = [copy(ws.cell(r, c)._style) for c in range(1, 10)]
            break

    # fill mode: template already lists the publications in column A
    template_rows = [r for r in range(header_row + 1, ws.max_row + 1) if len(_row_text(ws, r)) > 40]
    row_for_pub: dict[int, int] = {}
    unmatched_rows: list[int] = []
    mode = "fill" if template_rows else "build"
    if mode == "fill":
        remaining = {p.id: p for p in report_pubs}
        for r in template_rows:
            t = _norm(_row_text(ws, r))
            best, best_s = None, 0.0
            for p in remaining.values():
                s = SequenceMatcher(None, t, _norm(_flat(p.raw_text))).ratio()
                if s > best_s:
                    best, best_s = p, s
            if best and best_s >= 0.85:
                row_for_pub[best.id] = r
                del remaining[best.id]
            else:
                unmatched_rows.append(r)
        appended = list(remaining.values())
        next_row = ws.max_row + 2
        if appended:
            ws.cell(next_row, 1, "פרסומים מקורות החיים שלא הופיעו בתבנית").font = Font(bold=True)
            next_row += 1
            for p in appended:
                ws.cell(next_row, 1, _flat(p.raw_text))
                row_for_pub[p.id] = next_row
                next_row += 1
    else:
        # build mode: clear rows under the header and write categories + publications in CV order
        if ws.max_row > header_row:
            for rng in list(ws.merged_cells.ranges):
                if rng.min_row > header_row:
                    ws.unmerge_cells(str(rng))
            ws.delete_rows(header_row + 1, ws.max_row - header_row)
        r = header_row + 1
        current_cat = None
        for p in report_pubs:
            cat = p.subsection or p.section
            if cat != current_cat:
                c = ws.cell(r, 1, cat)
                c.font = Font(bold=True)
                for col in range(1, 10):
                    ws.cell(r, col).fill = CAT_FILL
                    ws.cell(r, col).border = BORDER
                current_cat = cat
                r += 1
            ws.cell(r, 1, _flat(p.raw_text))
            if sample_style:
                for col in range(1, 10):
                    ws.cell(r, col)._style = copy(sample_style[col - 1])
            row_for_pub[p.id] = r
            r += 1
        appended = []

    partial_count = 0
    for p in report_pubs:
        r = row_for_pub[p.id]
        a = ws.cell(r, 1)
        a.alignment = Alignment(wrap_text=True, vertical="top", horizontal="left", readingOrder=1)
        for prov, (c_ns, c_s) in PROVIDER_COLS.items():
            st = _write_provider(ws.cell(r, c_ns), ws.cell(r, c_s), metrics[p.id][prov])
            partial_count += st in ("partial", "missing_total")
        sm = summaries[p.id]
        h, i = ws.cell(r, SUMMARY_COLS[0]), ws.cell(r, SUMMARY_COLS[1])
        if policy.summary_mode == "empty":
            pass
        elif sm.non_self is None:
            h.value = i.value = "לא ניתן לחשב" if sm.note else None
            if sm.note:
                h.comment = Comment(sm.note, "FCR")
        else:
            h.value, i.value = (sm.non_self, sm.self) if sm.complete else (f"≥{sm.non_self} (זמני)", f"≥{sm.self} (זמני)")
            if not sm.complete:
                h.fill = i.fill = PARTIAL_FILL
                h.comment = Comment(sm.note, "FCR")
        for col in range(2, 10):
            ws.cell(r, col).alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
            ws.cell(r, col).border = BORDER

    # clarify the H/I summary policy on the header
    mode_label = {"sum": "סכום המאגרים — אינו ספירת ציטוטים ייחודיים",
                  "unique": "ציטוטים ייחודיים לאחר הסרת כפילויות בין המאגרים",
                  "max": "הערך מהמאגר עם הציטוטים הרבים ביותר — אינו ייחודי",
                  "empty": "לא מחושב לפי המדיניות"}[policy.summary_mode]
    for col in SUMMARY_COLS:
        hc = ws.cell(header_row, col)
        if hc.value in (None, ""):
            hc.value = "סיכום — לא עצמיים" if col == SUMMARY_COLS[0] else "סיכום — עצמיים"
        hc.comment = Comment(f"עמודות H-I: {mode_label}", "FCR")

    now = datetime.now(timezone.utc)
    footer = ws.max_row + 2
    def_label = "A — החוקר הנבדק מופיע בפרסום המקורי ובמצטט" if definition == "A" else "B — מחבר משותף כלשהו לפרסום המקורי ולמצטט"
    dates = [c.checked_at for p in pubs for c in p.checks if c.checked_at]
    rng = f"{min(dates):%d/%m/%Y} – {max(dates):%d/%m/%Y}" if dates else "לא נאספו נתונים"
    notes = [
        f"החוקר/ת: {case.researcher_name_en} {case.researcher_name_he}".strip(),
        f"תאריכי איסוף הנתונים: {rng}",
        f"הגדרת ציטוט עצמי: {def_label}",
        f"עמודות H-I: {mode_label}",
        "\"לא נבדק\" = הבדיקה לא הסתיימה; \"לא מאונדקס\" = הפרסום לא נמצא במאגר; \"דורש אימות\" = לא ניתן לקבוע בוודאות; \"זמני\" = קיימים ציטוטים שלא סווגו.",
        f"הופק: {now:%d/%m/%Y %H:%M} UTC על ידי {exported_by}"
        + (f"; אושר בבקרה: {case.reviewed_by}" if case.reviewed_by else "; טרם אושר בבקרת איכות"),
    ]
    for k, n in enumerate(notes):
        ws.cell(footer + k, 1, n).font = Font(italic=True, size=9)

    _audit_sheet(wb, case, policy, pubs, included, metrics, summaries, audit_rows, template_note, mode,
                 unmatched_rows, now, exported_by)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return {"path": str(out_path), "mode": mode, "publications_in_report": len(report_pubs),
            "excluded": len(pubs) - len(report_pubs), "partial_cells": partial_count,
            "unmatched_template_rows": unmatched_rows, "appended": len(appended)}


def _audit_sheet(wb, case, policy, pubs, included, metrics, summaries, audit_rows, template_note, mode,
                 unmatched_rows, now, exported_by):
    if "Audit Trail" in wb.sheetnames:
        del wb["Audit Trail"]
    ws = wb.create_sheet("Audit Trail")
    ws.sheet_view.rightToLeft = True
    r = 1

    def block(title):
        nonlocal r
        r += 1
        ws.cell(r, 1, title).font = Font(bold=True, size=12)
        r += 1

    def header(cols):
        nonlocal r
        for i, h in enumerate(cols, start=1):
            c = ws.cell(r, i, h)
            c.font = Font(bold=True)
            c.fill = HEADER_FILL
            c.border = BORDER
        r += 1

    def row(vals):
        nonlocal r
        for i, v in enumerate(vals, start=1):
            if isinstance(v, (list, dict)):
                v = str(v)
            c = ws.cell(r, i, v)
            c.border = BORDER
            c.alignment = Alignment(wrap_text=True, vertical="top")
        r += 1

    ws.cell(r, 1, "Audit Trail — תיעוד מלא של בדיקת הציטוטים").font = Font(bold=True, size=14)
    r += 1
    block("1. פרטי התיק")
    for k, v in [
        ("חוקר/ת (אנגלית)", case.researcher_name_en), ("חוקר/ת (עברית)", case.researcher_name_he),
        ("וריאנטים של השם", "; ".join(case.name_variants or [])), ("ORCID", case.orcid),
        ("Scopus Author ID", case.scopus_author_id), ("WoS ResearcherID", case.wos_researcher_id),
        ("קובץ קורות חיים", case.cv_filename), ("SHA-256 של קורות החיים", case.cv_sha256),
        ("תבנית", template_note), ("אופן מילוי התבנית", "מילוי שורות קיימות" if mode == "fill" else "בניית שורות לפי קורות החיים"),
        ("שורות בתבנית שלא הותאמו", ", ".join(map(str, unmatched_rows)) or "—"),
        ("הוכן על ידי", f"{case.prepared_by} {case.prepared_at:%d/%m/%Y %H:%M}" if case.prepared_at else "—"),
        ("נבדק ואושר על ידי", f"{case.reviewed_by} {case.reviewed_at:%d/%m/%Y %H:%M}" if case.reviewed_at else "טרם אושר"),
        ("הערת בודק", case.review_note), ("הופק", f"{now:%d/%m/%Y %H:%M} UTC, {exported_by}"),
    ]:
        row([k, v])
    block("2. מדיניות")
    row(["שפות נכללות", ", ".join(LANG_HE.get(x, x) for x in policy.included_languages)])
    row(["סטטוסים נכללים", ", ".join(STATUS_HE.get(x, x) for x in policy.included_statuses)])
    row(["סוגי פרסום נכללים", ", ".join(TYPE_HE.get(x, x) for x in policy.included_types)])
    row(["הגדרת ציטוט עצמי בדוח", policy.self_citation_definition + " (שתי ההגדרות מחושבות ומוצגות להלן)"])
    row(["שם מלא זהה ללא מזהה", "נחשב עצמי" if policy.full_name_match_is_self else "מועבר לאימות"])
    row(["מדיניות סיכום H-I", policy.summary_mode])

    block("3. פרסומים ובדיקה במאגרים")
    header(["#", "מס' בקו\"ח", "עמוד", "קטגוריה", "טקסט מקורי", "כותרת", "DOI", "שנה", "שפה", "סטטוס", "סוג",
            "נכלל", "סיבת החרגה", "מאגר", "מצב", "מזהה רשומה", "כותרת שנמצאה", "ציון התאמה", "קישור",
            "תאריך בדיקה", "בודק", "סך ציטוטים", "עצמי A", "עצמי B", "לא עצמי A", "לא עצמי B",
            "לא מסווג A", "לא מסווג B", "חסרים ברשימה", "רשימת מצטטים", "הושלם", "הערות", "סיכום H-I"])
    for p, (inc, reason) in included:
        for prov in ("wos", "scopus", "scholar"):
            m = metrics[p.id][prov]
            chk = next((c for c in p.checks if c.provider == prov), None)
            rec = chk.selected_record if chk else None
            sm = summaries[p.id]
            row([p.seq, p.original_number, p.cv_page, p.subsection or p.section, p.raw_text, p.title, p.doi, p.year,
                 LANG_HE.get(p.language), STATUS_HE.get(p.pub_status), TYPE_HE.get(p.pub_type),
                 "כן" if inc else "לא", reason, PROVIDER_LABEL[prov], m.status_label,
                 rec.record_id if rec else "", rec.found_title if rec else "",
                 round(rec.confidence, 2) if rec else "", m.source_url,
                 chk.checked_at.strftime("%d/%m/%Y %H:%M") if chk and chk.checked_at else "",
                 chk.checked_by if chk else "", m.total, m.self_a, m.self_b, m.non_self_a, m.non_self_b,
                 m.unresolved_a, m.unresolved_b, m.missing_records, m.citing_list_status,
                 "כן" if m.complete else "לא", "; ".join(m.warnings + ([chk.notes] if chk and chk.notes else [])),
                 f"{sm.label}: {sm.non_self}/{sm.self} {sm.note}" if prov == "wos" else ""])

    block("4. פרסומים מצטטים וסיווג")
    header(["# פרסום", "מאגר", "כותרת המצטט", "DOI", "מזהה", "שנה", "מחברים", "רשימת מחברים מלאה",
            "סיווג A", "הסבר A", "סיווג B", "הסבר B", "שינוי ידני", "הערת שינוי", "אושר ידנית", "מאשר", "מקור הנתון", "קישור"])
    for p in pubs:
        for c in p.citing:
            auth = "; ".join(a.get("name", "") + (f" [{a.get('orcid') or a.get('scopus_id') or a.get('researcher_id')}]"
                                                   if (a.get("orcid") or a.get("scopus_id") or a.get("researcher_id")) else "")
                             for a in c.authors)
            manual = ", ".join(x for x in [f"A→{CLASS_HE[c.manual_a]}" if c.manual_a else "",
                                           f"B→{CLASS_HE[c.manual_b]}" if c.manual_b else ""] if x)
            row([p.seq, PROVIDER_LABEL[c.provider], c.title, c.doi, c.external_id, c.year, auth or "(אין פרטי מחברים)",
                 "כן" if c.authors_complete else "לא", CLASS_HE[c.final("A")], c.explain_a, CLASS_HE[c.final("B")],
                 c.explain_b, manual, c.manual_note, "כן" if c.manually_confirmed else "לא", c.confirmed_by,
                 f"{c.origin}: {c.origin_detail}", c.source_url])

    block("5. יומן שינויים")
    header(["זמן (UTC)", "משתמש", "ישות", "מזהה", "פעולה", "פרטים"])
    for a in audit_rows:
        row([a.ts.strftime("%d/%m/%Y %H:%M:%S"), a.username, a.entity, a.entity_id, a.action, str(a.details)[:1000]])

    widths = {1: 14, 2: 12, 3: 30, 4: 30, 5: 60, 6: 40}
    for col in range(1, 34):
        ws.column_dimensions[get_column_letter(col)].width = widths.get(col, 16)
