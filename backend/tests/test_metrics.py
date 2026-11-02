"""Metric rules with lightweight in-memory objects (no database)."""
from types import SimpleNamespace as NS

from app.services.metrics import provider_metrics, summary


def citing(provider, a, b=None, doi="", title="t"):
    return NS(provider=provider, doi=doi, title=title, year=2020, final=lambda d, a=a, b=b or a: a if d == "A" else b)


def pub(total, records, status="found", provider="scopus"):
    rec = NS(record_id="X", source_url="u", total_citations=total)
    chk = NS(provider=provider, status=status, selected_record=rec if status == "found" else None,
             checked_at=None, citing_list_status="partial")
    return NS(checks=[chk], citing=records)


def test_not_checked_is_not_zero():
    m = provider_metrics(NS(checks=[], citing=[]), "wos", "A")
    assert m.status == "not_checked" and m.total is None and m.non_self_selected is None


def test_complete_classification_uses_formula():
    p = pub(3, [citing("scopus", "self"), citing("scopus", "non_self"), citing("scopus", "non_self")])
    m = provider_metrics(p, "scopus", "A")
    assert m.complete and m.non_self_formula == 2 and m.self_selected == 1


def test_total_larger_than_list_is_partial():
    p = pub(10, [citing("scopus", "self"), citing("scopus", "non_self")])
    m = provider_metrics(p, "scopus", "A")
    assert not m.complete and m.missing_records == 8 and m.unresolved_selected == 8
    assert m.non_self_formula is None


def test_unresolved_records_make_result_partial():
    p = pub(2, [citing("scopus", "needs_verification"), citing("scopus", "non_self")])
    m = provider_metrics(p, "scopus", "A")
    assert not m.complete and m.unresolved_selected == 1


def test_definitions_computed_separately():
    p = pub(2, [citing("scopus", "non_self", "self"), citing("scopus", "non_self")])
    a, b = provider_metrics(p, "scopus", "A"), provider_metrics(p, "scopus", "B")
    assert a.self_selected == 0 and b.self_selected == 1
    assert a.self_b == 1 and b.self_a == 0


def test_list_longer_than_total_is_warned():
    p = pub(1, [citing("scopus", "non_self", doi="1"), citing("scopus", "non_self", doi="2")])
    m = provider_metrics(p, "scopus", "A")
    assert any("גדול מסך" in w for w in m.warnings)


def test_summary_partial_when_incomplete():
    p = pub(5, [citing("scopus", "non_self")])
    ms = {"scopus": provider_metrics(p, "scopus", "A"), "wos": provider_metrics(p, "wos", "A"),
          "scholar": provider_metrics(p, "scholar", "A")}
    s = summary(p, ms, "sum", "A")
    assert not s.complete and "חלקית" in s.note
    u = summary(p, ms, "unique", "A")
    assert u.non_self is None and "לא ניתן" in u.note
