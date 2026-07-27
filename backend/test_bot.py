"""Tests pour l'orchestration de scan de GuitarHunterBot :
- _run_kijiji_scan() : source additionnelle Kijiji (préfixage d'ID, correction GPS de la
  localisation, tolérance aux pannes par ville).
- _run_sources_in_parallel() : dispatche Facebook et Kijiji chacun dans son propre thread
  au lieu de les enchaîner en séquence.
Le reste de GuitarHunterBot (Firestore, Playwright Facebook, IA, _run_facebook_scan) n'est
pas testé ici : aucun test unitaire n'existait encore pour bot.py avant ce module, le
périmètre reste volontairement limité à l'orchestration ajoutée pour Kijiji."""
import queue
import threading
import unittest
from unittest.mock import MagicMock, patch

from backend.bot import GuitarHunterBot


def _make_bot():
    """Instance minimale, sans passer par __init__ (qui exige Firestore/Firebase Auth) —
    seuls les attributs lus par _run_kijiji_scan/should_skip_deal/handle_deal_found sont
    posés à la main. handle_deal_found et should_skip_deal sont mockés : on teste
    l'orchestration de _run_kijiji_scan elle-même, pas le pipeline de traitement complet
    (déjà hors scope du module Kijiji autonome)."""
    bot = GuitarHunterBot.__new__(GuitarHunterBot)
    bot.logger = MagicMock()
    bot._user_id = "test_user_id"
    bot.stop_event = None
    bot.scan_stop_event = None
    bot._browser_semaphore = None
    bot.handle_deal_found = MagicMock()
    bot.should_skip_deal = MagicMock(return_value=False)
    return bot


LONGUEUIL = {"name": "Longueuil", "id": "loc1", "latitude": 45.5369, "longitude": -73.5105}
QUEBEC = {"name": "Quebec", "id": "loc2", "latitude": 46.8139, "longitude": -71.208}


def _deal(deal_id="123", lat=None, lng=None):
    return {
        "id": deal_id, "title": f"Guitare {deal_id}", "price": 200,
        "location": "Longueuil / South Shore", "source": "kijiji",
        "latitude": lat, "longitude": lng,
    }


@patch("backend.bot.time.sleep")  # évite les vraies pauses de 2s entre villes pendant les tests
class TestRunKijijiScan(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        self.scan_config = {"max_ads": 5, "search_query": "electric guitar", "distance": 0}

    @patch("backend.bot.KijijiScraper")
    def test_prefixes_id_and_corrects_location_via_gps(self, mock_scraper_cls, _sleep):
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.return_value = [_deal("123", lat=45.5369, lng=-73.5105)]

        self.bot._run_kijiji_scan(self.scan_config, [LONGUEUIL])

        self.bot.handle_deal_found.assert_called_once()
        (processed_deal,), _ = self.bot.handle_deal_found.call_args
        self.assertEqual(processed_deal["id"], "kijiji_123")
        self.assertEqual(processed_deal["location"], "longueuil")
        mock_scraper.close_session.assert_called_once()

    @patch("backend.bot.KijijiScraper")
    def test_scan_city_called_per_configured_city(self, mock_scraper_cls, _sleep):
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.return_value = []

        self.bot._run_kijiji_scan(self.scan_config, [LONGUEUIL, QUEBEC])

        self.assertEqual(mock_scraper.scan_city.call_count, 2)
        called_cities = [call.args[0] for call in mock_scraper.scan_city.call_args_list]
        self.assertEqual(called_cities, ["Longueuil", "Quebec"])
        _, kwargs = mock_scraper.scan_city.call_args_list[0]
        self.assertEqual(kwargs["category_id"], 613)

    @patch("backend.bot.KijijiScraper")
    def test_should_skip_callback_prefixes_id_before_delegating(self, mock_scraper_cls, _sleep):
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.return_value = []

        self.bot._run_kijiji_scan(self.scan_config, [LONGUEUIL])

        _, kwargs = mock_scraper.scan_city.call_args
        callback = kwargs["should_skip_callback"]
        callback("999", 100)
        self.bot.should_skip_deal.assert_called_once_with("kijiji_999", 100)

    @patch("backend.bot.KijijiScraper")
    def test_out_of_radius_deal_is_dropped_when_radius_configured(self, mock_scraper_cls, _sleep):
        mock_scraper = mock_scraper_cls.return_value
        # Coordonnées de Toronto alors que seul Longueuil est configuré, avec un rayon de 25km.
        mock_scraper.scan_city.return_value = [_deal("456", lat=43.6532, lng=-79.3832)]

        scan_config = {**self.scan_config, "distance": 25}
        self.bot._run_kijiji_scan(scan_config, [LONGUEUIL])

        self.bot.handle_deal_found.assert_not_called()

    @patch("backend.bot.KijijiScraper")
    def test_deal_without_gps_keeps_raw_location_when_no_radius_configured(self, mock_scraper_cls, _sleep):
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.return_value = [_deal("789", lat=None, lng=None)]

        self.bot._run_kijiji_scan(self.scan_config, [LONGUEUIL])

        self.bot.handle_deal_found.assert_called_once()
        (processed_deal,), _ = self.bot.handle_deal_found.call_args
        self.assertEqual(processed_deal["location"], "Longueuil / South Shore")

    @patch("backend.bot.KijijiScraper")
    def test_one_city_failure_does_not_abort_the_others(self, mock_scraper_cls, _sleep):
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.side_effect = [Exception("boom"), [_deal("321", lat=46.8139, lng=-71.208)]]

        self.bot._run_kijiji_scan(self.scan_config, [LONGUEUIL, QUEBEC])

        self.assertEqual(mock_scraper.scan_city.call_count, 2)
        self.bot.handle_deal_found.assert_called_once()

    @patch("backend.bot.KijijiScraper")
    def test_stop_requested_skips_scan_entirely(self, mock_scraper_cls, _sleep):
        mock_scraper = mock_scraper_cls.return_value
        self.bot.stop_event = MagicMock()
        self.bot.stop_event.is_set.return_value = True

        self.bot._run_kijiji_scan(self.scan_config, [LONGUEUIL])

        mock_scraper.scan_city.assert_not_called()
        self.bot.handle_deal_found.assert_not_called()


class TestRunSourcesInParallel(unittest.TestCase):
    """_run_sources_in_parallel() dispatche Facebook et Kijiji chacun dans son propre
    thread (au lieu de les enchaîner en séquence) — voir demande utilisateur du
    2026-07-27. Les scans réels (_run_facebook_scan/_run_kijiji_scan) sont mockés : ce
    qui est testé ici est l'orchestration (les deux tournent bien EN MÊME TEMPS, pas
    juste "les deux sont appelés"), pas leur logique interne (déjà couverte ailleurs
    pour Kijiji, jamais testée pour Facebook avant ce module)."""

    def setUp(self):
        self.bot = _make_bot()
        self.bot._run_facebook_scan = MagicMock()
        self.bot._run_kijiji_scan = MagicMock()
        self.cities = [LONGUEUIL]

    def test_both_sources_called_when_kijiji_enabled(self):
        self.bot._run_sources_in_parallel({"kijiji_enabled": True}, self.cities)

        self.bot._run_facebook_scan.assert_called_once_with({"kijiji_enabled": True}, self.cities)
        self.bot._run_kijiji_scan.assert_called_once_with({"kijiji_enabled": True}, self.cities)

    def test_only_facebook_called_when_kijiji_disabled(self):
        self.bot._run_sources_in_parallel({"kijiji_enabled": False}, self.cities)

        self.bot._run_facebook_scan.assert_called_once()
        self.bot._run_kijiji_scan.assert_not_called()

    def test_sources_actually_overlap_in_time_not_sequential(self):
        """Preuve de parallélisme réel (pas juste 'les deux mocks ont été appelés') :
        chaque cible signale son propre démarrage puis attend celui de l'autre — un
        timeout indique un enchaînement séquentiel plutôt qu'un vrai parallélisme
        (l'un ne peut démarrer qu'après le retour du premier)."""
        fb_started = threading.Event()
        kijiji_started = threading.Event()
        results = queue.Queue()

        def fb_target(scan_config, cities):
            fb_started.set()
            results.put(("fb", kijiji_started.wait(timeout=2)))

        def kijiji_target(scan_config, cities):
            kijiji_started.set()
            results.put(("kijiji", fb_started.wait(timeout=2)))

        self.bot._run_facebook_scan.side_effect = fb_target
        self.bot._run_kijiji_scan.side_effect = kijiji_target

        self.bot._run_sources_in_parallel({"kijiji_enabled": True}, self.cities)

        outcomes = dict(results.get_nowait() for _ in range(2))
        self.assertTrue(outcomes["fb"], "Le thread Facebook n'a jamais vu Kijiji démarrer — pas de vrai parallélisme.")
        self.assertTrue(outcomes["kijiji"], "Le thread Kijiji n'a jamais vu Facebook démarrer — pas de vrai parallélisme.")

    def test_exception_in_one_source_does_not_prevent_the_other(self):
        self.bot._run_facebook_scan.side_effect = Exception("boom Facebook")
        # _run_kijiji_scan (mock par défaut) réussit normalement.

        self.bot._run_sources_in_parallel({"kijiji_enabled": True}, self.cities)  # ne doit pas lever

        self.bot._run_kijiji_scan.assert_called_once()
        self.bot.logger.error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
