"""Doublons de véhicules entre plateformes : fonction PURE.

Les titres d'autos sont génériques (« 2017 Nissan Leaf SV ») : la similarité de titre utilisée pour les
guitares ne convient pas. On compare des attributs du véhicule ; le résultat sert à MARQUER `duplicate_of`,
jamais à jeter l'annonce (les concessionnaires publient sur plusieurs sites, l'écart de prix est utile).
"""
from typing import Any, Dict

from backend.leaf.geo import calculate_distance

KM_TOLERANCE = 0.01          # ±1 %
MAX_DISTANCE_KM = 10.0
NO_KM_DISTANCE_KM = 1.0      # sans kilométrage (Facebook) : même endroit, à 1 km près
PRICE_TOLERANCE = 0.01       # sans kilométrage : même prix, à 1 % près


def _norm_title(title) -> str:
    return " ".join("".join(c if c.isalnum() else " " for c in str(title or "").lower()).split())


def _same_without_km(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Doublon PROBABLE quand aucun des deux n'a de kilométrage (annonces Facebook, qui n'ont pas de champ structuré) : même titre,
    même prix à 1 % près et même endroit (GPS à 1 km, sinon même ville). Plus strict qu'avec le kilométrage, car rien d'autre ne confirme
    qu'il s'agit du même véhicule ; le résultat ne fait que MARQUER (la page masque les doublons par défaut, avec un compteur)."""
    price_a, price_b = a.get("price"), b.get("price")
    if not isinstance(price_a, (int, float)) or not isinstance(price_b, (int, float)) or max(price_a, price_b) <= 0 \
            or abs(price_a - price_b) / max(price_a, price_b) > PRICE_TOLERANCE:
        return False
    title_a, title_b = _norm_title(a.get("title")), _norm_title(b.get("title"))
    if not title_a or title_a != title_b:
        return False
    coords = (a.get("latitude"), a.get("longitude"), b.get("latitude"), b.get("longitude"))
    if None not in coords:
        return calculate_distance(*coords) <= NO_KM_DISTANCE_KM
    city_a, city_b = _norm_title(a.get("city")), _norm_title(b.get("city"))
    return bool(city_a) and city_a == city_b


def same_vehicle(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    vin_a, vin_b = (a.get("vin") or "").strip().upper(), (b.get("vin") or "").strip().upper()
    if vin_a and vin_b:
        return vin_a == vin_b
    if not a.get("year") or a.get("year") != b.get("year"):
        return False
    if a.get("trim") and b.get("trim") and a["trim"] != b["trim"]:
        return False
    km_a, km_b = a.get("km"), b.get("km")
    if km_a is None and km_b is None:
        return _same_without_km(a, b)      # Facebook : règle dédiée, plus stricte
    if km_a is None or km_b is None or max(km_a, km_b) <= 0:
        return False   # un seul kilométrage connu : on ne peut pas confirmer
    if abs(km_a - km_b) / max(km_a, km_b) > KM_TOLERANCE:
        return False
    coords = (a.get("latitude"), a.get("longitude"), b.get("latitude"), b.get("longitude"))
    if None not in coords and calculate_distance(*coords) > MAX_DISTANCE_KM:
        return False
    return True
