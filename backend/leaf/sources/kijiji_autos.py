"""Kijiji Autos : annonces `AutosListing` lues dans `__NEXT_DATA__` d'une page de résultats (HTTP simple).

Même source de vérité que `backend/scraping/kijiji/parser.py` (état Apollo SSR), catégorie autos (c174) au lieu
de la catégorie guitares. Parseurs purs : testables sans réseau.
"""
from typing import Any, Dict, List, Optional

from backend.scraping.kijiji.parser import KijijiListingParser
from backend.leaf.sources import extract_next_data

AUTOS_CATEGORY_ID = 174
QUEBEC_LOCATION_ID = 9001
SOURCE = "kijiji"


def build_search_url(page: int = 1, min_price: Optional[int] = None, max_price: Optional[int] = None) -> str:
    """Recherche « nissan leaf » à l'échelle du Québec, triée par date ; filtre prix côté site."""
    page_part = "" if page <= 1 else f"/page-{page}"
    url = (f"https://www.kijiji.ca/b-autos-camions/quebec{page_part}/nissan-leaf/"
           f"k0c{AUTOS_CATEGORY_ID}l{QUEBEC_LOCATION_ID}")
    price = f"{min_price if min_price is not None else ''}__{max_price if max_price is not None else ''}"
    return f"{url}?price={price}&sort=dateDesc"


def _attrs(entry: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Attributs `canonicalName -> première valeur` (repli sur `values` : c'est là que vit `cartrim`)."""
    out: Dict[str, Optional[str]] = {}
    for a in ((entry.get("attributes") or {}).get("all") or []):
        values = a.get("canonicalValues") or a.get("values") or [None]
        out[a.get("canonicalName")] = values[0]
    return out


def entry_to_listing(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Un `AutosListing` Apollo -> annonce brute au format commun des sources Leaf (prix en dollars)."""
    attrs = _attrs(entry)
    loc = entry.get("location") or {}
    coords = loc.get("coordinates") or {}
    amount = (entry.get("price") or {}).get("amount")
    year, km = attrs.get("caryear"), attrs.get("carmileageinkms")
    return {
        "source": SOURCE,
        "source_id": str(entry.get("id")),
        "id": f"leaf_{SOURCE}_{entry.get('id')}",
        "title": entry.get("title") or "",
        "description": entry.get("description") or "",
        "price": round(amount / 100) if isinstance(amount, (int, float)) else None,   # Kijiji : en cents
        "year": int(year) if (year or "").isdigit() else None,
        "km": int(km) if (km or "").isdigit() else None,
        "model": attrs.get("carmodel"),
        "trim": None,                              # la liste ne le donne pas : lu sur la fiche (`cartrim`)
        "seller_type": attrs.get("forsaleby"),     # 'ownr' (particulier) / 'delr' (commerçant)
        "city": (loc.get("address") or loc.get("name") or "").strip(),
        "latitude": coords.get("latitude"),
        "longitude": coords.get("longitude"),
        "url": entry.get("url"),
        "image_urls": list(entry.get("imageUrls") or []),
        "vin": None,
    }


def parse_search_page(html: str) -> List[Dict[str, Any]]:
    data = extract_next_data(html)
    if not data:
        return []
    entries = KijijiListingParser._pick_all_standard_listings(data, prefixes=("AutosListing:",))
    return [entry_to_listing(e) for e in entries.values()]


def parse_detail_page(html: str, source_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fiche d'une annonce : description COMPLÈTE (la liste la tronque), trim, GPS, type de vendeur.
    None si la page n'a pas d'état Apollo exploitable."""
    data = extract_next_data(html)
    if not data:
        return None
    entries = KijijiListingParser._pick_all_standard_listings(data, prefixes=("AutosListing:",))
    entry = entries.get(str(source_id)) if source_id is not None else None
    entry = entry or next(iter(entries.values()), None)
    if not entry:
        return None
    full = entry_to_listing(entry)
    trim = (_attrs(entry).get("cartrim") or "").strip().upper()
    return {
        "description": full["description"],
        "trim": trim or None,
        "city": full["city"], "latitude": full["latitude"], "longitude": full["longitude"],
        "seller_type": full["seller_type"],
        "year": full["year"], "km": full["km"],
    }
