from dataclasses import dataclass
from typing import Dict

@dataclass
class ScraperConfig:
    """Configuration centralisée pour le scraper."""
    # `headless=False` (2026-08-25, retour utilisateur) : un test manuel en navigateur "anonyme"
    # (donc sans compte, comme ce scraper) ne montrait jamais le remplissage international massif
    # (annonces belges) observé en production — seule différence structurelle restante avec le
    # bot : le mode headless. `scraping_leboncoin/core.py` tourne déjà en `headless=False` sur ce
    # même serveur (Xvfb déjà installé pour lui, voir `.github/workflows/deploy.yml`) — même
    # process/service que Facebook, donc le DISPLAY déjà fonctionnel pour LeBonCoin doit l'être
    # tout autant ici, sans changement d'infrastructure nécessaire.
    headless: bool = False
    timeout_navigation: int = 60000
    timeout_selector: int = 15000
    max_scroll_iterations: int = 20
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    locale: str = "fr-CA"
    timezone: str = "America/Montreal"
    geolocation: Dict[str, float] = None

    def __post_init__(self):
        if self.geolocation is None:
            self.geolocation = {"latitude": 45.5017, "longitude": -73.5673}
