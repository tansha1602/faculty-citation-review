"""Google Scholar — guided manual workflow only.

Google Scholar has no public API. This adapter performs NO network requests:
no scraping and no attempt to bypass CAPTCHA, robots.txt or blocking.
It only builds links for the librarian to open in a browser, and the counts are
entered manually (or imported from a lawfully obtained export file).
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus

REQUIREMENTS = ["אין צורך במפתח. הנתונים מוזנים ידנית מתוך דפדפן, או מיובאים מקובץ שהושג בדרך מותרת."]


class GoogleScholarAdapter:
    provider = "scholar"
    configured = True
    network_access = False

    @staticmethod
    def search_url(title: str, first_author: str = "", year: int | None = None) -> str:
        q = f'"{title}"' if title else ""
        if first_author:
            sur = first_author.split(",")[0].strip() if "," in first_author else first_author.split()[-1]
            q += f" author:{sur}"
        url = "https://scholar.google.com/scholar?hl=en&q=" + quote_plus(q.strip())
        if year:
            url += f"&as_ylo={year}&as_yhi={year}"
        return url

    @staticmethod
    def cluster_id_from_url(url: str) -> str:
        m = re.search(r"(?:cites|cluster)=(\d+)", url or "")
        return m.group(1) if m else ""

    @staticmethod
    def is_scholar_url(url: str) -> bool:
        return bool(re.match(r"^https?://scholar\.google\.[a-z.]+/", url or ""))
