"""Verdict Leaf calculé EN CODE (jamais par l'IA) à partir des scores et drapeaux : fonction PURE.

CANDIDAT_FORT, A_VERIFIER, BATTERIE_DOUTEUSE, TROP_CHER, INCOMPLET. (HORS_CRITERES n'existe pas ici : une annonce hors critères
n'est jamais stockée.) Ce verdict est un tri pour l'utilisateur, pas une décision : il dit pourquoi (`reasons`)."""
from typing import Any, Dict, List

SOH_DOUBTFUL_BELOW = 85.0
BARS_DOUBTFUL_AT_OR_BELOW = 9          # jauge de capacité du tableau de bord : 9 barres ou moins sur 12 = batterie nettement dégradée
SOH_STRONG_FROM = 88.0
TOO_EXPENSIVE_PCT = 15.0            # prix supérieur de 15 % ou plus au prix de marché estimé
CHEAP_ENOUGH_PCT = 5.0              # prix au plus 5 % au-dessus du marché pour un « candidat fort »

LABELS = {
    "CANDIDAT_FORT": "Candidat fort",
    "A_VERIFIER": "À vérifier",
    "BATTERIE_DOUTEUSE": "Batterie douteuse",
    "TROP_CHER": "Trop cher",
    "INCOMPLET": "Informations incomplètes",
}


def compute_verdict(listing: Dict[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []
    soh = listing.get("soh_announced")
    fit = listing.get("price_fit") or None
    winter = (listing.get("winter_fit") or {}).get("verdict")
    flags = set(listing.get("flags") or []) | set(listing.get("risk_flags") or [])
    has_accident_flag = any(f.startswith("accident:") or f == "ai_accident_mentioned" for f in flags)

    if soh is not None and soh < SOH_DOUBTFUL_BELOW:
        return {"verdict": "BATTERIE_DOUTEUSE", "reasons": [f"SOH annoncé {soh:.0f} % (sous {SOH_DOUBTFUL_BELOW:.0f} %)"]}
    bars = listing.get("capacity_bars")
    if soh is None and bars is not None and bars <= BARS_DOUBTFUL_AT_OR_BELOW:
        return {"verdict": "BATTERIE_DOUTEUSE", "reasons": [f"jauge de capacité : {bars} barres sur 12 au tableau de bord"]}
    if fit and fit.get("delta_pct") is not None and fit["delta_pct"] >= TOO_EXPENSIVE_PCT:
        return {"verdict": "TROP_CHER", "reasons": [f"{fit['delta_pct']:.0f} % au-dessus du prix de marché estimé"]}
    missing = [name for name, value in (("année", listing.get("year")), ("kilométrage", listing.get("km"))) if value is None]
    if missing:
        return {"verdict": "INCOMPLET", "reasons": [f"{' et '.join(missing)} inconnu(s)"]}
    replaced_with_proof = bool((listing.get("mentions") or {}).get("battery_replaced")) and listing.get("battery_kwh_low") == 24
    strong_battery = soh is not None and soh >= SOH_STRONG_FROM
    if (strong_battery or replaced_with_proof) and winter in ("ok", "juste") and not has_accident_flag \
            and (not fit or fit.get("delta_pct") is None or fit["delta_pct"] <= CHEAP_ENOUGH_PCT):
        reasons.append(f"SOH annoncé {soh:.0f} %" if strong_battery else "batterie remplacée (preuve à demander)")
        reasons.append(f"autonomie hivernale {winter}")
        return {"verdict": "CANDIDAT_FORT", "reasons": reasons}
    if soh is None:
        reasons.append("SOH inconnu : à mesurer avec LeafSpy")
    if has_accident_flag:
        reasons.append("mention d'accident ou de dommage")
    return {"verdict": "A_VERIFIER", "reasons": reasons or ["rien d'anormal, mais rien de prouvé non plus"]}
