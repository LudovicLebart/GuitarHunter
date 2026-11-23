"""Lecture des FICHES d'annonces Leaf (une requête par annonce retenue) et fusion avec les données de la liste.

Les pages de résultats ne donnent qu'une description tronquée (Kijiji) ou aucune (AutoHebdo) : or le SOH, les
accidents ou la pompe à chaleur s'écrivent dans le texte complet. On ne lit une fiche que pour les annonces qui
ont déjà passé les filtres de la liste (politesse : pause entre requêtes, arrêt net sur 403/429).
"""
import logging
from typing import Any, Callable, Dict, Optional

from backend.leaf.sources import BlockedError, autohebdo, fetch_html, kijiji_autos

_module_logger = logging.getLogger(__name__)

_PARSERS = {
    "kijiji": lambda html, raw: kijiji_autos.parse_detail_page(html, raw.get("source_id")),
    "autohebdo": lambda html, raw: autohebdo.parse_detail_page(html),
}
_FILL_IF_MISSING = ("trim", "city", "latitude", "longitude", "seller_type", "year", "km", "vin")


def merge_detail(raw: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
    """Annonce brute enrichie (sans modifier `raw`) : description la plus complète, champs manquants
    complétés, indicateurs de dommages et équipement ajoutés."""
    merged = dict(raw)
    if len(detail.get("description") or "") > len(raw.get("description") or ""):
        merged["description"] = detail["description"]
    for key in _FILL_IF_MISSING:
        if merged.get(key) in (None, "") and detail.get(key) not in (None, ""):
            merged[key] = detail[key]
    if len(detail.get("image_urls") or []) > len(raw.get("image_urls") or []):
        merged["image_urls"] = list(detail["image_urls"])          # la fiche donne plus de photos que la liste
    for key in ("equipment", "had_accident", "currently_damaged"):
        if key in detail:
            merged[key] = detail[key]
    merged["detail_fetched"] = True
    return merged


class DetailFetcher:
    """Appelable `fetcher(raw) -> dict | None`. Après un blocage (403/429), les appels suivants renvoient None
    sans requête : on n'insiste pas auprès d'un site qui refuse. Le journal passe par `logger` (piège connu :
    seul le logger du bot est visible dans le LogViewer de l'application)."""

    def __init__(self, fetch: Callable[[str], str] = fetch_html, logger: Optional[logging.Logger] = None):
        self._fetch = fetch
        self._log = logger or _module_logger
        self.blocked = False
        self.fetched = 0
        self.failed = 0

    def __call__(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        parser = _PARSERS.get(raw.get("source"))
        if self.blocked or not parser or not raw.get("url"):
            return None
        try:
            detail = parser(self._fetch(raw["url"]), raw)
        except BlockedError as e:
            self.blocked = True
            self._log.warning(f"[Leaf] {raw.get('source')} bloque les requêtes, fiches suivantes ignorées : {e}")
            return None
        except Exception as e:
            self.failed += 1
            self._log.debug(f"[Leaf] fiche illisible ({raw.get('source')}) : {e}")
            return None
        if detail is None:
            self.failed += 1
            return None
        self.fetched += 1
        return detail
