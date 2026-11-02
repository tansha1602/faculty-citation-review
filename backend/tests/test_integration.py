"""End-to-end flow through the HTTP API with the fictional sample files."""
from pathlib import Path

import openpyxl

from conftest import login

SAMPLES = Path(__file__).resolve().parents[2] / "sample_data"


def _setup_case(client, admin):
    r = client.post("/api/cases", headers=admin, json={
        "researcher_name_en": "Dana Example", "name_variants": ["Example, D."],
        "orcid": "0000-0000-0000-0001", "scopus_author_id": "90000000001"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    with open(SAMPLES / "sample_cv.docx", "rb") as f:
        r = client.post(f"/api/cases/{cid}/cv", headers=admin, files={"file": ("sample_cv.docx", f)})
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 12
    pubs = client.get(f"/api/cases/{cid}/publications", headers=admin).json()
    return cid, {p["original_number"]: p for p in pubs}


def test_requires_login(client):
    assert client.get("/api/cases").status_code == 401


def test_full_flow_and_excel(client, admin):
    cid, pubs = _setup_case(client, admin)

    # default policy: English; published/online first/accepted
    assert pubs["3"]["included"] is False and "גרמנית" in pubs["3"]["exclusion_reason"]
    assert pubs["9"]["included"] is False and "עברית" in pubs["9"]["exclusion_reason"]
    assert pubs["12"]["included"] is False and "Submitted" in pubs["12"]["exclusion_reason"]
    assert pubs["11"]["included"] is True
    included = [p for p in pubs.values() if p["included"]]
    assert len(included) == 8  # 1,2,4,5,6,7,8,11

    # correction screen: fix a field and keep the raw text unchanged
    p2 = pubs["2"]
    r = client.patch(f"/api/publications/{p2['id']}", headers=admin, json={"venue": "Planning Example Review (corrected)"})
    assert r.status_code == 200 and r.json()["raw_text"] == p2["raw_text"] and r.json()["manually_edited"]
    assert client.post(f"/api/cases/{cid}/confirm-extraction", headers=admin).status_code == 200

    # Scopus not configured -> explicit list of required credentials, no fake data
    r = client.post(f"/api/publications/{pubs['1']['id']}/search/scopus", headers=admin)
    assert r.status_code == 412 and "SCOPUS_API_KEY" in r.json()["detail"]

    p1 = pubs["1"]["id"]
    # Scopus: verified record entered manually, total 7, but only 6 citing records available (partial list)
    r = client.post(f"/api/publications/{p1}/manual/scopus", headers=admin,
                    json={"total_citations": 7, "record_id": "2-s2.0-SAMPLE", "source_url": "https://www.scopus.com/sample"})
    assert r.status_code == 200
    with open(SAMPLES / "sample_citing_scopus_pub1.csv", "rb") as f:
        r = client.post(f"/api/publications/{p1}/citing/scopus/import", headers=admin,
                        files={"file": ("cites.csv", f)}, data={"list_complete": "false"})
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 6
    citing = {c["title"]: c for c in client.get(f"/api/publications/{p1}/citing?provider=scopus", headers=admin).json()}
    # the CV lists the co-author by initials only ("Sampleson, Y.") -> uncertain -> human review
    assert citing["Co-author only paper"]["class_b"] == "needs_verification"
    # librarian completes the author names on the correction screen -> automatic reclassification
    r = client.patch(f"/api/publications/{p1}", headers=admin, json={"authors": ["Example, Dana", "Sampleson, Yoav"]})
    assert r.status_code == 200
    citing = {c["title"]: c for c in client.get(f"/api/publications/{p1}/citing?provider=scopus", headers=admin).json()}
    assert citing["Self-citing follow-up study"]["class_a"] == "self"
    assert citing["Co-author only paper"]["class_a"] == "non_self" and citing["Co-author only paper"]["class_b"] == "self"
    assert citing["Independent paper one"]["class_a"] == "non_self"
    assert citing["Homonym author paper"]["class_a"] == "non_self"  # different Scopus Author ID
    assert citing["Paper with no author data"]["class_a"] == "needs_verification"
    assert citing["Initials only paper"]["class_a"] == "needs_verification"

    detail = client.get(f"/api/publications/{p1}", headers=admin).json()
    m = detail["metrics"]["scopus"]
    assert m["total"] == 7 and m["citing_records"] == 6 and m["missing_records"] == 1
    assert m["self_a"] == 1 and m["self_b"] == 2 and m["unresolved_a"] == 2
    assert m["complete"] is False and m["unresolved_selected"] == 3

    # duplicate rows are not counted twice within the same database
    with open(SAMPLES / "sample_citing_scopus_pub1.csv", "rb") as f:
        r = client.post(f"/api/publications/{p1}/citing/scopus/import", headers=admin, files={"file": ("cites.csv", f)})
    assert r.json()["added"] == 0 and r.json()["skipped_duplicates"] == 6

    # manual reclassification requires a reason, then resolves the record
    nid = citing["Paper with no author data"]["id"]
    assert client.patch(f"/api/citing/{nid}", headers=admin, json={"manual_a": "non_self"}).status_code == 400
    r = client.patch(f"/api/citing/{nid}", headers=admin, json={"manual_a": "non_self", "manual_b": "non_self",
                                                                 "manual_note": "authors checked in publisher site", "confirm": True})
    assert r.status_code == 200 and r.json()["final_a"] == "non_self"

    # Google Scholar: manual count only (no list) -> partial, never invented
    r = client.post(f"/api/publications/{p1}/manual/scholar", headers=admin,
                    json={"total_citations": 12, "source_url": "https://scholar.google.com/scholar?cites=111"})
    assert r.status_code == 200
    assert r.json()["metrics"]["scholar"]["complete"] is False
    assert client.post(f"/api/publications/{p1}/manual/scholar", headers=admin,
                       json={"total_citations": 1, "source_url": "https://example.com"}).status_code == 400

    # publication #2 not found in WoS -> "not indexed", never 0
    p2id = pubs["2"]["id"]
    client.post(f"/api/publications/{p2id}/status/wos", headers=admin, json={"status": "not_indexed", "notes": "searched title"})
    # publication #2 in Scopus: complete classification
    client.post(f"/api/publications/{p2id}/manual/scopus", headers=admin, json={"total_citations": 2, "record_id": "2-s2.0-S2"})
    client.post(f"/api/publications/{p2id}/citing/scopus", headers=admin,
                json={"title": "A", "authors": [{"name": "Writer, X."}], "doi": "10.99999/a"})
    client.post(f"/api/publications/{p2id}/citing/scopus", headers=admin,
                json={"title": "B", "authors": [{"name": "Example, Dana", "orcid": "0000-0000-0000-0001"}], "doi": "10.99999/b"})
    m2 = client.get(f"/api/publications/{p2id}", headers=admin).json()["metrics"]["scopus"]
    assert m2["complete"] is True and m2["non_self_formula"] == 1 and m2["self_selected"] == 1

    # QA shows errors (not-checked cells), so preparation is blocked
    qa = client.get(f"/api/cases/{cid}/qa", headers=admin).json()
    assert qa["errors"] > 0 and not qa["ready"]
    assert any(i["code"] == "similar_titles" for i in qa["issues"])  # #4 / #5 kept separate, flagged
    assert client.post(f"/api/cases/{cid}/prepare", headers=admin, json={}).status_code == 409

    # export works anyway as a draft
    r = client.post(f"/api/cases/{cid}/export", headers=admin)
    assert r.status_code == 200, r.text
    info = r.json()
    assert info["status"] == "draft" and info["publications_in_report"] == 8
    dl = client.get(f"/api/cases/{cid}/exports/{info['filename']}", headers=admin)
    assert dl.status_code == 200
    out = Path(info["path"])
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["דוח ציטוטים", "Audit Trail"]
    ws = wb["דוח ציטוטים"]
    rows = {str(ws.cell(r, 1).value or "")[:3]: r for r in range(5, ws.max_row + 1)}
    r1, r2 = rows["1. "], rows["2. "]
    # B/C WoS not checked for #1 ; D/E Scopus partial ; F/G Scholar partial
    assert ws.cell(r1, 2).value == "לא נבדק"
    assert str(ws.cell(r1, 4).value).startswith("≥") and "זמני" in str(ws.cell(r1, 4).value)
    assert "זמני" in str(ws.cell(r1, 6).value)
    # #2: WoS not indexed, Scopus final numbers
    assert ws.cell(r2, 2).value == "לא מאונדקס"
    assert ws.cell(r2, 4).value == 1 and ws.cell(r2, 5).value == 1
    # no zero was invented anywhere for unchecked data
    for r in range(5, ws.max_row + 1):
        for c in range(2, 8):
            v = ws.cell(r, c).value
            if v == 0:
                raise AssertionError(f"unexpected zero at row {r} col {c}")
    # excluded publications are not in the report but are documented
    texts = [str(ws.cell(r, 1).value or "") for r in range(1, ws.max_row + 1)]
    assert not any("Beispielstadt" in t for t in texts)
    audit = wb["Audit Trail"]
    audit_text = " ".join(str(c.value) for row in audit.iter_rows() for c in row if c.value)
    assert "Beispielstadt" in audit_text and "הוחרג" in audit_text
    assert "Homonym author paper" in audit_text


def test_template_fill_mode_keeps_order(client, admin, tmp_path):
    cid, pubs = _setup_case(client, admin)
    # a faculty template that already lists publications (in CV order) under its own categories
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"], ws["B1"], ws["C1"] = "Publication", "WoS non-self", "WoS self"
    ws["A2"] = "Refereed journal articles"
    ws["A3"] = pubs["1"]["raw_text"].replace("\n", " ")
    ws["A4"] = pubs["2"]["raw_text"].replace("\n", " ")
    ws["A5"] = "Unrelated row that is not in the CV at all, kept as is with a long text"
    path = tmp_path / "tpl.xlsx"
    wb.save(path)
    with open(path, "rb") as f:
        assert client.post(f"/api/cases/{cid}/template", headers=admin, files={"file": ("tpl.xlsx", f)}).status_code == 200
    info = client.post(f"/api/cases/{cid}/export", headers=admin).json()
    assert info["mode"] == "fill"
    assert info["unmatched_template_rows"] == [5]
    out = openpyxl.load_workbook(info["path"]).worksheets[0]
    assert out["A2"].value == "Refereed journal articles"
    assert out["B3"].value == "לא נבדק"
    assert out["A5"].value.startswith("Unrelated")


def test_policy_change_requires_admin_and_second_reviewer(client, admin):
    cid, pubs = _setup_case(client, admin)
    client.post("/api/users", headers=admin, json={"username": "lib", "password": "lib-pass-123", "role": "librarian"})
    client.post("/api/users", headers=admin, json={"username": "rev", "password": "rev-pass-123", "role": "reviewer"})
    lib = login(client, "lib", "lib-pass-123")
    rev = login(client, "rev", "rev-pass-123")
    pol = client.get(f"/api/cases/{cid}/policy", headers=lib).json()
    pol_in = {k: pol[k] for k in ("included_languages", "included_statuses", "included_types",
                                  "self_citation_definition", "full_name_match_is_self", "summary_mode")}
    assert client.put(f"/api/cases/{cid}/policy", headers=lib, json=pol_in).status_code == 403
    pol_in["included_languages"] = ["english", "german"]
    assert client.put(f"/api/cases/{cid}/policy", headers=admin, json=pol_in).status_code == 200
    pubs2 = {p["original_number"]: p for p in client.get(f"/api/cases/{cid}/publications", headers=lib).json()}
    assert pubs2["3"]["included"] is True

    # make every included publication "not indexed" in all databases -> QA has no errors
    client.post(f"/api/cases/{cid}/confirm-extraction", headers=lib)
    for p in pubs2.values():
        if p["included"]:
            for prov in ("wos", "scopus", "scholar"):
                client.post(f"/api/publications/{p['id']}/status/{prov}", headers=lib, json={"status": "not_indexed"})
    assert client.post(f"/api/cases/{cid}/prepare", headers=lib, json={}).status_code == 200
    # the preparer cannot approve; the reviewer can (after acknowledging warnings)
    assert client.post(f"/api/cases/{cid}/review", headers=lib, json={}).status_code == 403
    r = client.post(f"/api/cases/{cid}/review", headers=rev, json={"acknowledge_warnings": True, "note": "ok"})
    assert r.status_code == 200 and r.json()["reviewed_by"] == "rev"
    info = client.post(f"/api/cases/{cid}/export", headers=rev).json()
    assert info["status"] == "final"
    log = client.get(f"/api/audit?case_id={cid}", headers=admin).json()
    actions = {a["action"] for a in log}
    assert {"update_case", "prepared", "reviewed", "export"} <= actions


def test_unique_summary_requires_complete_lists(client, admin):
    cid, pubs = _setup_case(client, admin)
    p = pubs["1"]["id"]
    for prov, total in (("scopus", 2), ("wos", 1)):
        client.post(f"/api/publications/{p}/manual/{prov}", headers=admin, json={"total_citations": total, "record_id": prov})
    client.post(f"/api/publications/{p}/citing/scopus", headers=admin, json={"title": "Same paper", "doi": "10.99999/s", "authors": [{"name": "Writer, X."}]})
    client.post(f"/api/publications/{p}/citing/scopus", headers=admin, json={"title": "Other paper", "doi": "10.99999/o", "authors": [{"name": "Writer, Y."}]})
    client.post(f"/api/publications/{p}/citing/wos", headers=admin, json={"title": "SAME PAPER", "doi": "10.99999/S", "authors": [{"name": "Writer, X."}]})
    pol = client.get(f"/api/cases/{cid}/policy", headers=admin).json()
    pol["summary_mode"] = "unique"
    pol_in = {k: pol[k] for k in ("included_languages", "included_statuses", "included_types",
                                  "self_citation_definition", "full_name_match_is_self", "summary_mode")}
    client.put(f"/api/cases/{cid}/policy", headers=admin, json=pol_in)
    d = client.get(f"/api/publications/{p}", headers=admin).json()
    # scholar not checked -> only found databases count; both lists complete -> 2 unique, not 3
    assert d["summary"]["non_self"] == 2 and d["summary"]["complete"] is True
    pol_in["summary_mode"] = "sum"
    client.put(f"/api/cases/{cid}/policy", headers=admin, json=pol_in)
    d = client.get(f"/api/publications/{p}", headers=admin).json()
    assert d["summary"]["non_self"] == 3 and "לא ציטוטים ייחודיים" in d["summary"]["label"]
