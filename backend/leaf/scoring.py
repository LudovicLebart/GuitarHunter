"""Scores Leaf CALCULÉS EN CODE (jamais demandés à un modèle) : fonctions PURES.

Hypothèses (paramétrables ici, sources : EPA pour l'autonomie nominale, AVEQ/CAA-Québec pour le froid :
-25 % à -15 °C, -45 % à -25 °C) :
"""
from typing import Any, Dict, List, Optional, Sequence

NOMINAL_RANGE_KM = {24: 135, 30: 172, 40: 241}
COLD_FACTOR_MILD = 0.75    # -15 °C
COLD_FACTOR_SEVERE = 0.55  # -25 °C
SOH_REPLACED_LOW, SOH_REPLACED_HIGH = 95.0, 100.0   # batterie remplacée annoncée, preuve à confirmer
SOH_ASSUMED_LOW, SOH_ASSUMED_HIGH = 75.0, 90.0   # quand le SOH est inconnu : fourchette, jamais une valeur
DEFAULT_DAILY_KM = 50
DEFAULT_MARGIN = 1.5


def battery_score(soh_pct: Optional[float]) -> Optional[int]:
    """Barème déterministe. SOH inconnu -> None (« à mesurer avec LeafSpy »), jamais estimé."""
    if soh_pct is None:
        return None
    if soh_pct >= 90:
        return 10
    if soh_pct >= 85:
        return 8
    if soh_pct >= 80:
        return 5
    return 2


def winter_fit(listing: Dict[str, Any], daily_km: float = DEFAULT_DAILY_KM,
               margin: float = DEFAULT_MARGIN) -> Dict[str, Any]:
    """Autonomie hivernale = autonomie nominale x SOH x facteur de froid.
    Bas de fourchette : -25 °C ; haut : -15 °C. Verdict : ok / juste / insuffisant / inconnu."""
    k_low, k_high = listing.get("battery_kwh_low"), listing.get("battery_kwh_high")
    needed = round(daily_km * margin)
    if k_low not in NOMINAL_RANGE_KM or k_high not in NOMINAL_RANGE_KM:
        return {"low_km": None, "high_km": None, "needed_km": needed, "verdict": "inconnu",
                "soh_assumed": None}
    soh = listing.get("soh_announced")
    replaced = bool((listing.get("mentions") or {}).get("battery_replaced"))
    a_low, a_high = (SOH_REPLACED_LOW, SOH_REPLACED_HIGH) if replaced else (SOH_ASSUMED_LOW, SOH_ASSUMED_HIGH)
    soh_low = soh if soh is not None else a_low
    soh_high = soh if soh is not None else a_high
    low = round(NOMINAL_RANGE_KM[k_low] * soh_low / 100 * COLD_FACTOR_SEVERE)
    high = round(NOMINAL_RANGE_KM[k_high] * soh_high / 100 * COLD_FACTOR_MILD)
    if low >= needed:
        verdict = "ok"
    elif high >= needed:
        verdict = "juste"
    else:
        verdict = "insuffisant"
    return {"low_km": low, "high_km": high, "needed_km": needed, "verdict": verdict,
            "soh_assumed": None if soh is not None else (a_low, a_high)}


def equipment_score(listing: Dict[str, Any]) -> Dict[str, Any]:
    """Score /10 : pompe à chaleur 4, pneus d'hiver 3, sièges chauffants 2, volant chauffant 1.
    Pompe à chaleur déduite du trim SV/SL = comptée mais marquée « inferred » (à confirmer)."""
    m = listing.get("mentions") or {}
    heat_stated = bool(m.get("heat_pump"))
    heat_inferred = (not heat_stated) and listing.get("trim") in ("SV", "SL")
    points = 0
    points += 4 if (heat_stated or heat_inferred) else 0
    points += 3 if m.get("winter_tires") else 0
    points += 2 if m.get("heated_seats") else 0
    points += 1 if m.get("heated_wheel") else 0
    return {"score": points, "heat_pump_inferred": heat_inferred}


def risk_flags(listing: Dict[str, Any]) -> List[str]:
    flags = [f"accident:{w}" for w in listing.get("accident_flags") or []]
    if listing.get("soh_announced") is None:
        flags.append("soh_unknown")
    if listing.get("km") is None:
        flags.append("km_unknown")
    if listing.get("year") is None:
        flags.append("year_unknown")
    if listing.get("battery_kwh_low") == 24:
        replaced = (listing.get("mentions") or {}).get("battery_replaced")
        flags.append("battery_24_replaced" if replaced and listing.get("battery_source") == "stated"
                     else "battery_24_possible")
    return flags


def _solve3(a: List[List[float]], b: List[float]) -> Optional[List[float]]:
    """Élimination de Gauss 3x3 (pivot partiel). None si matrice singulière."""
    n = 3
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-9:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))) / m[r][r]
    return x


def price_fit(listing: Dict[str, Any], comparables: Sequence[Dict[str, Any]],
              min_comparables: int = 15) -> Optional[Dict[str, Any]]:
    """Écart du prix à une régression prix ~ année + km sur NOS annonces vues. None sous le seuil de
    comparables (« marché insuffisant ») : on n'invente pas un prix de marché."""
    rows = [(c["year"], c["km"], c["price"]) for c in comparables
            if c.get("year") and c.get("km") is not None and c.get("price")]
    if len(rows) < min_comparables or not listing.get("year") or listing.get("km") is None \
            or not listing.get("price"):
        return None
    # moindres carrés : price = b0 + b1*(year-2016) + b2*(km/10000)
    xs = [(1.0, r[0] - 2016.0, r[1] / 10000.0) for r in rows]
    ys = [float(r[2]) for r in rows]
    ata = [[sum(x[i] * x[j] for x in xs) for j in range(3)] for i in range(3)]
    atb = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(3)]
    beta = _solve3(ata, atb)
    if beta is None:
        return None
    expected = beta[0] + beta[1] * (listing["year"] - 2016.0) + beta[2] * (listing["km"] / 10000.0)
    if expected <= 0:
        return None
    delta = listing["price"] - expected
    return {"expected": round(expected), "delta": round(delta), "delta_pct": round(100 * delta / expected, 1),
            "n": len(rows)}
