"""Facebook Marketplace pour Leaf (2026-11-23) : réutilise le scraper Playwright des guitares (`FacebookScraper`) sans le modifier.

Contrairement aux autres sources Leaf (HTTP simple), celle-ci ouvre un navigateur : elle est donc OPTIONNELLE (`sources` de
`leafConfig`, absente par défaut), importe Playwright seulement quand on la lance, et son scraper est créé DANS le fil appelant
(Playwright n'est pas thread-safe). Le tri géographique se fait par le pipeline (GPS de la fiche, `home`), pas par la liste de
villes des guitares : `LeafFacebookScraper` laisse passer toutes les cartes.

`deal_to_raw` est PUR (testé sans navigateur) : il met une annonce du scraper au format commun des sources Leaf, pour que
normalisation, règles, scores et doublons s'appliquent tels quels. Année, km et version ne sont pas des champs structurés ici :
ils sont lus dans le titre/la description par `normalize`. Si le texte ne dit pas l'année, l'annonce n'est PAS écartée
(`year_optional` : drapeau `year_unknown`), car une carte Facebook range souvent l'année dans des attributs que le scraper ne lit pas."""
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

SOURCE = "facebook"
SEARCH_QUERY = "nissan leaf"
ITEM_URL = "https://www.facebook.com/marketplace/item/{id}/"


def deal_to_raw(deal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Annonce du scraper Facebook -> annonce brute Leaf. None si elle n'a pas d'identifiant. Rien n'est deviné : une absence reste None."""
    fb_id = str(deal.get("id") or "").strip()
    if not fb_id:
        return None
    price = deal.get("price")
    images = [u for u in (deal.get("imageUrls") or []) if isinstance(u, str) and u.startswith("https://")]
    if not images and isinstance(deal.get("imageUrl"), str) and deal["imageUrl"].startswith("https://"):
        images = [deal["imageUrl"]]
    return {
        "source": SOURCE,
        "source_id": fb_id,
        "id": f"leaf_{SOURCE}_{fb_id}",
        "title": deal.get("title") or "",
        "description": deal.get("description") or "",
        "price": round(price) if isinstance(price, (int, float)) and not isinstance(price, bool) else None,
        "year": None, "km": None, "trim": None, "model": None, "vin": None, "seller_type": None,
        "year_optional": True,        # année absente du texte : gardée avec un drapeau plutôt qu'écartée en silence
        "detail_fetched": True,       # le scraper Facebook a DÉJÀ lu la fiche : pas de seconde lecture (aucun parseur de fiche)
        "city": deal.get("location") or "",
        "latitude": deal.get("latitude"), "longitude": deal.get("longitude"),
        "url": ITEM_URL.format(id=fb_id),
        "image_urls": images,
    }


def _scan_config(scan: Dict[str, Any], location: str, max_ads: int) -> Dict[str, Any]:
    return {"search_query": SEARCH_QUERY, "location": location, "min_price": scan["min_price"],
            "max_price": scan["max_price"], "max_ads": max_ads}


def _make_scraper(city_id: str, location: str, logger: logging.Logger, coords: Optional[Dict[str, float]] = None):
    from backend.scraping.core import FacebookScraper          # import tardif : Playwright seulement si la source est activée

    class LeafFacebookScraper(FacebookScraper):
        def is_city_allowed(self, city_name):                   # le tri par distance est fait par le pipeline (GPS)
            return True

    scraper = LeafFacebookScraper({}, {}, logger=logger)
    scraper.city_mapping = {location: city_id}
    if coords:        # force la géolocalisation du navigateur sur la ville cherchée (sinon : résultats selon l'IP du serveur)
        scraper.city_coordinates = {location: {"lat": coords["latitude"], "lng": coords["longitude"]}}
    return scraper


def collect_facebook(scan: Dict[str, Any], logger: Optional[logging.Logger] = None,
                     scraper_factory: Callable[..., Any] = _make_scraper, max_ads: int = 20,
                     should_skip: Optional[Callable[[str, Any], bool]] = None, stop_event: Optional[Any] = None
                     ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """(annonces brutes, passage au format de `collect_sources`). `scan['facebook_city']` = {'id': ID/slug Facebook, 'name'} ;
    absent -> passage « skipped » sans rien lancer. Ne lève jamais : un échec devient un résultat `error`/`blocked`."""
    from backend.scrape_health import classify_facebook      # codes de résultat partagés avec les guitares
    log = logger or logging.getLogger(__name__)
    city = scan.get("facebook_city") or {}
    if not city.get("id"):
        return [], {"source": SOURCE, "outcome": "skipped", "detail": "aucune ville Facebook configurée", "cards_seen": 0, "duration_ms": 0}
    t0 = time.time()
    scraper = None
    try:
        from backend.scraping.parser import ListingParser
        location = ListingParser.normalize_city_name(city.get("name") or str(city["id"]))
        coords = {"latitude": city["latitude"], "longitude": city["longitude"]} \
            if city.get("latitude") is not None and city.get("longitude") is not None else None
        scraper = scraper_factory(str(city["id"]), location, log, coords)
        # `should_skip` : annonce déjà connue au même prix (pas de fiche rouverte) ; `stop_event` : STOP_BOT / STOP_SCAN interrompent.
        result = scraper.scan_marketplace(_scan_config(scan, location, max_ads), should_skip, stop_event=stop_event, allow_catchup=False)
        outcome, detail = classify_facebook(result)
        raws = [r for r in (deal_to_raw(d) for d in (result.get("deals") or [])) if r]
        return raws, {"source": SOURCE, "outcome": outcome, "detail": detail or None,
                      "cards_seen": result.get("total_cards_seen", 0) or 0, "duration_ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        log.error(f"[Leaf] Facebook : {e}", exc_info=True)
        return [], {"source": SOURCE, "outcome": "error", "detail": str(e)[:300], "cards_seen": 0,
                    "duration_ms": int((time.time() - t0) * 1000)}
    finally:
        if scraper is not None:
            try:
                scraper.close_session()
            except Exception:
                pass
