"""Web of Science adapter — Clarivate APIs (licensed access only).

* Lookup + Times Cited: Web of Science Starter API (WOS_STARTER_API_KEY).
* Citing records: Web of Science API Expanded `/citing` (WOS_EXPANDED_API_KEY) — only
  if the institution subscribes to it. Without it, the citing list is "unavailable"
  and citing records must be imported from a WoS export file.

The response parsing follows Clarivate's published schemas; verify against the live
API with your institutional credentials before production use.
"""
from __future__ import annotations

import re

import httpx

from .base import AdapterError, AdapterNotConfigured, Candidate, CitingResult, PubQuery

STARTER = "https://api.clarivate.com/apis/wos-starter/v1/documents"
EXPANDED_CITING = "https://wos-api.clarivate.com/api/wos/citing"
REQUIREMENTS = [
    "WOS_STARTER_API_KEY — מפתח Web of Science Starter API (Clarivate Developer Portal) לאיתור ו-Times Cited",
    "WOS_EXPANDED_API_KEY — (אופציונלי) מפתח Web of Science API Expanded לרשימת המצטטים, אם קיים מנוי",
]


def _q(s: str) -> str:
    return re.sub(r'["()\\]', " ", s or "").strip()


class WebOfScienceAdapter:
    provider = "wos"

    def __init__(self, starter_key: str | None, expanded_key: str | None = None, timeout: float = 30,
                 transport: httpx.BaseTransport | None = None):
        self.starter_key, self.expanded_key, self.timeout, self.transport = starter_key, expanded_key, timeout, transport

    @property
    def configured(self) -> bool:
        return bool(self.starter_key)

    def _get(self, url: str, key: str | None, params: dict) -> dict:
        if not key:
            raise AdapterNotConfigured("Web of Science: " + "; ".join(REQUIREMENTS))
        with httpx.Client(headers={"X-ApiKey": key, "Accept": "application/json"}, timeout=self.timeout,
                          transport=self.transport) as client:
            r = client.get(url, params=params)
        if r.status_code in (401, 403):
            raise AdapterError(f"Web of Science: אין הרשאה ({r.status_code})")
        if r.status_code == 429:
            raise AdapterError("Web of Science: חריגה ממכסת הבקשות (429)")
        if r.status_code >= 400:
            raise AdapterError(f"Web of Science: שגיאה {r.status_code}: {r.text[:200]}")
        return r.json()

    @staticmethod
    def _hit(h: dict) -> Candidate:
        authors = []
        for a in (h.get("names", {}) or {}).get("authors", []) or []:
            d = {"name": a.get("wosStandard") or a.get("displayName", "")}
            if a.get("researcherId"):
                d["researcher_id"] = a["researcherId"]
            authors.append(d)
        cited = None
        for c in h.get("citations", []) or []:
            if c.get("db") in ("WOS", None):
                cited = c.get("count")
        src = h.get("source", {}) or {}
        return Candidate(
            provider="wos",
            record_id=h.get("uid", ""),
            title=h.get("title", ""),
            authors=authors,
            year=src.get("publishYear"),
            doi=(h.get("identifiers", {}) or {}).get("doi", "") or "",
            total_citations=cited,
            source_url=(h.get("links", {}) or {}).get("record", ""),
        )

    def find(self, q: PubQuery) -> list[Candidate]:
        hits = []
        if q.doi:
            hits = self._get(STARTER, self.starter_key, {"db": "WOS", "q": f'DO=("{_q(q.doi)}")', "limit": 10}).get("hits", [])
        if not hits:
            query = f'TI=("{_q(q.title)}")'
            if q.year:
                query += f" AND PY=({q.year - 1}-{q.year + 1})"
            hits = self._get(STARTER, self.starter_key, {"db": "WOS", "q": query, "limit": 10}).get("hits", [])
        return [self._hit(h) for h in hits]

    @staticmethod
    def _rec(rec: dict) -> dict:
        sd = rec.get("static_data", {}) or {}
        summ = sd.get("summary", {}) or {}
        titles = (summ.get("titles", {}) or {}).get("title", [])
        titles = titles if isinstance(titles, list) else [titles]
        title = next((t.get("content", "") for t in titles if t.get("type") == "item"), "")
        names = (summ.get("names", {}) or {}).get("name", [])
        names = names if isinstance(names, list) else [names]
        authors = []
        for n in names:
            if n.get("role") not in (None, "author"):
                continue
            d = {"name": n.get("full_name") or n.get("display_name") or n.get("wos_standard", "")}
            if n.get("orcid_id"):
                d["orcid"] = n["orcid_id"]
            if n.get("r_id"):
                d["researcher_id"] = n["r_id"]
            authors.append(d)
        idents = ((rec.get("dynamic_data", {}) or {}).get("cluster_related", {}) or {}).get("identifiers", {}) or {}
        idents = idents.get("identifier", [])
        idents = idents if isinstance(idents, list) else [idents]
        doi = next((i.get("value", "") for i in idents if i.get("type") in ("doi", "xref_doi")), "")
        year = (summ.get("pub_info", {}) or {}).get("pubyear")
        uid = rec.get("UID", "")
        return {"title": title, "doi": doi, "external_id": uid, "year": int(year) if year else None,
                "authors": authors, "authors_complete": bool(authors),
                "source_url": f"https://www.webofscience.com/wos/woscc/full-record/{uid}" if uid else ""}

    def citing(self, uid: str, max_records: int = 2000) -> CitingResult:
        if not self.expanded_key:
            return CitingResult([], "unavailable",
                                "רשימת המצטטים דורשת Web of Science API Expanded. ניתן לייבא קובץ ייצוא מ-WoS.")
        if not uid:
            return CitingResult([], "unavailable", "חסר WoS UID")
        records, first, total = [], 1, None
        while True:
            data = self._get(EXPANDED_CITING, self.expanded_key,
                             {"databaseId": "WOS", "uniqueId": uid, "count": 100, "firstRecord": first})
            if total is None:
                total = int((data.get("QueryResult", {}) or {}).get("RecordsFound", 0))
            recs = (((data.get("Data", {}) or {}).get("Records", {}) or {}).get("records", {}) or {}).get("REC", [])
            if not recs:
                break
            records.extend(self._rec(r) for r in recs)
            first += len(recs)
            if first > min(total, max_records):
                break
        return CitingResult(records, "complete" if len(records) >= (total or 0) else "partial",
                            f"{len(records)} מתוך {total} רשומות")
