from dataclasses import dataclass


@dataclass
class KijijiScraperConfig:
    """Configuration centralisée pour le scraper Kijiji."""
    headless: bool = True
    timeout_navigation: int = 60000
    timeout_selector: int = 15000
    max_scroll_iterations: int = 20
    locale: str = "fr-CA"
    timezone: str = "America/Montreal"
