"""Validation des URL fournies par un utilisateur avant que le serveur ne les visite ou ne les télécharge
(revue R-6-1 / R-6-2, 2026-11-06). Sans dépendance : importé par le bot ET par l'API (donc listé dans
l'étape « Service API PROD » de `deploy.yml`, voir `backend/api/test_prod_sync.py`)."""
import os
from urllib.parse import urlparse

LISTING_HOSTS = ("facebook.com", "kijiji.ca")
STORAGE_HOSTS = ("storage.googleapis.com", "firebasestorage.googleapis.com")
MAX_URL_LENGTH = 2000


def _host(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return None, None
    return parsed.scheme, (parsed.hostname or "").lower()


def _host_matches(host, allowed):
    return any(host == h or host.endswith("." + h) for h in allowed)


def is_listing_url(url):
    """True si `url` est une adresse https d'annonce Facebook ou Kijiji (domaine exact ou sous-domaine).
    Refuse `http`, les adresses internes, `https://evil.com/?kijiji.ca` et `https://kijiji.ca.evil.com`."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        return False
    scheme, host = _host(url.strip())
    return scheme == "https" and bool(host) and _host_matches(host, LISTING_HOSTS)


def is_storage_image_url(url, bucket=None):
    """True si `url` est une adresse https du stockage Firebase/Google. Si `bucket` (ou la variable
    `FIREBASE_STORAGE_BUCKET`) est connu, il doit apparaître dans le chemin."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        return False
    scheme, host = _host(url.strip())
    if scheme != "https" or host not in STORAGE_HOSTS:
        return False
    bucket = bucket if bucket is not None else os.getenv("FIREBASE_STORAGE_BUCKET", "")
    return not bucket or bucket in url
