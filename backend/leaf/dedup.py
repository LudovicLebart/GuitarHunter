"""Doublons de véhicules entre plateformes : fonction PURE.

Les titres d'autos sont génériques (« 2017 Nissan Leaf SV ») : la similarité de titre utilisée pour les
guitares ne convient pas. On compare des attributs du véhicule ; le résultat sert à MARQUER `duplicate_of`,
jamais à jeter l'annonce (les concessionnaires publient sur plusieurs sites, l'écart de prix est utile).
"""
from typing import Any, Dict

from backend.scraping.utils import calculate_distance

KM_TOLERANCE = 0.01          # ±1 %
MAX_DISTANCE_KM = 10.0


def same_vehicle(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    vin_a, vin_b = (a.get("vin") or "").strip().upper(), (b.get("vin") or "").strip().upper()
    if vin_a and vin_b:
        return vin_a == vin_b
    if not a.get("year") or a.get("year") != b.get("year"):
        return False
    if a.get("trim") and b.get("trim") and a["trim"] != b["trim"]:
        return False
    km_a, km_b = a.get("km"), b.get("km")
    if km_a is None or km_b is None or max(km_a, km_b) <= 0:
        return False   # sans kilométrage des deux côtés, on ne peut pas confirmer : pas de doublon
    if abs(km_a - km_b) / max(km_a, km_b) > KM_TOLERANCE:
        return False
    coords = (a.get("latitude"), a.get("longitude"), b.get("latitude"), b.get("longitude"))
    if None not in coords and calculate_distance(*coords) > MAX_DISTANCE_KM:
        return False
    return True
