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
from backend.scraping.utils import calculate_distance


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
SAINT_BRUNO = {"name": "Saint-Bruno-de-Montarville", "id": "loc3", "latitude": 45.5333, "longitude": -73.3500}


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
    def test_radius_km_defaults_to_none_when_nothing_configured(self, mock_scraper_cls, _sleep):
        """`scanConfig.distance=0` (défaut) et pas de `kijijiRadiusKm` par ville : `None`
        transmis à `scan_city()`, qui applique elle-même son défaut à deux paliers plutôt
        que de recevoir un plancher arbitraire côté `bot.py` (voir JOURNAL.md 2026-07-27)."""
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.return_value = []

        self.bot._run_kijiji_scan(self.scan_config, [LONGUEUIL])

        _, kwargs = mock_scraper.scan_city.call_args
        self.assertIsNone(kwargs["radius_km"])

    @patch("backend.bot.KijijiScraper")
    def test_radius_km_uses_global_distance_when_configured(self, mock_scraper_cls, _sleep):
        """`scanConfig.distance` > 0 (réglage global explicite) transmis tel quel."""
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.return_value = []

        scan_config = {**self.scan_config, "distance": 12}
        self.bot._run_kijiji_scan(scan_config, [LONGUEUIL])

        _, kwargs = mock_scraper.scan_city.call_args
        self.assertEqual(kwargs["radius_km"], 12)

    @patch("backend.bot.KijijiScraper")
    def test_radius_km_per_city_overrides_global_distance(self, mock_scraper_cls, _sleep):
        """`city_data['kijijiRadiusKm']` prime sur `scanConfig.distance` — réglage le plus
        spécifique gagne."""
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.return_value = []

        city_with_override = {**LONGUEUIL, "kijijiRadiusKm": 3}
        scan_config = {**self.scan_config, "distance": 12}
        self.bot._run_kijiji_scan(scan_config, [city_with_override])

        _, kwargs = mock_scraper.scan_city.call_args
        self.assertEqual(kwargs["radius_km"], 3)

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
    def test_close_cities_are_clustered_into_a_single_search(self, mock_scraper_cls, _sleep):
        """Deux villes proches (<80km, sans réglage `kijijiRadiusKm`) sont regroupées
        derrière un seul point d'ancrage — une seule recherche Kijiji au lieu de deux
        (2026-08-25, voir backend/scraping/geo_clustering.py)."""
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.return_value = []

        self.bot._run_kijiji_scan(self.scan_config, [LONGUEUIL, SAINT_BRUNO])

        self.assertEqual(mock_scraper.scan_city.call_count, 1)

    @patch("backend.bot.KijijiScraper")
    def test_clustered_search_radius_covers_every_member(self, mock_scraper_cls, _sleep):
        """Le rayon envoyé à Kijiji pour un cluster doit être au moins celui requis pour
        atteindre son membre le plus éloigné — sinon la consolidation en un seul point
        d'ancrage perdrait des villes qu'une recherche dédiée aurait trouvées."""
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.return_value = []

        self.bot._run_kijiji_scan(self.scan_config, [LONGUEUIL, SAINT_BRUNO])

        _, kwargs = mock_scraper.scan_city.call_args
        required_radius = calculate_distance(
            LONGUEUIL["latitude"], LONGUEUIL["longitude"], SAINT_BRUNO["latitude"], SAINT_BRUNO["longitude"]
        )
        self.assertGreaterEqual(kwargs["radius_km"], required_radius)

    @patch("backend.bot.KijijiScraper")
    def test_clustered_search_radius_respects_larger_global_distance(self, mock_scraper_cls, _sleep):
        """`scanConfig.distance` reste respecté tel quel s'il est plus grand que ce que le
        cluster exige — la consolidation ne doit jamais RÉDUIRE la portée que
        l'utilisateur a explicitement configurée."""
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.return_value = []

        scan_config = {**self.scan_config, "distance": 60}
        self.bot._run_kijiji_scan(scan_config, [LONGUEUIL, SAINT_BRUNO])

        _, kwargs = mock_scraper.scan_city.call_args
        self.assertEqual(kwargs["radius_km"], 60)

    @patch("backend.bot.KijijiScraper")
    def test_city_with_radius_override_is_never_clustered(self, mock_scraper_cls, _sleep):
        """Une ville avec `kijijiRadiusKm` explicite (réglage Firestore par ville) signale
        une intention précise de l'utilisateur pour CETTE ville — jamais absorbée dans un
        cluster, toujours scannée seule avec exactement ce rayon."""
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.return_value = []

        city_with_override = {**SAINT_BRUNO, "kijijiRadiusKm": 3}
        self.bot._run_kijiji_scan(self.scan_config, [LONGUEUIL, city_with_override])

        self.assertEqual(mock_scraper.scan_city.call_count, 2)
        radius_by_city = {
            call.args[0]: call.kwargs["radius_km"] for call in mock_scraper.scan_city.call_args_list
        }
        self.assertEqual(radius_by_city["Saint-Bruno-de-Montarville"], 3)

    @patch("backend.bot.KijijiScraper")
    def test_deal_from_clustered_member_city_still_gets_its_own_location(self, mock_scraper_cls, _sleep):
        """Une annonce retournée pour le cluster (recherché sous l'ancre Longueuil) mais
        géolocalisée près de Saint-Bruno doit rester rattachée à Saint-Bruno — pas à
        l'ancre par défaut (`nearest_configured_city` s'appuie sur TOUTES les villes
        configurées, pas seulement les ancres)."""
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scan_city.return_value = [
            _deal("555", lat=SAINT_BRUNO["latitude"], lng=SAINT_BRUNO["longitude"])
        ]

        self.bot._run_kijiji_scan(self.scan_config, [LONGUEUIL, SAINT_BRUNO])

        (processed_deal,), _ = self.bot.handle_deal_found.call_args
        self.assertEqual(processed_deal["location"], "Saint-Bruno-de-Montarville")

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

    def test_facebook_enabled_by_default_when_absent(self):
        """`facebook_enabled` absent (comptes existants avant ce réglage, 2026-07-27) :
        Facebook tourne quand même — pas de désactivation silencieuse."""
        self.bot._run_sources_in_parallel({}, self.cities)

        self.bot._run_facebook_scan.assert_called_once()

    def test_only_kijiji_called_when_facebook_disabled(self):
        """Facebook désactivable indépendamment — utile pour isoler un scan Kijiji seul
        en debug (demande utilisateur du 2026-07-27)."""
        self.bot._run_sources_in_parallel({"facebook_enabled": False, "kijiji_enabled": True}, self.cities)

        self.bot._run_facebook_scan.assert_not_called()
        self.bot._run_kijiji_scan.assert_called_once()

    def test_no_scan_when_both_sources_disabled(self):
        self.bot._run_sources_in_parallel({"facebook_enabled": False, "kijiji_enabled": False}, self.cities)

        self.bot._run_facebook_scan.assert_not_called()
        self.bot._run_kijiji_scan.assert_not_called()
        self.bot.logger.warning.assert_called_once()

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


class TestScanSpecificUrl(unittest.TestCase):
    """scan_specific_url() ("Scanner une URL spécifique") doit dispatcher vers le bon
    scraper selon le domaine de l'URL — avant ce correctif (2026-07-27), `FacebookScraper`
    était utilisé sans condition, y compris pour une URL kijiji.ca : échec silencieux
    (mauvais site/sélecteurs), notification générique "Impossible de récupérer les
    informations..." mal étiquetée "URL Facebook" — signalé par l'utilisateur."""

    def setUp(self):
        self.bot = _make_bot()
        self.bot.offline_mode = True
        self.bot._user_email = ''
        self.bot.handle_deal_found = MagicMock(return_value="processed")

    @patch("backend.bot.NotificationService")
    @patch("backend.bot.KijijiScraper")
    @patch("backend.bot.FacebookScraper")
    def test_facebook_url_uses_facebook_scraper(self, mock_fb_cls, mock_kj_cls, _mock_notif):
        mock_fb = mock_fb_cls.return_value
        self.bot.scan_specific_url("https://www.facebook.com/marketplace/item/123456")

        mock_fb_cls.assert_called_once()
        mock_kj_cls.assert_not_called()
        mock_fb.scan_specific_url.assert_called_once()

    @patch("backend.bot.NotificationService")
    @patch("backend.bot.KijijiScraper")
    @patch("backend.bot.FacebookScraper")
    def test_kijiji_url_uses_kijiji_scraper(self, mock_fb_cls, mock_kj_cls, _mock_notif):
        mock_kj = mock_kj_cls.return_value
        self.bot.scan_specific_url("https://www.kijiji.ca/v-guitar/longueuil-rive-sud/guitare-electrique/1740804650")

        mock_kj_cls.assert_called_once()
        mock_fb_cls.assert_not_called()
        mock_kj.scan_specific_url.assert_called_once()

    @patch("backend.bot.NotificationService")
    @patch("backend.bot.KijijiScraper")
    @patch("backend.bot.FacebookScraper")
    def test_kijiji_deal_id_is_prefixed_and_source_passed(self, _mock_fb_cls, mock_kj_cls, _mock_notif):
        mock_kj = mock_kj_cls.return_value

        def fake_scan(url, on_deal_found):
            on_deal_found({"id": "1740804650", "title": "Guitare électrique"})
        mock_kj.scan_specific_url.side_effect = fake_scan

        self.bot.scan_specific_url("https://www.kijiji.ca/v-guitar/longueuil-rive-sud/guitare-electrique/1740804650")

        (listing_data,), kwargs = self.bot.handle_deal_found.call_args
        self.assertEqual(listing_data["id"], "kijiji_1740804650")
        self.assertEqual(kwargs["source"], "Kijiji")
        self.assertTrue(kwargs["is_manual_scan"])

    @patch("backend.bot.NotificationService")
    @patch("backend.bot.KijijiScraper")
    @patch("backend.bot.FacebookScraper")
    def test_notification_labeled_with_correct_source(self, _mock_fb_cls, mock_kj_cls, mock_notif):
        self.bot.scan_specific_url("https://www.kijiji.ca/v-guitar/longueuil-rive-sud/guitare-electrique/1740804650")

        _, kwargs = mock_notif.notify_scan_url_finished.call_args
        self.assertEqual(kwargs["source"], "Kijiji")

    @patch("backend.bot.NotificationService")
    @patch("backend.bot.KijijiScraper")
    def test_kijiji_manual_scan_corrects_location_via_gps(self, mock_kj_cls, _mock_notif):
        """Régression : le scan manuel Kijiji ne corrigeait pas `location` (imprécis par
        nature, ex: "Longueuil / South Shore") via GPS, contrairement au scan automatique
        (`_run_kijiji_scan`) — signalé par l'utilisateur (empêchait la dédup
        cross-plateforme de repli par nom de ville de fonctionner)."""
        mock_kj = mock_kj_cls.return_value

        def fake_scan(url, on_deal_found):
            on_deal_found({"id": "1740804650", "title": "Guitare", "latitude": 45.58, "longitude": -73.32, "location": "Longueuil / South Shore"})
        mock_kj.scan_specific_url.side_effect = fake_scan

        self.bot.offline_mode = False
        self.bot.set_status = MagicMock()
        self.bot.repo = MagicMock()
        self.bot.repo.get_cities.return_value = [
            {"name": "Sainte-Julie", "latitude": 45.5906, "longitude": -73.3306},
            {"name": "Longueuil", "latitude": 45.5369, "longitude": -73.5105},
        ]

        self.bot.scan_specific_url("https://www.kijiji.ca/v-guitar/longueuil-rive-sud/guitare-electrique/1740804650")

        (listing_data,), _ = self.bot.handle_deal_found.call_args
        self.assertEqual(listing_data["location"], "sainte julie")  # nearest_configured_city() retourne un nom normalisé


class TestFindCrossPlatformDuplicate(unittest.TestCase):
    """`_find_cross_platform_duplicate()` repère une même annonce postée sur Facebook et
    Kijiji avant de payer le pipeline IA une seconde fois. Localisation comparée par
    distance GPS (précise même quand `location.name` Kijiji ne l'est pas), avec repli sur
    le nom de ville normalisé si les coordonnées manquent d'un côté — voir sa docstring
    pour le contexte complet (2026-07-27, signalé par l'utilisateur : faux négatif d'abord,
    puis risque de faux positif sur titre générique identifié avant d'implémenter)."""

    def setUp(self):
        self.bot = _make_bot()
        self.bot.offline_mode = False
        self.bot.repo = MagicMock()

    def _set_index(self, entries):
        self.bot.repo.get_deals_index_snapshot.return_value = entries

    def test_returns_none_when_offline(self):
        self.bot.offline_mode = True
        self._set_index({"123": {"p": 200, "title": "Guitare"}})
        result = self.bot._find_cross_platform_duplicate({"price": 200, "title": "Guitare"}, "Kijiji")
        self.assertIsNone(result)

    def test_matches_via_gps_distance_when_both_have_coordinates(self):
        """Même prix/titre, coordonnées à quelques centaines de mètres (jitter de
        géocodage) : doublon détecté même si les noms de ville diffèrent (l'annonce
        Kijiji "Longueuil / South Shore" vs Facebook "Sainte-Julie", cas réel signalé)."""
        self._set_index({
            "999": {"p": 220, "title": "Guitare électrique", "l": "sainte-julie", "la": 45.5906, "lo": -73.3306},
        })
        result = self.bot._find_cross_platform_duplicate(
            {"price": 220, "title": "Guitare électrique", "location": "Longueuil / South Shore",
             "latitude": 45.58, "longitude": -73.32},
            "Kijiji",
        )
        self.assertEqual(result, "999")

    def test_no_match_via_gps_when_too_far_even_with_generic_title(self):
        """Régression clé (signalé par l'utilisateur) : même prix et titre générique
        identique ("guitare électrique") ne doit PAS suffire si les coordonnées GPS des
        deux côtés montrent des villes clairement différentes — sans ce garde-fou, deux
        guitares différentes à Montréal et Québec seraient à tort fusionnées."""
        self._set_index({
            "999": {"p": 200, "title": "Guitare électrique", "la": 46.8139, "lo": -71.2080},  # Québec
        })
        result = self.bot._find_cross_platform_duplicate(
            {"price": 200, "title": "Guitare électrique", "latitude": 45.5017, "longitude": -73.5673},  # Montréal
            "Kijiji",
        )
        self.assertIsNone(result)

    def test_falls_back_to_location_name_when_coordinates_missing(self):
        """Coordonnées absentes d'un côté : repli sur la comparaison par nom de ville
        (comportement historique, préservé pour ne pas perdre tout filtre géographique)."""
        self._set_index({
            "999": {"p": 200, "title": "Guitare électrique", "l": "sainte-julie"},  # pas de la/lo
        })
        result = self.bot._find_cross_platform_duplicate(
            {"price": 200, "title": "Guitare électrique", "location": "Sainte-Julie"},  # pas de latitude/longitude
            "Kijiji",
        )
        self.assertEqual(result, "999")

    def test_no_match_via_location_fallback_when_cities_differ(self):
        self._set_index({
            "999": {"p": 200, "title": "Guitare électrique", "l": "quebec"},
        })
        result = self.bot._find_cross_platform_duplicate(
            {"price": 200, "title": "Guitare électrique", "location": "Montreal"},
            "Kijiji",
        )
        self.assertIsNone(result)

    def test_same_source_entries_are_skipped(self):
        """Un doublon même-source (même préfixe `kijiji_` ou son absence) est déjà géré
        par ID exact (`should_skip_deal`) — ne doit jamais matcher ici."""
        self._set_index({
            "kijiji_999": {"p": 200, "title": "Guitare électrique", "la": 45.58, "lo": -73.32},
        })
        result = self.bot._find_cross_platform_duplicate(
            {"price": 200, "title": "Guitare électrique", "latitude": 45.58, "longitude": -73.32},
            "Kijiji",  # même source que "kijiji_999"
        )
        self.assertIsNone(result)

    def test_returns_none_when_price_or_title_missing(self):
        self._set_index({"999": {"p": 200, "title": "Guitare électrique"}})
        self.assertIsNone(self.bot._find_cross_platform_duplicate({"price": 0, "title": "Guitare électrique"}, "Kijiji"))
        self.assertIsNone(self.bot._find_cross_platform_duplicate({"price": 200, "title": ""}, "Kijiji"))

    def test_ignores_non_numeric_coordinates(self):
        """Régression : une coordonnée non numérique (chaîne, `None`) ne doit pas être
        traitée comme "0,0" par calculate_distance() — même piège que
        nearest_configured_city(), voir `_is_number()`."""
        self._set_index({
            "999": {"p": 200, "title": "Guitare électrique", "l": "sainte-julie", "la": "invalide", "lo": -73.3306},
        })
        result = self.bot._find_cross_platform_duplicate(
            {"price": 200, "title": "Guitare électrique", "location": "Sainte-Julie",
             "latitude": 45.5906, "longitude": -73.3306},
            "Kijiji",
        )
        # Repli sur le nom de ville (coordonnées invalides côté candidat) plutôt que de
        # planter ou de considérer "invalide" comme une coordonnée valide.
        self.assertEqual(result, "999")


if __name__ == "__main__":
    unittest.main()
