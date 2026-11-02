from pathlib import Path

import pytest

from app.services.cv_parser import Line, extract_fields, extract_from_lines, extract_publications

SAMPLES = Path(__file__).resolve().parents[2] / "sample_data"


@pytest.mark.parametrize("name", ["sample_cv.pdf", "sample_cv.docx"])
def test_extracts_all_entries_in_order(name):
    r = extract_publications(SAMPLES / name)
    assert r.section_found
    assert [p.original_number for p in r.publications] == [str(i) for i in range(1, 13)]
    # text after PUBLICATIONS ends at TEACHING
    assert all("Studio" not in p.raw_text for p in r.publications)


@pytest.mark.parametrize("name", ["sample_cv.pdf", "sample_cv.docx"])
def test_raw_text_kept_verbatim(name):
    r = extract_publications(SAMPLES / name)
    first = r.publications[0].raw_text.replace("\n", " ")
    assert first.startswith("1. Example, D., & Sampleson, Y. (2017). Public space and urban renewal")
    assert "https://doi.org/10.99999/jut.2017.001" in first


def test_publication_with_doi():
    f = extract_fields("1. Example, D., & Sampleson, Y. (2017). Public space and urban renewal: A test case. "
                       "Journal of Urban Testing, 12(3), 45-67. https://doi.org/10.99999/jut.2017.001")
    assert f["doi"] == "10.99999/jut.2017.001"
    assert f["year"] == 2017
    assert f["title"] == "Public space and urban renewal: A test case"
    assert f["authors"] == ["Example, D.", "Sampleson, Y."]
    assert f["venue"] == "Journal of Urban Testing"


def test_publication_without_doi():
    f = extract_fields("2. Example, D. (2019). Housing, community and the sample city. Planning Example Review, 8(1), 1-20.")
    assert f["doi"] == ""
    assert f["title"] == "Housing, community and the sample city"


def test_subsections_types_languages_and_statuses():
    r = extract_publications(SAMPLES / "sample_cv.pdf")
    by = {p.original_number: p for p in r.publications}
    assert by["1"].subsection.startswith("A. Refereed Articles")
    assert by["7"].pub_type == "book"
    assert by["8"].pub_type == "book_chapter"
    # German detected from the text, not from a marker
    assert by["3"].language == "german"
    # Hebrew detected from the section heading even though the title is transliterated Latin text
    assert by["9"].language == "hebrew" and by["10"].language == "hebrew"
    assert by["11"].pub_status == "online_first"
    assert by["12"].pub_status == "submitted"
    assert by["1"].language == "english" and by["1"].pub_status == "published"


def test_page_numbers_pdf_and_docx():
    pdf = extract_publications(SAMPLES / "sample_cv.pdf")
    assert all(p.cv_page is not None for p in pdf.publications)
    docx = extract_publications(SAMPLES / "sample_cv.docx")
    by = {p.original_number: p.cv_page for p in docx.publications}
    assert by["1"] == 1 and by["9"] == 2  # explicit page break after #8
    assert docx.page_numbers_approximate


def test_missing_publications_heading_is_reported():
    lines = [Line("Some text", 1), Line("1. Example, D. (2010). A title of a paper. Journal, 1, 1-2.", 1)]
    r = extract_from_lines(lines)
    assert not r.section_found
    assert any("PUBLICATIONS" in w for w in r.warnings)
    assert len(r.publications) == 1


def test_similar_titles_are_not_merged():
    r = extract_publications(SAMPLES / "sample_cv.docx")
    titles = [p.title for p in r.publications]
    assert "Similar titles in planning research: Part one" in titles
    assert "Similar titles in planning research: Part two" in titles


def test_hebrew_script_detected():
    lines = [Line("PUBLICATIONS", 1), Line("1. אקזמפל, ד. (2016). מרחב ציבורי בעיר. אופקים בגאוגרפיה, 90, 1-20.", 1)]
    r = extract_from_lines(lines)
    assert r.publications[0].language == "hebrew"
