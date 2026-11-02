"""Self-citation definitions A and B, following the procedure's example table."""
from app.services.names import compare_authors, parse_name
from app.services.self_citation import NON_SELF, SELF, VERIFY, classify, researcher_variants

R = researcher_variants("Dana Example", ["Example, D."], orcid="0000-0000-0000-0001", scopus_id="90000000001")
ORIGINAL = [{"name": "Example, Dana", "scopus_id": "90000000001"}, {"name": "Sampleson, Yoav", "scopus_id": "90000000002"}]


def test_parse_name_formats():
    for s in ["Example, Dana", "Dana Example", "Example D.", "Example, D."]:
        assert parse_name(s).surname == "example"
    assert parse_name("Ben-Joseph, Eran").surname == "benjoseph"
    assert parse_name("Eran Ben Joseph").surname == "benjoseph"
    assert parse_name("van der Berg, J.").surname == "vanderberg"


def test_researcher_self_citation_both_definitions():
    a, b = classify(R, ORIGINAL, [{"name": "Example, Dana", "scopus_id": "90000000001"}, {"name": "Writer, X."}])
    assert a.result == SELF and b.result == SELF


def test_coauthor_only_self_citation():
    a, b = classify(R, ORIGINAL, [{"name": "Sampleson, Yoav", "scopus_id": "90000000002"}, {"name": "Writer, Y."}])
    assert a.result == NON_SELF
    assert b.result == SELF
    assert "Sampleson" in b.explanation


def test_no_shared_author():
    a, b = classify(R, ORIGINAL, [{"name": "Writer, X.", "scopus_id": "1"}, {"name": "Writer, Y.", "scopus_id": "2"}])
    assert a.result == NON_SELF and b.result == NON_SELF


def test_homonym_with_different_identifier_is_not_self():
    a, b = classify(R, ORIGINAL, [{"name": "Example, Dana", "scopus_id": "90000000999"}])
    assert a.result == NON_SELF and b.result == NON_SELF
    assert "שונה" in a.explanation


def test_same_full_name_without_identifier_depends_on_policy():
    citing = [{"name": "Example, Dana"}]
    lenient = classify(R, ORIGINAL, citing, strict_names=False)
    strict = classify(R, ORIGINAL, citing, strict_names=True)
    assert lenient[0].result == SELF
    assert strict[0].result == VERIFY


def test_initials_only_needs_verification():
    a, b = classify(R, ORIGINAL, [{"name": "Example, D."}, {"name": "Fourth, Q."}])
    assert a.result == VERIFY and b.result == VERIFY


def test_surname_only_is_never_self():
    c = compare_authors({"name": "Example, Dana"}, {"name": "Example"})
    assert c.result == "uncertain"
    c = compare_authors({"name": "Example, Dana"}, {"name": "Example, Ruth"})
    assert c.result == "different"


def test_missing_author_data_is_not_non_self():
    a, b = classify(R, ORIGINAL, [])
    assert a.result == VERIFY and b.result == VERIFY


def test_incomplete_author_list_is_not_non_self():
    a, b = classify(R, ORIGINAL, [{"name": "Writer, X.", "scopus_id": "1"}], authors_complete=False)
    assert a.result == VERIFY and b.result == VERIFY


def test_orcid_formats_match():
    c = compare_authors({"name": "X", "orcid": "https://orcid.org/0000-0000-0000-0001"}, {"name": "Y", "orcid": "0000000000000001"})
    assert c.result == "same"


def test_procedure_example_table():
    """Original by Eizenberg & Jabareen (example from the procedure); evaluated researcher: Eizenberg."""
    r = researcher_variants("Efrat Eizenberg", [])
    original = [{"name": "Efrat Eizenberg"}, {"name": "Yosef Jabareen"}]
    rows = [
        ([{"name": "Efrat Eizenberg"}, {"name": "Author X"}], SELF, SELF),
        ([{"name": "Yosef Jabareen"}, {"name": "Author Y"}], NON_SELF, SELF),
        ([{"name": "Author X"}, {"name": "Author Y"}], NON_SELF, NON_SELF),
    ]
    for citing, exp_a, exp_b in rows:
        a, b = classify(r, original, citing)
        assert (a.result, b.result) == (exp_a, exp_b), citing
