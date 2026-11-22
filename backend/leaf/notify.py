"""Notifications ntfy de Leaf Hunter : SUJET SÉPARÉ de celui des guitares (`LEAF_NTFY_TOPIC`, hors dépôt).

Sans la variable, rien n'est envoyé (jamais de repli sur `NTFY_TOPIC` : on ne mélange pas les deux flux).
N'importe pas `backend.notifications` (module lié au chemin `config` du bot) : bibliothèque Leaf autonome."""
import logging
import os
from email.header import Header
from typing import Optional


def send(title: str, message: str, priority: str = "default", click_url: Optional[str] = None,
         tags: Optional[list] = None, logger: Optional[logging.Logger] = None) -> bool:
    """True si ntfy a accepté. Ne lève jamais (une notification ne doit pas faire échouer un passage)."""
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
    try:
        resp = requests.post(f"https://ntfy.sh/{topic}", data=message.encode("utf-8"), headers=headers, timeout=10)
        if resp.status_code == 200:
            return True
        log.error(f"[Leaf] ntfy : HTTP {resp.status_code}")
    except Exception as e:
        log.error(f"[Leaf] ntfy injoignable : {e}")
    return False
