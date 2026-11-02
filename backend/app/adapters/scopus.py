"""Scopus adapter — Elsevier Scopus Search API (licensed access only).

Required: SCOPUS_API_KEY (from https://dev.elsevier.com, tied to an institutional
subscription). Optional: SCOPUS_INST_TOKEN for off-campus access.
The full author list (with Scopus Author IDs) for citing documents requires
view=COMPLETE, which depends on the institution's entitlements. When only
STANDARD view is available, citing records carry the first author only and are
marked as having an incomplete author list.
"""
from __future__ import annotations

import re

import httpx

from .base import AdapterError, AdapterNotConfigured, Candidate, CitingResult, PubQuery

BASE = "https://api.elsevier.com/content/search/scopus"
REQUIREMENTS = [
    "SCOPUS_API_KEY — מפתח Elsevier Developer Portal המשויך למנוי הטכניון",
    "SCOPUS_INST_TOKEN — (אופציונלי) טוקן מוסדי לשימוש מחוץ לרשת הטכניון",
    "הרשאת view=COMPLETE — נדרשת לקבלת כל מחברי המאמרים המצטטים ומזהי Scopus Author ID",
]


def _clean(s: str) -> str:
    return re.sub(r'["{}()\\]', " ", s or "").strip()


class ScopusAdapter:
    provider = "scopus"

    def __init__(self, api_key: str | None, inst_token: str | None = None, timeout: float = 30,
                 transport: httpx.BaseTransport | None = None):
        self.api_key, self.inst_token, self.timeout, self.transport = api_key, inst_token, timeout, transport

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _client(self) -> httpx.Client:
        if not self.api_key:
            raise AdapterNotConfigured("Scopus: " + "; ".join(REQUIREMENTS))
        headers = {"X-ELS-APIKey": self.api_key, "Accept": "application/json"}
        if self.inst_token:
            headers["X-ELS-Insttoken"] = self.inst_token
        return httpx.Client(headers=headers, timeout=self.timeout, transport=self.transport)

    def _search(self, client: httpx.Client, query: str, view: str = "STANDARD", start: int = 0, count: int = 25) -> dict:
        r = client.get(BASE, params={"query": query, "view": view, "start": start, "count": count})
        if r.status_code in (401, 403):
            raise AdapterError(f"Scopus: אין הרשאה ({r.status_code}). בדקו את המפתח וההרשאות של view={view}.")
        if r.status_code == 429:
            raise AdapterError("Scopus: חריגה ממכסת הבקשות (429). נסו שוב מאוחר יותר.")
        if r.status_code >= 400:
            raise AdapterError(f"Scopus: שגיאה {r.status_code}: {r.text[:200]}")
        return r.json().get("search-results", {})

    @staticmethod
    def _entry_to_candidate(e: dict) -> Candidate:
        authors = []
        for a in e.get("author", []) or []:
            authors.append({"name": a.get("authname") or f"{a.get('surname', '')}, {a.get('given-name', '')}".strip(", "),
                            "scopus_id": a.get("authid", "")})
        if not authors and e.get("dc:creator"):
            authors = [{"name": e["dc:creator"]}]
        url = next((l.get("@href") for l in e.get("link", []) if l.get("@ref") == "scopus"), "")
        date = e.get("prism:coverDate", "") or ""
        cnt = e.get("citedby-count")
        return Candidate(
            provider="scopus",
            record_id=e.get("eid", ""),
            title=e.get("dc:title", ""),
            authors=authors,
            year=int(date[:4]) if date[:4].isdigit() else None,
            doi=e.get("prism:doi", ""),
            total_citations=int(cnt) if cnt not in (None, "") else None,
            source_url=url,
        )

    def find(self, q: PubQuery) -> list[Candidate]:
        with self._client() as client:
            entries = []
            if q.doi:
                entries = self._search(client, f'DOI("{_clean(q.doi)}")').get("entry", [])
            if not entries or (len(entries) == 1 and "error" in entries[0]):
                parts = [f'TITLE("{_clean(q.title)}")']
                if q.authors:
                    first = q.authors[0]
                    sur = _clean(first.split(",")[0] if "," in first else (first.split() or [""])[-1])
                    if sur:
                        parts.append(f"AUTHLASTNAME({sur})")
                if q.year:
                    parts.append(f"PUBYEAR > {q.year - 2} AND PUBYEAR < {q.year + 2}")
                entries = self._search(client, " AND ".join(parts)).get("entry", [])
            return [self._entry_to_candidate(e) for e in entries if "error" not in e]

    def citing(self, eid: str, max_records: int = 2000) -> CitingResult:
        """Citing documents via REFEID(). Tries view=COMPLETE (full author list) first."""
        if not eid:
            return CitingResult([], "unavailable", "חסר Scopus EID")
        with self._client() as client:
            view = "COMPLETE"
            try:
                first = self._search(client, f"REFEID({eid})", view=view, count=25)
            except AdapterError:
                view = "STANDARD"
                first = self._search(client, f"REFEID({eid})", view=view, count=25)
            total = int(first.get("opensearch:totalResults", 0) or 0)
            entries = [e for e in first.get("entry", []) if "error" not in e]
            start = len(entries)
            while start < min(total, max_records):
                page = self._search(client, f"REFEID({eid})", view=view, start=start, count=25)
                batch = [e for e in page.get("entry", []) if "error" not in e]
                if not batch:
                    break
                entries.extend(batch)
                start += len(batch)
        records = []
        for e in entries:
            c = self._entry_to_candidate(e)
            full = view == "COMPLETE" and bool(e.get("author"))
            records.append({"title": c.title, "doi": c.doi, "external_id": c.record_id, "year": c.year,
                            "authors": c.authors, "authors_complete": full, "source_url": c.source_url})
        status = "complete" if len(records) >= total else "partial"
        note = f"view={view}; {len(records)} מתוך {total} רשומות"
        if view != "COMPLETE":
            note += " — רק מחבר ראשון זמין (אין הרשאת COMPLETE)"
        return CitingResult(records, status, note)
