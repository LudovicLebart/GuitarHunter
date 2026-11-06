"""Validation des URL fournies par un utilisateur avant que le serveur ne les visite ou ne les télécharge
(revue R-6-1 / R-6-2, 2026-11-06). Sans dépendance : importé par le bot ET par l'API (donc listé dans
l'étape « Service API PROD » de `deploy.yml`, voir `backend/api/test_prod_sync.py`)."""
import os
from urllib.parse import urlparse

# Liste blanche d'hôtes EXACTS, sans sous-domaines génériques : `l.facebook.com` / `lm.facebook.com` sont des
# redirecteurs ouverts (`/l.php?u=<n'importe quelle adresse>`) qui feraient visiter une adresse arbitraire au serveur.
LISTING_HOSTS = ("facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com",
                 "mbasic.facebook.com", "kijiji.ca", "www.kijiji.ca")
STORAGE_HOSTS = ("storage.googleapis.com", "firebasestorage.googleapis.com")
# Même valeur par défaut que `config.py::FIREBASE_STORAGE_BUCKET` (l'API de production n'importe pas `config`).
DEFAULT_STORAGE_BUCKET = "guitarehunter-d6e35.firebasestorage.app"
MAX_URL_LENGTH = 2000


def _host(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return None, None
    return parsed.scheme, (parsed.hostname or "").lower()


def _storage_bucket():
    return (os.getenv("FIREBASE_STORAGE_BUCKET") or os.getenv("VITE_FIREBASE_STORAGE_BUCKET")
            or DEFAULT_STORAGE_BUCKET)


def is_listing_url(url):
    """True si `url` est une adresse https d'annonce Facebook ou Kijiji (hôte de `LISTING_HOSTS`, exact).
    Refuse `http`, les adresses internes, `https://evil.com/?kijiji.ca`, `https://kijiji.ca.evil.com` et les
    redirecteurs `l.facebook.com`."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        return False
    scheme, host = _host(url.strip())
    return scheme == "https" and bool(host) and host in LISTING_HOSTS


def is_storage_image_url(url, bucket=None):
    """True si `url` est une adresse https d'un objet du bucket du projet : `/v0/b/<bucket>/` sur
    firebasestorage.googleapis.com, `/<bucket>/` sur storage.googleapis.com. Le bucket vient de `bucket`, sinon de
    `FIREBASE_STORAGE_BUCKET`, sinon du bucket du projet : jamais « n'importe quel bucket »."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        return False
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in STORAGE_HOSTS:
        return False
    bucket = bucket or _storage_bucket()
    prefix = f"/v0/b/{bucket}/" if host == "firebasestorage.googleapis.com" else f"/{bucket}/"
    return parsed.path.startswith(prefix)
