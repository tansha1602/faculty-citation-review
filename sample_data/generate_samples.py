"""Generate SAMPLE input files for trying out the system and for the tests.

All people, titles, DOIs (prefix 10.99999 — not a real registrant) and IDs here are
FICTIONAL. These files must never be presented as real results.

Usage:  python sample_data/generate_samples.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))

HEADER = [
    ("h", "CURRICULUM VITAE — SAMPLE (fictional researcher, for testing only)"),
    ("p", "Dr. Dana Example"),
    ("p", "Faculty of Architecture and Town Planning"),
    ("h", "EDUCATION"),
    ("p", "2005 PhD, Urban Planning, Example University"),
    ("h", "PUBLICATIONS"),
]

PUBS = [
    ("sub", "A. Refereed Articles in Scientific Journals"),
    ("1", "Example, D., & Sampleson, Y. (2017). Public space and urban renewal: A test case. Journal of Urban Testing, 12(3), 45-67. https://doi.org/10.99999/jut.2017.001"),
    ("2", "Example, D. (2019). Housing, community and the sample city. Planning Example Review, 8(1), 1-20."),
    ("3", "Example, D. (2012). Öffentlicher Raum und Stadtplanung in der Beispielstadt. Zeitschrift für Beispielplanung, 4, 33-50."),
    ("4", "Example, D., & Other, A. (2021). Similar titles in planning research: Part one. Journal of Urban Testing, 16(2), 10-30. doi:10.99999/jut.2021.002"),
    ("5", "Example, D., & Other, A. (2022). Similar titles in planning research: Part two. Journal of Urban Testing, 17(1), 5-25. doi:10.99999/jut.2022.003"),
    ("6", "Example, D. (2014). Community gardens as urban commons. Example Journal of Geography, 3(2), 100-118."),
    ("sub", "B. Books"),
    ("7", "Example, D. (2015). The Example City: Space and Society. London: Example Press."),
    ("sub", "C. Chapters in Books"),
    ("8", "Example, D. (2018). Urban gardens. In: Sampleson, Y. (Ed.), Handbook of Example Cities (pp. 100-120). Example Press."),
    ("sub", "D. Articles in Hebrew"),
    ("9", "Example, D. (2016). Merhav tziburi ba-ir [Public space in the city]. Ofakim be-Geografia, 90, 1-20."),
    ("10", "Example, D. & Sampleson, Y. (2020). Tichnun ironi ve-kehila [Urban planning and community]. Tichnun, 17, 22-40."),
    ("sub", "E. Accepted for Publication"),
    ("11", "Example, D. (2025). Online platforms and planning participation. Journal of Urban Testing. Published online first. doi:10.99999/jut.2025.009"),
    ("sub", "F. Submitted Papers"),
    ("12", "Example, D., & Sampleson, Y. Planning under uncertainty in sample cities. Submitted to Planning Example Review."),
]

FOOTER = [("h", "TEACHING"), ("p", "Urban Planning Studio, 2010-present")]


def make_docx(path: Path):
    import docx
    from docx.shared import Pt

    d = docx.Document()
    for kind, text in HEADER:
        par = d.add_paragraph(text)
        if kind == "h":
            par.runs[0].bold = True
    for num, text in PUBS:
        if num == "sub":
            par = d.add_paragraph(text)
            par.runs[0].bold = True
        else:
            d.add_paragraph(f"{num}. {text}")
        if num == "8":
            d.add_page_break()
    for kind, text in FOOTER:
        par = d.add_paragraph(text)
        if kind == "h":
            par.runs[0].bold = True
    for p in d.paragraphs:
        for r in p.runs:
            r.font.size = Pt(11)
    d.save(path)


def make_pdf(path: Path):
    import pymupdf

    html = []
    for kind, text in HEADER:
        html.append(f"<p><b>{text}</b></p>" if kind == "h" else f"<p>{text}</p>")
    for num, text in PUBS:
        html.append(f"<p><b>{text}</b></p>" if num == "sub" else f"<p>{num}. {text}</p>")
    for kind, text in FOOTER:
        html.append(f"<p><b>{text}</b></p>" if kind == "h" else f"<p>{text}</p>")
    story = pymupdf.Story(html="".join(html), user_css="p{font-family:sans-serif;font-size:10pt;margin-bottom:6pt}")
    writer = pymupdf.DocumentWriter(str(path))
    rect = pymupdf.paper_rect("a4")
    where = rect + (60, 60, -60, -60)
    more = True
    while more:
        dev = writer.begin_page(rect)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()


RESEARCHER = {"name": "Example, Dana", "orcid": "0000-0000-0000-0001"}

# Citing records for publication #1 (Scopus) — exercises every classification path.
CITING_SCOPUS_PUB1 = [
    # title, year, doi, authors "Name (ScopusID)"; ...
    ("Self-citing follow-up study", 2019, "10.99999/c.001", "Example, Dana (90000000001); Writer, X. (90000000101)"),
    ("Co-author only paper", 2020, "10.99999/c.002", "Sampleson, Yoav (90000000002); Writer, Y. (90000000102)"),
    ("Independent paper one", 2020, "10.99999/c.003", "Writer, X. (90000000101); Writer, Y. (90000000102)"),
    ("Homonym author paper", 2021, "10.99999/c.004", "Example, Dana (90000000999); Third, Z. (90000000103)"),
    ("Paper with no author data", 2021, "10.99999/c.005", ""),
    ("Initials only paper", 2022, "", "Example, D.; Fourth, Q."),
]


def make_citing_csv(path: Path):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Author full names", "Title", "Year", "DOI", "EID", "Link"])
        for i, (title, year, doi, authors) in enumerate(CITING_SCOPUS_PUB1, start=1):
            w.writerow([authors, title, year, doi, f"2-s2.0-SAMPLE{i:04d}", ""])


def make_generic_template(path: Path):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["publication", "title", "year", "doi", "external_id", "authors", "author_orcids",
                    "author_scopus_ids", "author_researcher_ids", "url", "authors_complete"])
        w.writerow(["1", "SAMPLE citing paper (fictional)", "2020", "10.99999/x.1", "", "Writer, X.; Example, Dana",
                    "; 0000-0000-0000-0001", "", "", "", "yes"])


def main():
    out = HERE
    make_docx(out / "sample_cv.docx")
    make_pdf(out / "sample_cv.pdf")
    make_citing_csv(out / "sample_citing_scopus_pub1.csv")
    make_generic_template(out / "citing_import_template.csv")
    from app.services.excel_export import build_default_template

    build_default_template(out / "report_template.xlsx")
    print("Sample files written to", out)


if __name__ == "__main__":
    main()
