"""Configuration, orchestrateur et notifications Leaf. Données INVENTÉES (dépôt public).
La config est pure ; l'orchestrateur tourne contre un Postgres JETABLE (`KB_TEST_DATABASE_URL`), sinon sauté."""
import os
import unittest
from unittest import mock

from backend.leaf import config as lc
from backend.leaf import notify

URL = os.getenv("KB_TEST_DATABASE_URL")
SCHEMA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api", "schema.sql")


class TestConfig(unittest.TestCase):
    def test_absent_config_is_disabled_with_defaults(self):
        c = lc.normalize_config(None)
        self.assertFalse(c["enabled"])
        self.assertEqual((c["scan"]["frequency"], c["scan"]["min_price"], c["scan"]["max_price"]), (120, 1500, 7500))
        self.assertEqual(c["scan"]["home"], {"latitude": 45.5333, "longitude": -73.35, "max_km": 150})   # Saint-Bruno

    def test_enabled_only_when_exactly_true(self):
        self.assertTrue(lc.normalize_config({"enabled": True})["enabled"])
        for v in ("true", 1, None):
            self.assertFalse(lc.normalize_config({"enabled": v})["enabled"])

    def test_values_are_clamped_and_garbage_ignored(self):
        c = lc.normalize_config({"scanConfig": {"frequency": 5, "pages": 99, "max_price": 100, "min_price": 2000,
                                                "years": [1999, 2017, "x"], "sources": ["nope"], "max_km": "abc"}})["scan"]
        self.assertEqual((c["frequency"], c["pages"], c["years"]), (60, 3, [2017]))
        self.assertEqual((c["min_price"], c["max_price"]), (2000, 2000))     # le plafond ne passe jamais sous le plancher
        self.assertEqual((c["sources"], c["max_km"]), (["kijiji", "autohebdo"], 150000))

    def test_incomplete_home_falls_back_to_saint_bruno(self):
        home = lc.normalize_config({"scanConfig": {"home": {"latitude": 45.5}}})["scan"]["home"]
        self.assertEqual((home["latitude"], home["longitude"]), (45.5333, -73.35))
    def test_custom_home_and_radius(self):
        home = lc.normalize_config({"scanConfig": {"home": {"latitude": 45.5, "longitude": -73.5}, "radius_km": 80}})["scan"]["home"]
        self.assertEqual(home["max_km"], 80)

    def test_server_switch(self):
        with mock.patch.dict(os.environ, {"LEAF_ENABLED": "true"}):
            self.assertTrue(lc.server_enabled())
        with mock.patch.dict(os.environ, {"LEAF_ENABLED": ""}):
            self.assertFalse(lc.server_enabled())


class TestNotify(unittest.TestCase):
    def test_no_topic_means_nothing_sent_and_no_fallback_to_guitar_topic(self):
        with mock.patch.dict(os.environ, {"LEAF_NTFY_TOPIC": "", "NTFY_TOPIC": "guitares"}), \
                mock.patch("requests.post") as post:
            self.assertFalse(notify.send("t", "m"))
            post.assert_not_called()

    def test_sends_to_the_leaf_topic_with_encoded_title(self):
        with mock.patch.dict(os.environ, {"LEAF_NTFY_TOPIC": "sujet-test"}), \
                mock.patch("requests.post", return_value=mock.Mock(status_code=200)) as post:
            self.assertTrue(notify.send("Baisse → 5 500 $", "m", click_url="https://exemple.invalide"))
        self.assertEqual(post.call_args.args[0], "https://ntfy.sh/sujet-test")
        self.assertTrue(post.call_args.kwargs["headers"]["Title"].isascii())

    def test_network_failure_never_raises(self):
        with mock.patch.dict(os.environ, {"LEAF_NTFY_TOPIC": "x"}), mock.patch("requests.post", side_effect=OSError("down")):
            self.assertFalse(notify.send("t", "m"))


def raw(id_, price=6000, **extra):
    base = {"id": id_, "source": "test", "source_id": id_, "url": f"https://exemple.invalide/{id_}", "title": "2017 Nissan Leaf SV",
            "description": "annonce de test", "price": price, "year": 2017, "trim": "SV", "km": 90000, "model": "Leaf",
            "city": "Ville-Test", "latitude": 45.5, "longitude": -73.5, "image_urls": []}
    base.update(extra)
    return base


@unittest.skipUnless(URL, "définir KB_TEST_DATABASE_URL (base Postgres JETABLE)")
class TestHunter(unittest.TestCase):
    UID = "u-leaf-hunter"

    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
        from psycopg_pool import ConnectionPool
        from backend.leaf.hunter import LeafHunter
        from backend.leaf.repository import LeafRepository
        with open(SCHEMA, encoding="utf-8") as fh:
            schema = fh.read()
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute(schema)
            conn.execute("TRUNCATE vehicle_deals, user_vehicle_matches, user_vehicle_state, vehicle_price_history, scrape_runs CASCADE")
            conn.execute("DELETE FROM users WHERE uid = %s", (self.UID,))
            conn.execute("INSERT INTO users (uid, config) VALUES (%s, %s)", (self.UID, Jsonb({"leafConfig": {"enabled": True}})))
        self.pool = ConnectionPool(URL, min_size=1, max_size=3, kwargs={"row_factory": dict_row}, open=True)
        self.addCleanup(self.pool.close)
        self.repo = LeafRepository(self.pool)
        self.sent = []
        self.raws, self.runs = [raw("leaf_test_1")], [{"source": "kijiji", "outcome": "ok", "cards_seen": 1, "duration_ms": 5}]
        self.hunter = LeafHunter(self.repo, self.UID, collector=lambda scan: (self.raws, self.runs),
                                 detail_fetcher_factory=lambda: None,
                                 notifier=lambda title, msg, **kw: self.sent.append((title, msg)) or True)
        env = mock.patch.dict(os.environ, {"LEAF_ENABLED": "true"})
        env.start()
        self.addCleanup(env.stop)

    def _set_config(self, cfg):
        from psycopg.types.json import Jsonb
        with self.pool.connection() as conn:
            conn.execute("UPDATE users SET config = %s WHERE uid = %s", (Jsonb({"leafConfig": cfg}), self.UID))

    def test_scan_stores_links_notifies_and_records_run(self):
        stats = self.hunter.run_scan()
        self.assertEqual((stats["kept"], stats["new"]), (1, 1))
        self.assertEqual(self.repo.active_ids(), ["leaf_test_1"])
        with self.pool.connection() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM user_vehicle_matches WHERE user_id = %s", (self.UID,)).fetchone()["n"], 1)
            self.assertEqual(conn.execute("SELECT source, outcome FROM scrape_runs").fetchone(), {"source": "leaf_kijiji", "outcome": "ok"})
        self.assertEqual([t for t, _ in self.sent], ["Leaf : nouvelle annonce"])

    def test_second_scan_is_silent_and_price_drop_notifies(self):
        self.hunter.run_scan()
        self.sent.clear()
        self.assertEqual(self.hunter.run_scan()["new"], 0)
        self.assertEqual(self.sent, [])
        self.raws = [raw("leaf_test_1", price=5500)]
        self.assertEqual(self.hunter.run_scan()["price_drops"], 1)
        self.assertIn("baisse de prix", self.sent[0][0])

    def test_disabled_user_or_server_does_nothing(self):
        self._set_config({"enabled": False})
        self.assertIsNone(self.hunter.run_scan())
        self.assertEqual(self.repo.active_ids(), [])
        self.assertIsNotNone(self.hunter.run_scan(force=True))          # commande manuelle : passe l'interrupteur utilisateur
        with mock.patch.dict(os.environ, {"LEAF_ENABLED": "false"}):
            self.assertIsNone(self.hunter.run_scan(force=True))          # jamais l'interrupteur serveur

    def test_first_scan_with_many_listings_sends_one_summary(self):
        self.raws = [raw(f"leaf_test_{i}", price=5000 + i) for i in range(8)]
        self.hunter.run_scan()
        self.assertEqual(len(self.sent), 1)
        self.assertIn("8 annonces", self.sent[0][0])

    def test_notifications_can_be_turned_off(self):
        self._set_config({"enabled": True, "notify": {"enabled": False}})
        self.hunter.run_scan()
        self.assertEqual(self.sent, [])

    def test_health_alert_once_at_third_consecutive_failure(self):
        self.runs = [{"source": "kijiji", "outcome": "blocked", "detail": "HTTP 429"}]
        self.raws = []
        for _ in range(4):
            self.hunter.run_scan()
        self.assertEqual([t for t, _ in self.sent], ["Leaf : source kijiji en panne"])

    def test_collector_crash_is_swallowed(self):
        def boom(scan):
            raise RuntimeError("réseau")
        self.hunter._collector = boom
        self.assertIsNone(self.hunter.run_scan())

    def test_overlapping_scan_is_skipped(self):
        self.hunter._lock.acquire()
        self.addCleanup(self.hunter._lock.release)
        self.assertIsNone(self.hunter.run_scan())

    def test_commands_fail_clearly_when_server_disabled_and_cleanup_works(self):
        handlers = self.hunter.command_handlers()
        self.assertEqual(set(handlers), {"LEAF_REFRESH", "LEAF_CLEANUP"})
        self.hunter.run_scan()
        with self.pool.connection() as conn:
            conn.execute("UPDATE vehicle_deals SET last_seen_at = now() - interval '10 days'")
        handlers["LEAF_CLEANUP"](None)
        self.assertEqual(self.repo.active_ids(), [])
        with mock.patch.dict(os.environ, {"LEAF_ENABLED": "false"}):
            with self.assertRaises(RuntimeError):
                handlers["LEAF_REFRESH"](None)


if __name__ == "__main__":
    unittest.main()
