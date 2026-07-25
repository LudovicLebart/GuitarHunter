"""
Base commune pour les scrapers de marketplace basés sur Playwright, en mode
"douce" (stealth léger : rotation UA/viewport, flags anti-détection — SANS
contournement actif type SSL Pinning/TLS spoofing). Gère uniquement le cycle
de vie de la session (démarrage/fermeture, onglet réutilisé) ; à charge de la
sous-classe de fournir la logique propre au site (construction d'URL,
extraction, détection de blocage).

À sous-classer par un scraper de site spécifique (LeboncoinScraper, et les
futurs modules — Kijiji, Reverb...).

FacebookScraper (backend/scraping/core.py) n'hérite PAS de cette classe pour
l'instant — c'est un scraper en production (proxy, géolocalisation, en-têtes
spécifiques à gérer) ; une migration éventuelle est un chantier distinct et
délibéré (voir docs/management/TODO.md), pas un effet de bord de ce refactor.
"""
import logging
import random

from playwright.sync_api import sync_playwright

from .human_behavior import HumanBehaviorMixin

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]
DEFAULT_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
]
DEFAULT_STEALTH_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled", "--disable-infobars", "--no-sandbox",
]


class BaseMarketplaceScraper(HumanBehaviorMixin):
    """`storage_state_path` est optionnel : fournir un chemin pour une session
    authentifiée persistée (ex: LeBonCoin), ou laisser `None` pour une session
    anonyme. Les sous-classes peuvent surcharger `user_agents`/`viewports`/
    `stealth_launch_args` si besoin d'un jeu différent du défaut partagé."""

    user_agents = DEFAULT_USER_AGENTS
    viewports = DEFAULT_VIEWPORTS
    stealth_launch_args = DEFAULT_STEALTH_LAUNCH_ARGS
    locale = "fr-FR"

    def __init__(self, storage_state_path=None, logger=None):
        self.storage_state_path = storage_state_path
        self.logger = logger or logging.getLogger(__name__)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None  # onglet réutilisé sur toute la session (pas de nouvel onglet par recherche)
        self._responses = []
        self._mouse_pos = (640, 400)  # position de départ arbitraire, mise à jour à chaque déplacement

    def start_session(self):
        """Démarre la session Playwright. Sans effet si déjà démarrée — permet
        d'appeler search() plusieurs fois dans la même session (comportement
        humain : l'onglet reste ouvert, on relance des recherches)."""
        if self.context:
            return
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=False, args=self.stealth_launch_args)
        ua = random.choice(self.user_agents)
        vp = random.choice(self.viewports)
        context_kwargs = {"user_agent": ua, "viewport": vp, "locale": self.locale}
        if self.storage_state_path:
            context_kwargs["storage_state"] = self.storage_state_path
        self.context = self.browser.new_context(**context_kwargs)
        self.logger.info("Session démarrée.")

    def close_session(self):
        if self.context:
            self.context.close()  # ferme aussi self.page
            self.context = None
        self.page = None
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
        self.logger.info("Session fermée.")

    def _ensure_session(self):
        if not self.context:
            self.start_session()

    def _get_page(self):
        """Onglet unique réutilisé pour toutes les recherches de la session — un
        humain relance des recherches dans le même onglet, il n'en ouvre pas un
        nouveau à chaque fois. Recréé seulement si absent ou fermé (ex: fermé
        manuellement par l'utilisateur).

        Le listener ne retient que (status, url) des réponses 403/429 — pas
        l'objet Response complet (headers/corps) de CHAQUE requête (images, JS,
        CSS...), qui s'accumulerait inutilement pendant les dizaines de secondes
        de lecture décorative sur chaque page."""
        if self.page is None or self.page.is_closed():
            self.page = self.context.new_page()
            self.page.on("response", lambda r: self._responses.append((r.status, r.url)) if r.status in (403, 429) else None)
        return self.page
