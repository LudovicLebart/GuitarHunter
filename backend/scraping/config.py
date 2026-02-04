from dataclasses import dataclass
from typing import Dict

@dataclass
class ScraperConfig:
    """Configuration centralisée pour le scraper."""
    headless: bool = False
    timeout_navigation: int = 60000
    timeout_selector: int = 15000
    scroll_iterations: int = 3
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    locale: str = "fr-CA"
    timezone: str = "America/Montreal"
    geolocation: Dict[str, float] = None

    def __post_init__(self):
        if self.geolocation is None:
            self.geolocation = {"latitude": 45.5017, "longitude": -73.5673}
