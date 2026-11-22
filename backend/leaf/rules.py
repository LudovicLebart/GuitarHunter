"""Portier Leaf — niveau 1 : règles DÉTERMINISTES (gratuites, sans IA). Fonctions PURES.

Principe : ne rejeter que sur une preuve. L'absence d'information (SOH inconnu, km inconnu) devient un
drapeau, jamais un rejet.
"""
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_SOH_MIN_REJECT = 80.0


def gatekeeper_rules(listing: Dict[str, Any], soh_min_reject: float = DEFAULT_SOH_MIN_REJECT
                     ) -> Tuple[str, List[str], List[str]]:
    """(décision, raisons de rejet, drapeaux). Décision : 'REJECT' ou 'PASS'.
    Attend une annonce passée par `normalize.normalize_listing`."""
    reasons: List[str] = []
    flags: List[str] = []

    if listing.get("battery_source") == "stated" and listing.get("battery_kwh_high") == 24:
        reasons.append("battery_24kwh")
    elif listing.get("battery_kwh_low") == 24:
        flags.append("battery_24_possible")

    for word in listing.get("accident_flags") or []:
        reasons.append(f"accident:{word}")

    soh = listing.get("soh_announced")
    if soh is None:
        flags.append("soh_unknown")
    elif soh < soh_min_reject:
        reasons.append(f"soh_below_{int(soh_min_reject)}")

    if listing.get("km") is None:
        flags.append("km_unknown")
    if listing.get("battery_source") == "unknown":
        flags.append("battery_unknown")

    return ("REJECT" if reasons else "PASS"), reasons, flags
