"""
Résolution ville -> ID de lieu Kijiji.

Kijiji publie un arbre statique et complet de TOUS ses lieux, pour tout le Canada, via
`https://www.kijiji.ca/j-locations.json` (confirmé en test live du 2026-07-26 : le
paramètre `q` (ex: `?q=Quebec`, `?q=Ontario`) ne filtre en réalité rien — vérifié par
diagnostic comparatif [`diag_kijiji_locations_scope.py`] puis confirmé par recherche
directe de l'ID de Toronto, 1700273, présent dans la réponse peu importe `q`). Un seul
appel HTTP couvre donc déjà toutes les provinces. Contrairement à Facebook
(`FacebookScraper.get_city_id_and_coords()`, qui doit piloter le sélecteur de lieu du
site une ville à la fois), on peut résoudre n'importe quelle ville canadienne sans
navigateur.

Voir `backend/scripts/fetch_kijiji_locations.py` pour télécharger/actualiser le fichier
ressource (`backend/resources/kijiji_locations.json`) consommé par `load_location_lookup()`.
"""
import json
import logging
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional

from ..utils import calculate_distance

from ..parser import ListingParser

_module_logger = logging.getLogger(__name__)

_DEFAULT_RESOURCE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "resources", "kijiji_locations.json")
)


def parse_locations_response(raw_text: str) -> Dict[str, Any]:
    """`j-locations.json` renvoie du JavaScript (`var locationsTree = {...};`), pas du
    JSON pur — on retire l'enrobage avant de parser."""
    text = raw_text.strip()
    if "=" in text.split("{", 1)[0]:
        text = text.split("=", 1)[1].strip()
    if text.endswith(";"):
        text = text[:-1]
    return json.loads(text)


def flatten_locations_tree(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Aplatit l'arbre hiérarchique (province > région > ville) en une liste de lieux
    terminaux (`leaf: true` uniquement — les régions agrégées comme "Grand Montréal" ne
    sont pas des lieux de recherche valides individuellement, seules leurs villes le sont)."""
    leaves: List[Dict[str, Any]] = []

    def _walk(node: Any):
        if not isinstance(node, dict):
            return
        if node.get("leaf") and node.get("id") is not None:
            leaves.append({
                "id": node["id"],
                "nameEn": node.get("nameEn"),
                "nameFr": node.get("nameFr"),
                "homePageSEOUrl": node.get("homePageSEOUrl"),
            })
        for child in node.get("children") or []:
            _walk(child)

    _walk(tree)
    return leaves


def location_slug_from_seo_url(home_page_seo_url: Optional[str]) -> Optional[str]:
    """Extrait le slug depuis `homePageSEOUrl` (ex: "/h-longueuil-rive-sud/1700279"
    -> "longueuil-rive-sud")."""
    if not home_page_seo_url:
        return None
    parts = [p for p in home_page_seo_url.split("/") if p]
    if not parts:
        return None
    first = parts[0]
    return first[2:] if first.startswith("h-") else first


def build_location_lookup(leaves: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Construit un dict {nom_normalisé: {id, slug}}, à partir des noms EN et FR de
    chaque lieu (réutilise `ListingParser.normalize_city_name` pour rester cohérent avec
    le reste du projet — mapping `cities` Firestore, `city_coordinates.json`)."""
    lookup: Dict[str, Dict[str, Any]] = {}
    for leaf in leaves:
        slug = location_slug_from_seo_url(leaf.get("homePageSEOUrl"))
        for name in (leaf.get("nameEn"), leaf.get("nameFr")):
            if not name:
                continue
            normalized = ListingParser.normalize_city_name(name)
            if normalized and normalized not in lookup:
                lookup[normalized] = {"id": leaf["id"], "slug": slug}
    return lookup


def load_location_lookup(path: str = None) -> Dict[str, Dict[str, Any]]:
    """Charge le lookup ville -> {id, slug} depuis le fichier ressource généré par
    `backend/scripts/fetch_kijiji_locations.py`. Retourne un dict vide si absent — le
    scraper reste utilisable sans, simplement sans résolution automatique de ville."""
    resolved_path = path or _DEFAULT_RESOURCE_PATH
    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        _module_logger.debug(f"Lookup de lieux Kijiji introuvable/invalide ({resolved_path}): {e}")
        return {}


def resolve_location(city_name: str, lookup: Dict[str, Dict[str, Any]], log: logging.Logger = None) -> Optional[Dict[str, Any]]:
    """
    Résout un nom de ville vers `{id, slug}`. Kijiji regroupe certaines grandes villes
    sous un nom "Ville / Région" (ex: "Longueuil / South Shore") — une recherche pour
    "Longueuil" seul ne matche donc pas exactement la clé normalisée complète ; on
    compare aussi contre la partie avant le "/".

    Volontairement STRICT au-delà de ces deux cas (pas de repli par correspondance
    partielle/substring) : validé empiriquement contre les 192 lieux Kijiji réels
    (`backend/resources/kijiji_locations.json`) et les 839 municipalités QC
    (`city_coordinates.json`) — un simple test `normalized in key` matchait à tort des
    villes québécoises vers des lieux homonymes d'AUTRES provinces (ex: "Waterloo" (QC)
    → "Kitchener / Waterloo" (ON), "Abbotsford" (QC, Saint-Paul-d'Abbotsford) →
    "Abbotsford" (BC), "Stoke" (QC) → "Revelstoke" (BC), "Oka" (QC) → "Muskoka" (ON)),
    et rendait "Québec" ambigu contre "Chibougamau / Nord-du-Québec" (mot "quebec"
    partagé, lieu totalement différent). Kijiji ne couvrant qu'~192 grandes sous-zones
    pour tout le pays, la plupart des petites municipalités n'ont simplement AUCUN
    équivalent Kijiji par nom — retourner `None` (ville ignorée pour Kijiji, journalisé
    par l'appelant) est le comportement correct dans ce cas, pas un bug à contourner par
    du matching plus permissif.
    """
    log = log or _module_logger
    if not city_name or not lookup:
        return None
    normalized = ListingParser.normalize_city_name(city_name)

    if normalized in lookup:
        return lookup[normalized]

    for key, value in lookup.items():
        prefix = key.split("/")[0].strip()
        if prefix == normalized:
            return value

    return None


def build_search_url(category_id: int, location_id: int, query: str,
                      category_slug: str = "recherche", location_slug: str = "lieu",
                      min_price: int = 0, max_price: int = 0,
                      lat: float = None, lng: float = None, radius_km: float = None) -> str:
    """
    Construit une URL de résultats de recherche Kijiji à partir d'IDs de catégorie et de
    lieu déjà résolus (catégorie : ID global stable pour tout le site, ex: 613 = Guitars ;
    lieu : voir `resolve_location`).

    ⚠️ Les segments texte du chemin (`category_slug`/`location_slug`) semblent cosmétiques
    — les URLs `/b-guitare/...` (FR) et `/b-guitar/...` (EN) ont toutes deux fonctionné en
    test live pour la même annonce, seul le suffixe `k0c<id>l<id>` semblant réellement
    déterminer les résultats. Non vérifié avec un slug complètement arbitraire : utiliser
    les vrais slugs quand disponibles (`resolve_location(...)["slug"]`) reste le choix le
    plus sûr.

    `min_price`/`max_price` : filtre de prix côté recherche (format `price=min__max`,
    déduit d'une URL de résultats réelle — non confirmé par diagnostic live, voir
    `test_kijiji_scraper.py --search-url` pour valider). Filtre au moins un des deux bords
    déjà appliqué avant d'ajouter le paramètre ; un bord absent est laissé vide (ex:
    `price=100__` pour "100$ et plus").

    `lat`/`lng`/`radius_km` : filtre géographique (`ll=lat,lng&radius=...`, même mécanisme
    que celui utilisé par le site pour "Within Xkm" — voir `searchQuery.area` dans
    `__NEXT_DATA__`). Le sélecteur de rayon du site Kijiji n'autorise pas 0km : l'appelant
    doit passer une valeur >= 1 (voir `bot.py::_run_kijiji_scan`).
    """
    query_slug = _slugify(query) or "recherche"
    url = f"https://www.kijiji.ca/b-{category_slug}/{location_slug}/{query_slug}/k0c{category_id}l{location_id}"

    params = []
    if min_price > 0 or max_price > 0:
        min_part = str(min_price) if min_price > 0 else ""
        max_part = str(max_price) if max_price > 0 else ""
        params.append(f"price={min_part}__{max_part}")
    if lat is not None and lng is not None and radius_km is not None and radius_km > 0:
        params.append(f"ll={lat}%2C{lng}")
        params.append(f"radius={radius_km}")

    if params:
        url += "?" + "&".join(params)
    return url


def _is_number(value: Any) -> bool:
    """`bool` est une sous-classe d'`int` en Python mais n'est pas une coordonnée valide."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _slugify(text: str) -> str:
    """Retire les accents (ex: "électrique" -> "electrique", pas "lectrique") avant de
    remplacer tout caractère non alphanumérique par un tiret."""
    ascii_text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("utf-8")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def nearest_configured_city(latitude: Optional[float], longitude: Optional[float],
                             city_coordinates: Dict[str, Dict[str, float]],
                             max_radius_km: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """
    Retourne la ville configurée la plus proche de (latitude, longitude), par distance
    Haversine (`scraping.utils.calculate_distance`).

    Plus fiable que `location.name`/`location.address` d'une annonce Kijiji pour savoir
    à quelle ville configurée elle appartient : `location.name` reflète le choix du
    VENDEUR au moment de poster l'annonce (parfois son village exact, parfois une grande
    région Kijiji comme "Longueuil / South Shore" — constaté en test live du 2026-07-26,
    incohérent d'une annonce à l'autre), alors que les coordonnées GPS sont toujours
    présentes et précises.

    `city_coordinates` : même format que `backend/resources/city_coordinates.json`
    (`{"nom_ville": {"lat": ..., "lng": ...}, ...}`).
    `max_radius_km` : si fourni, retourne `None` plutôt que la ville la plus proche si
    celle-ci est quand même à plus de cette distance (évite de rattacher une annonce
    lointaine à une ville configurée qui n'est en réalité pas pertinente pour elle).
    """
    if not _is_number(latitude) or not _is_number(longitude) or not city_coordinates:
        return None

    nearest_name = None
    nearest_distance = None
    for city_name, coords in city_coordinates.items():
        if not isinstance(coords, dict):
            continue
        city_lat, city_lng = coords.get("lat"), coords.get("lng")
        if not _is_number(city_lat) or not _is_number(city_lng):
            # Un lat/lng non numérique ferait planter math.radians() dans
            # calculate_distance(), qui capture l'exception et retourne 0 — une entrée
            # malformée "gagnerait" alors silencieusement comme ville la plus proche
            # (0 étant la distance minimale possible). On l'exclut explicitement au lieu
            # de laisser ce faux 0 concourir.
            continue
        distance = calculate_distance(latitude, longitude, city_lat, city_lng)
        if nearest_distance is None or distance < nearest_distance:
            nearest_distance = distance
            nearest_name = city_name

    if nearest_name is None:
        return None
    if max_radius_km is not None and nearest_distance > max_radius_km:
        return None

    return {"city": nearest_name, "distance_km": round(nearest_distance, 2)}
