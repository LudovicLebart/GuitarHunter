"""Enchaînement pur Leaf : brut -> normalisé -> filtré -> règles -> scores -> doublons. Aucun accès base/réseau."""
from typing import Any, Dict, List, Optional, Sequence

from backend.leaf import dedup, filters, normalize, rules, scoring


def evaluate_listings(raws: Sequence[Dict[str, Any]], criteria: Optional[Dict[str, Any]] = None,
                      soh_min_reject: float = rules.DEFAULT_SOH_MIN_REJECT,
                      home: Optional[Dict[str, Any]] = None,
                      daily_km: float = scoring.DEFAULT_DAILY_KM) -> Dict[str, List[Dict[str, Any]]]:
    """Retourne {'kept': [...], 'rejected': [...], 'ignored': [...]} .
    - ignored : hors périmètre (année, prix, km, distance...) — ne serait pas stocké ;
    - rejected : dans le périmètre mais écarté par les règles du Portier (raisons fournies) ;
    - kept : annonces à stocker/afficher, triées par prix puis km, avec scores et `duplicate_of`.
    `home` : {'latitude', 'longitude', 'max_km'} pour le filtre de distance (optionnel)."""
    kept: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    ignored: List[Dict[str, Any]] = []
    seen_ids = set()

    for raw in raws:
        if raw.get("id") in seen_ids:
            continue
        seen_ids.add(raw.get("id"))
        listing = normalize.normalize_listing(raw)

        ok, reason = filters.passes_criteria(listing, criteria)
        if ok and home:
            ok_dist, dist = filters.within_distance(listing, home.get("latitude"), home.get("longitude"),
                                                    home.get("max_km"))
            listing["distance_km"] = dist
            if not ok_dist:
                ok, reason = False, "distance"
        if not ok:
            ignored.append({**listing, "ignored_reason": reason})
            continue

        decision, reject_reasons, flags = rules.gatekeeper_rules(listing, soh_min_reject)
        listing["flags"] = flags
        if decision == "REJECT":
            rejected.append({**listing, "reject_reasons": reject_reasons})
            continue

        listing["battery_score"] = scoring.battery_score(listing.get("soh_announced"))
        listing["winter_fit"] = scoring.winter_fit(listing, daily_km=daily_km)
        listing["equipment"] = scoring.equipment_score(listing)
        listing["risk_flags"] = scoring.risk_flags(listing)
        listing["duplicate_of"] = None
        for earlier in kept:
            if dedup.same_vehicle(listing, earlier):
                listing["duplicate_of"] = earlier["id"]
                break
        kept.append(listing)

    kept.sort(key=lambda a: (a["price"], a["km"] if a.get("km") is not None else 10**9))
    return {"kept": kept, "rejected": rejected, "ignored": ignored}
