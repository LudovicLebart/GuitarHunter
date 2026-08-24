"""
Posture de furtivité partagée entre les scrapers du projet (Facebook, Kijiji, LeBonCoin,
2026-08-24 — dette technique documentée dans TODO.md depuis le 2026-07-22).

Ce module ne porte QUE ce qui est identique en substance entre les trois scrapers : pools
UA/viewport, flags de lancement Playwright, sélection de proxy, pauses/gestes "humains". La
logique d'extraction (sélecteurs CSS Facebook, JSON __NEXT_DATA__ Kijiji/LeBonCoin) reste
propre à chaque module — rien à mutualiser là, les sites n'ont rien en commun sur ce plan.

Choix délibéré : des CONSTANTES et FONCTIONS partagées plutôt qu'une classe de base avec
héritage/composition sur `self.playwright`/`self.browser`/`self.context`. Les trois scrapers
ont des besoins de session réellement différents (Facebook : géolocalisation forcée par ville,
proxy ; Kijiji : rien de spécial ; LeBonCoin : `storage_state` persistant, `headless=False`
volontaire, session réutilisée entre recherches au lieu d'être refermée) — une hiérarchie de
classes aurait dû absorber ces différences via des points d'extension, pour un gain marginal
par rapport à réutiliser directement ces fonctions dans le `start_session()` propre à chacun.
Une classe commune resterait à faire si un 4e scraper apparaît avec un besoin de session
identique à un des trois existants.
"""
import logging
import random
import time

_module_logger = logging.getLogger(__name__)

# Union des listes UA/viewport auparavant dupliquées (avec variations) dans
# backend/scraping/core.py, backend/scraping/kijiji/core.py et
# backend/scraping_leboncoin/core.py — une seule liste à tenir à jour désormais.
USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Edge Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Chrome macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Safari macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 2560, "height": 1440},
]

# Flags Chromium communs aux trois scrapers — `--start-minimized` reste propre à
# FacebookScraper (comportement de fenêtre, pas une mesure de furtivité en soi).
STEALTH_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-sandbox",
]


def pick_user_agent_and_viewport(user_agents=None, viewports=None):
    """Tire un couple (UA, viewport) aléatoire. Pools par défaut = ceux de ce module ;
    un scraper peut passer les siens si besoin d'un sous-ensemble spécifique."""
    ua = random.choice(user_agents or USER_AGENTS)
    vp = random.choice(viewports or VIEWPORTS)
    return ua, vp


def build_proxy_config(proxies, logger=None):
    """Choisit un proxy au hasard dans `proxies` (voir config.py::PROXIES, vide par défaut)
    et retourne le dict attendu par `playwright.chromium.launch(proxy=...)`, ou None si la
    liste est vide — comportement inchangé (pas de proxy) tant que PROXIES n'est pas rempli."""
    if not proxies:
        return None
    selected_proxy = random.choice(proxies)
    (logger or _module_logger).info(f"🌐 Utilisation du proxy : {selected_proxy}")
    return {"server": selected_proxy}


def human_pause(low: float, high: float):
    """Pause aléatoire — jamais un délai fixe. Un `time.sleep(N)` identique à chaque
    interaction est lui-même un signal comportemental détectable dans la durée,
    indépendamment de son utilité fonctionnelle (attente de rendu, etc.)."""
    time.sleep(random.uniform(low, high))


def simulate_scroll_and_mouse(page, logger=None, iterations=None):
    """Scroll + déplacement de souris simulés — porté depuis LeboncoinScraper (2026-07-21,
    validé en conditions réelles face à DataDome) vers les autres scrapers. Aucun besoin
    fonctionnel pour Facebook/Kijiji (les cartes sont déjà dans le DOM après le défilement
    piloté par `page.mouse.wheel()` existant) : un signal comportemental gratuit en plus,
    pas un remplacement du défilement qui charge réellement les résultats.
    Avale ses propres erreurs (page fermée entre-temps, etc.) — jamais critique pour le scan.
    """
    try:
        n = iterations if iterations is not None else random.randint(1, 3)
        for _ in range(n):
            page.mouse.wheel(0, random.randint(300, 1000))
            human_pause(0.5, 1.8)
        page.mouse.move(random.randint(100, 800), random.randint(100, 600))
    except Exception as e:
        (logger or _module_logger).warning(f"Simulation scroll/souris échouée (non bloquant): {e}")
