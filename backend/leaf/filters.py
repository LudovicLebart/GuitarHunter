"""Filtres de périmètre Leaf : fonctions PURES.

Même philosophie que `out_of_budget` côté guitares : une annonce hors critères est IGNORÉE (aucune écriture),
ce n'est pas une « mauvaise annonce » à archiver.
"""
from typing import Any, Dict, Optional, Tuple

from backend.scraping.utils import calculate_distance

DEFAULT_CRITERIA: Dict[str, Any] = {
    "years": (2016, 2017, 2018),
    "min_price": 1500,     # sous ce prix : souvent des épaves / véhicules à pièces
    "max_price": 7500,
    "max_km": 150_000,
}


def is_leaf(listing: Dict[str, Any]) -> bool:
    """Modèle Leaf : attribut `model` de la source s'il existe, sinon le titre."""
    model = (listing.get("model") or "").strip().lower()
    if model:
        return model == "leaf"
    return "leaf" in (listing.get("title") or "").lower()


def passes_criteria(listing: Dict[str, Any], criteria: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """(accepté, raison). Raisons : ok | not_leaf | no_price | year | price_low | price_high | km.
    Un kilométrage inconnu n'élimine pas l'annonce (drapeau `km_unknown` côté règles)."""
    c = {**DEFAULT_CRITERIA, **(criteria or {})}
    if not is_leaf(listing):
        return False, "not_leaf"
    price = listing.get("price")
    if not isinstance(price, (int, float)) or price <= 0:
        return False, "no_price"
    if listing.get("year") not in tuple(c["years"]):
        return False, "year"
    if price < c["min_price"]:
        return False, "price_low"
    if price > c["max_price"]:
        return False, "price_high"
    km = listing.get("km")
    if km is not None and km > c["max_km"]:
        return False, "km"
    return True, "ok"


def within_distance(listing: Dict[str, Any], home_lat: Optional[float], home_lng: Optional[float],
                    max_km: Optional[float]) -> Tuple[bool, Optional[float]]:
    """(dans le rayon, distance en km). GPS ou rayon absent : accepté, distance None."""
    lat, lng = listing.get("latitude"), listing.get("longitude")
    if None in (lat, lng, home_lat, home_lng) or not max_km:
        return True, None
    d = calculate_distance(home_lat, home_lng, lat, lng)
    return d <= max_km, round(d, 1)
