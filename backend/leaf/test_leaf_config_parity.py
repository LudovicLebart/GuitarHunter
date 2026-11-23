"""Parité entre la validation de l'API (`backend/api/leaf_config.py`, autonome pour l'API de production) et celle du bot
(`backend/leaf/config.py`) : les deux doivent donner les MÊMES réglages effectifs pour un même `leafConfig` stocké.
Sans Postgres ni réseau."""
import unittest

from backend.api import leaf_config as api_cfg
from backend.leaf import config as bot_cfg

CASES = [
    None, {}, {"enabled": True}, {"enabled": "true"},
    {"scanConfig": {"frequency": 5, "pages": 99, "max_price": 100, "min_price": 2000, "years": [1999, 2017, "x"],
                    "sources": ["nope"], "max_km": "abc"}},
    {"scanConfig": {"frequency": 99999, "max_km": 0, "radius_km": 0}},
    {"scanConfig": {"home": {"latitude": 45.5}}},
    {"scanConfig": {"home": {"latitude": 46.1, "longitude": -72.0}, "radius_km": 80, "read_details": False}},
    {"scanConfig": {"sources": ["autohebdo"], "years": [2018]}, "notify": {"enabled": False, "new": False}},
    {"scanConfig": {"min_price": True, "max_price": None}},
]


def bot_view(raw):
    c = bot_cfg.normalize_config(raw)
    s = c["scan"]
    return {"enabled": c["enabled"], "frequency": s["frequency"], "years": s["years"], "min_price": s["min_price"],
            "max_price": s["max_price"], "max_km": s["max_km"], "pages": s["pages"], "sources": s["sources"],
            "read_details": s["read_details"], "lat": s["home"]["latitude"], "lon": s["home"]["longitude"],
            "radius": s["home"]["max_km"], "notify": c["notify"]}


def api_view(raw):
    c = api_cfg.effective(raw)
    s = c["scan"]
    return {"enabled": c["enabled"], "frequency": s["frequency"], "years": s["years"], "min_price": s["min_price"],
            "max_price": s["max_price"], "max_km": s["max_km"], "pages": s["pages"], "sources": s["sources"],
            "read_details": s["read_details"], "lat": s["home"]["latitude"], "lon": s["home"]["longitude"],
            "radius": s["radius_km"], "notify": c["notify"]}


class TestParity(unittest.TestCase):
    def test_same_effective_settings(self):
        for raw in CASES:
            self.assertEqual(api_view(raw), bot_view(raw), raw)

    def test_defaults_and_home_match(self):
        self.assertEqual(api_cfg.DEFAULT_HOME["latitude"], bot_cfg.DEFAULT_HOME["latitude"])
        self.assertEqual(api_cfg.DEFAULT_HOME["longitude"], bot_cfg.DEFAULT_HOME["longitude"])
        self.assertEqual(api_cfg.MIN_FREQUENCY_MIN, bot_cfg.MIN_FREQUENCY_MIN)
        self.assertEqual(api_cfg.VALID_SOURCES, bot_cfg.VALID_SOURCES)
        self.assertEqual(api_cfg.DEFAULT_RADIUS_KM, bot_cfg.DEFAULT_RADIUS_KM)

    def test_stored_form_is_read_back_identically_by_the_bot(self):
        body = api_cfg.LeafConfigIn(enabled=True, scan=api_cfg.ScanIn(
            frequency=180, min_price=2000, max_price=6500, max_km=130000, pages=3, years=[2017, 2018], sources=["kijiji"],
            read_details=False, home=api_cfg.HomeIn(latitude=45.6, longitude=-73.4, name="Ville-Test"), radius_km=90),
            notify=api_cfg.NotifyIn(enabled=True, new=False, price_drop=True))
        stored = api_cfg.to_stored(body)
        self.assertEqual(api_view(stored), bot_view(stored))
        self.assertEqual(bot_cfg.normalize_config(stored)["scan"]["home"]["max_km"], 90)


if __name__ == "__main__":
    unittest.main()
