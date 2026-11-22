"""AutoHebdo : annonces lues dans le JSON-LD (`schema.org ItemList`) d'une page de résultats (HTTP simple).

Limites connues : la liste n'expose ni l'année (elle vient de l'URL de recherche `my_YYYY`) ni la ville ni le
GPS ; le JSON-LD est analysé avec `json` + regex (pas de dépendance à BeautifulSoup).
"""
import html as html_lib
import json
import re
from typing import Any, Dict, List, Optional

SOURCE = "autohebdo"
_LD_JSON = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I)
_UUID_END = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def build_search_url(year: int) -> str:
    return f"https://www.autohebdo.net/autos/nissan/leaf/my_{year}/reg_qc"


def _source_id(url: str) -> str:
    last = url.rstrip("/").split("/")[-1]
    m = _UUID_END.search(last)
    return m.group(0) if m else last


def _to_int(value: Any) -> Optional[int]:
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return None


def _item_nodes(data: Any) -> List[Dict[str, Any]]:
    """Éléments d'un `ItemList` (dans `@graph` -> `mainEntity`, ou directement)."""
    nodes = data.get("@graph", [data]) if isinstance(data, dict) else []
    out: List[Dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        item_list = node.get("mainEntity") if isinstance(node.get("mainEntity"), dict) else node
        if item_list.get("@type") == "ItemList":
            out.extend(el for el in item_list.get("itemListElement", []) if isinstance(el, dict))
    return out


def parse_results_page(page_html: str, page_year: Optional[int] = None) -> List[Dict[str, Any]]:
    """Annonces brutes au format commun des sources Leaf. `page_year` : année de l'URL de recherche."""
    listings: List[Dict[str, Any]] = []
    for raw in _LD_JSON.findall(page_html or ""):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        for el in _item_nodes(data):
            item = el.get("item", el) if isinstance(el.get("item", el), dict) else el
            url = item.get("url") or el.get("url")
            if not url:
                continue
            mileage = item.get("mileageFromOdometer")
            offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
            year = item.get("vehicleModelDate") or item.get("productionDate")
            listings.append({
                "source": SOURCE,
                "source_id": _source_id(url),
                "id": f"leaf_{SOURCE}_{_source_id(url)}",
                "title": html_lib.unescape(item.get("name") or ""),
                "description": html_lib.unescape(item.get("description") or ""),
                "price": _to_int(offers.get("price")),
                "year": _to_int(year) or page_year,
                "km": _to_int(mileage.get("value")) if isinstance(mileage, dict) else _to_int(mileage),
                "model": None,
                "seller_type": None,
                "city": "",
                "latitude": None,
                "longitude": None,
                "url": url,
                "image_urls": [],
                "vin": item.get("vehicleIdentificationNumber"),
            })
    return listings
