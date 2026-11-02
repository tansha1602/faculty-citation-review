"""Adapters against httpx.MockTransport. The JSON below is a fixture shaped like the
providers' responses — it is test data only, never shown as real results."""
import httpx
import pytest

from app.adapters.base import AdapterNotConfigured, Candidate, PubQuery, rank
from app.adapters.scholar import GoogleScholarAdapter
from app.adapters.scopus import ScopusAdapter
from app.adapters.wos import WebOfScienceAdapter


def scopus_entry(eid, title, doi="", year="2017", cited="5"):
    return {"eid": eid, "dc:title": title, "prism:doi": doi, "prism:coverDate": f"{year}-01-01", "citedby-count": cited,
            "dc:creator": "Example D.", "link": [{"@ref": "scopus", "@href": f"https://www.scopus.com/record/{eid}"}],
            "author": [{"authname": "Example D.", "authid": "90000000001"}, {"authname": "Sampleson Y.", "authid": "90000000002"}]}


def test_scopus_requires_key():
    with pytest.raises(AdapterNotConfigured) as e:
        ScopusAdapter(None).find(PubQuery("t", [], 2017, ""))
    assert "SCOPUS_API_KEY" in str(e.value)


def test_scopus_find_by_doi_auto_selects():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        assert req.headers["X-ELS-APIKey"] == "test-key"
        return httpx.Response(200, json={"search-results": {"entry": [
            scopus_entry("2-s2.0-1", "Public space and urban renewal: A test case", "10.99999/jut.2017.001")]}})

    ad = ScopusAdapter("test-key", transport=httpx.MockTransport(handler))
    q = PubQuery("Public space and urban renewal: A test case", ["Example, D."], 2017, "10.99999/jut.2017.001")
    cands, auto, reason = rank(q, ad.find(q))
    assert "DOI" in seen[0].url.params["query"]
    assert auto is not None and auto.record_id == "2-s2.0-1" and auto.total_citations == 5
    assert auto.authors[0]["scopus_id"] == "90000000001"


def test_scopus_without_doi_uses_title_search():
    def handler(req):
        assert "TITLE(" in req.url.params["query"] and "AUTHLASTNAME(Example)" in req.url.params["query"]
        return httpx.Response(200, json={"search-results": {"entry": [
            scopus_entry("2-s2.0-2", "Housing, community and the sample city", year="2019")]}})

    ad = ScopusAdapter("k", transport=httpx.MockTransport(handler))
    q = PubQuery("Housing, community and the sample city", ["Example, D."], 2019, "")
    _, auto, _ = rank(q, ad.find(q))
    assert auto is not None  # identical title + year + author


def test_not_found_returns_no_candidates():
    def handler(req):
        return httpx.Response(200, json={"search-results": {"entry": [{"@_fa": "true", "error": "Result set was empty"}]}})

    ad = ScopusAdapter("k", transport=httpx.MockTransport(handler))
    q = PubQuery("Nonexistent", ["Example, D."], 2019, "")
    cands, auto, reason = rank(q, ad.find(q))
    assert cands == [] and auto is None


def test_similar_titles_are_not_auto_selected():
    q = PubQuery("Similar titles in planning research: Part one", ["Example, D."], 2021, "")
    cands = [Candidate("scopus", "a", "Similar titles in planning research: Part one", [{"name": "Example D."}], 2021),
             Candidate("scopus", "b", "Similar titles in planning research: Part two", [{"name": "Example D."}], 2021)]
    _, auto, reason = rank(q, cands)
    assert auto is None
    assert "ידנית" in reason


def test_scopus_citing_partial_without_complete_view():
    calls = []

    def handler(req):
        calls.append(req.url.params["view"])
        if req.url.params["view"] == "COMPLETE":
            return httpx.Response(403, json={})
        return httpx.Response(200, json={"search-results": {"opensearch:totalResults": "2", "entry": [
            {"eid": "c1", "dc:title": "Citing 1", "dc:creator": "Writer X."},
            {"eid": "c2", "dc:title": "Citing 2", "dc:creator": "Example D."}]}})

    res = ScopusAdapter("k", transport=httpx.MockTransport(handler)).citing("2-s2.0-1")
    assert calls[0] == "COMPLETE" and "STANDARD" in calls
    assert len(res.records) == 2
    assert all(r["authors_complete"] is False for r in res.records)  # first author only


def test_wos_starter_lookup():
    def handler(req):
        assert req.headers["X-ApiKey"] == "w"
        return httpx.Response(200, json={"hits": [{
            "uid": "WOS:000000000000001", "title": "Public space and urban renewal: A test case",
            "names": {"authors": [{"wosStandard": "Example, D", "researcherId": "AAA-0000-2000"}]},
            "source": {"publishYear": 2017}, "identifiers": {"doi": "10.99999/jut.2017.001"},
            "citations": [{"db": "WOS", "count": 4}], "links": {"record": "https://www.webofscience.com/x"}}]})

    ad = WebOfScienceAdapter("w", transport=httpx.MockTransport(handler))
    q = PubQuery("Public space and urban renewal: A test case", ["Example, D."], 2017, "10.99999/jut.2017.001")
    _, auto, _ = rank(q, ad.find(q))
    assert auto.record_id == "WOS:000000000000001" and auto.total_citations == 4
    assert auto.authors[0]["researcher_id"] == "AAA-0000-2000"


def test_wos_citing_unavailable_without_expanded_key():
    res = WebOfScienceAdapter("w").citing("WOS:1")
    assert res.status == "unavailable" and res.records == []


def test_scholar_makes_no_network_calls_and_builds_links():
    ad = GoogleScholarAdapter()
    assert ad.network_access is False
    assert not hasattr(ad, "find") and not hasattr(ad, "citing")
    url = ad.search_url("Public space", "Example, D.", 2017)
    assert url.startswith("https://scholar.google.com/scholar?") and "author%3AExample" in url
    assert ad.cluster_id_from_url("https://scholar.google.com/scholar?cites=123456&as_sdt=2005") == "123456"
