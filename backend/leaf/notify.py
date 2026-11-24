"""Notifications ntfy de Leaf Hunter : SUJET SÉPARÉ de celui des guitares (`LEAF_NTFY_TOPIC`, hors dépôt).

Sans la variable, rien n'est envoyé (jamais de repli sur `NTFY_TOPIC` : on ne mélange pas les deux flux).
N'importe pas `backend.notifications` (module lié au chemin `config` du bot) : bibliothèque Leaf autonome."""
import logging
import os
import re
from email.header import Header
from typing import Optional


DEFAULT_SITE_URL = "https://ludoviclebart.github.io/GuitarHunter/"          # même site que les notifications des guitares
_ROUTE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,120}$")                       # identiques à `parseLeafHash` (src/utils/leaf.js)


def leaf_link(deal_id: Optional[str] = None) -> str:
    """Adresse de la page Leaf Hunter (`#leaf`), ou d'une annonce (`#leaf/<id>`) : ce que le toucher d'une notification ouvre. Le site se
    règle par `LEAF_SITE_URL` ; un identifiant que la route ne sait pas lire retombe sur la liste."""
    base = (os.getenv("LEAF_SITE_URL", "").strip() or DEFAULT_SITE_URL).rstrip("/") + "/"
    return base + (f"#leaf/{deal_id}" if deal_id and _ROUTE_ID_RE.match(str(deal_id)) else "#leaf")


def send(title: str, message: str, priority: str = "default", click_url: Optional[str] = None,
         tags: Optional[list] = None, logger: Optional[logging.Logger] = None, actions: Optional[list] = None) -> bool:
    """True si ntfy a accepté. Ne lève jamais (une notification ne doit pas faire échouer un passage).
    `actions` : boutons « voir » [(libellé, adresse)] ; seuls libellés et adresses ASCII passent (en-tête HTTP), le reste est ignoré."""
    log = logger or logging.getLogger(__name__)
    topic = os.getenv("LEAF_NTFY_TOPIC", "").strip()
    if not topic:
        return False
    import requests
    headers = {"Title": Header(title.replace("\n", " ").replace("\r", " "), "utf-8", maxlinelen=998).encode(),
               "Priority": priority}
    if tags:
        headers["Tags"] = ",".join(tags)
    if click_url:
        headers["Click"] = click_url
    buttons = []
    for label, url in actions or []:
        if str(label).isascii() and str(url).isascii() and str(url).startswith("https://") and "," not in str(label) + str(url):
            buttons.append(f"view, {label}, {url}")
    if buttons:
        headers["Actions"] = "; ".join(buttons[:3])
    try:
        resp = requests.post(f"https://ntfy.sh/{topic}", data=message.encode("utf-8"), headers=headers, timeout=10)
        if resp.status_code == 200:
            return True
        log.error(f"[Leaf] ntfy : HTTP {resp.status_code}")
    except Exception as e:
        log.error(f"[Leaf] ntfy injoignable : {e}")
    return False
