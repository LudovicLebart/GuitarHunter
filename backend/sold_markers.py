"""Marqueurs textuels de vente déjà conclue, partagés entre `bot.py` et les scrapers (2026-08-17).

Un vendeur qui ne supprime pas son annonce édite parfois son titre ou sa description pour
signaler la vente ("VENDU - Fender Strat...", "SOLD!!"). Deux points du pipeline doivent
détecter ce même signal, sur des textes différents :
  - `bot.py::handle_deal_found` — au moment de la découverte, sur titre + description.
  - `FacebookScraper`/`KijijiScraper::check_listing_availability()` — lors du nettoyage
    périodique, sur le titre actuel (`og:title`) d'une fiche déjà en base qui n'a ni disparu
    (404) ni redirigé, mais dont le titre a changé depuis.

Recherche par sous-chaîne (`in`), volontairement non ancrée : contrairement aux badges de statut
détectés par `check_listing_availability()` (regex `^vendu$` stricte, pour ne pas confondre un
badge "Vendu" avec un mot dans une description libre), un titre peut légitimement contenir le
marqueur n'importe où ("VENDU - Fender Strat 62", "Fender Strat 62 - SOLD").
"""

SOLD_MARKERS = ['vendu', 'sold', 'deal closed', 'plus disponible', 'no longer available']


def find_sold_marker(text):
    """Retourne le premier marqueur de `SOLD_MARKERS` trouvé dans `text` (insensible à la casse),
    ou `None`. `text` peut être `None` ou vide."""
    text_lower = (text or '').lower()
    return next((m for m in SOLD_MARKERS if m in text_lower), None)


# Fragments d'URL d'une page de blocage (connexion, captcha, point de contrôle) : la fiche n'a
# alors pas été vue, on ne sait rien de sa disponibilité (revue R-3-2, 2026-11-06).
BLOCK_URL_MARKERS = ('/login', '/checkpoint', 'captcha', 'recaptcha', '/challenge', 'consent.')


def is_block_page_url(url):
    """True si `url` est une page de blocage anti-bot ou de connexion, pas une fiche."""
    url_lower = (url or '').lower()
    return any(m in url_lower for m in BLOCK_URL_MARKERS)
