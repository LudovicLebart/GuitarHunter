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


def resolve_location(city_name: str, lookup: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Résout un nom de ville vers `{id, slug}`. Kijiji regroupe certaines grandes villes
    sous un nom "Ville / Région" (ex: "Longueuil / South Shore") — une recherche pour
    "Longueuil" seul ne matche donc pas exactement la clé normalisée complète ; on
    compare aussi contre la partie avant le "/". Dernier repli : correspondance
    partielle (best-effort, peut être ambiguë sur de grandes listes de lieux).
    """
    if not city_name or not lookup:
        return None
    normalized = ListingParser.normalize_city_name(city_name)

    if normalized in lookup:
        return lookup[normalized]

    for key, value in lookup.items():
        prefix = key.split("/")[0].strip()
        if prefix == normalized:
            return value

    for key, value in lookup.items():
        if normalized in key or key in normalized:
            return value

    return None


def build_search_url(category_id: int, location_id: int, query: str,
                      category_slug: str = "recherche", location_slug: str = "lieu") -> str:
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
    """
    query_slug = _slugify(query) or "recherche"
    return f"https://www.kijiji.ca/b-{category_slug}/{location_slug}/{query_slug}/k0c{category_id}l{location_id}"


def _slugify(text: str) -> str:
    """Retire les accents (ex: "électrique" -> "electrique", pas "lectrique") avant de
    remplacer tout caractère non alphanumérique par un tiret."""
    ascii_text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("utf-8")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
