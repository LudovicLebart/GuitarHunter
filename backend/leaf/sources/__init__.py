"""Sources d'annonces Leaf (HTTP simple, sans navigateur). Parseurs PURS + un petit client HTTP poli."""
import re
import time
from typing import Optional

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
REQUEST_DELAY_S = 2.0       # pause minimale entre deux requêtes (politesse)
TIMEOUT_S = 25


class BlockedError(Exception):
    """Le site refuse (403/429) : on s'arrête immédiatement au lieu d'insister."""


def fetch_html(url: str, session=None, delay_s: float = REQUEST_DELAY_S) -> str:
    """GET poli (pause avant, arrêt sur 403/429). `session` : `requests.Session` injectable (tests)."""
    import requests
    s = session or requests.Session()
    if delay_s:
        time.sleep(delay_s)
    r = s.get(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8"},
              timeout=TIMEOUT_S)
    if r.status_code in (403, 429):
        raise BlockedError(f"HTTP {r.status_code} : {url.split('?')[0]}")
    r.raise_for_status()
    return r.text


def extract_next_data(html: str) -> Optional[dict]:
    """Contenu JSON de `<script id="__NEXT_DATA__">` (Kijiji), ou None."""
    import json
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None
