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
        self.assertEqual((c["sources"], c["max_km"]), (["kijiji", "autohebdo"], 150000))   # Facebook jamais activé par défaut

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
        from backend import t1_circuit_breaker            # état partagé du processus : chaque test repart avec un Dell « sain »
        t1_circuit_breaker.record_success("local")
        self.addCleanup(t1_circuit_breaker.record_success, "local")
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

    def test_facebook_city_is_resolved_only_when_the_source_is_enabled(self):
        with self.pool.connection() as conn:
            conn.execute("INSERT INTO cities (id, name, latitude, longitude, fb_location_id) VALUES "
                         "('c-leaf-near','Ville Proche',45.5,-73.35,'fb123'),('c-leaf-far','Ville Loin',48.0,-70.0,'fb999') ON CONFLICT (id) DO NOTHING")
        def drop_cities():
            with self.pool.connection() as conn:
                conn.execute("DELETE FROM cities WHERE id LIKE 'c-leaf-%'")
        self.addCleanup(drop_cities)
        seen = []
        self.hunter._collector = lambda scan: seen.append(scan.get("facebook_city")) or (self.raws, self.runs)
        self.hunter.run_scan()
        self.assertEqual(seen, [None])                                   # source absente : aucune ville résolue
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji", "facebook"]}})
        self.hunter.run_scan()
        self.assertEqual((seen[1]["id"], seen[1]["name"]), ("fb123", "Ville Proche"))
        self._set_config({"enabled": True, "scanConfig": {"sources": ["facebook"], "radius_km": 1,
                                                          "home": {"latitude": 10.0, "longitude": 10.0}}})
        self.hunter.run_scan()
        self.assertIsNone(seen[2])                                       # aucune ville dans le rayon : pas de recherche

    def test_facebook_city_lookup_failure_does_not_stop_the_other_sources(self):
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji", "facebook"]}})
        self.repo.nearest_facebook_city = lambda *a: (_ for _ in ()).throw(RuntimeError("colonne fb_location_id absente"))
        seen = []
        self.hunter._collector = lambda scan: seen.append(scan.get("facebook_city")) or (self.raws, self.runs)
        stats = self.hunter.run_scan()
        self.assertEqual((stats["kept"], seen), (1, [None]))               # Kijiji passe, Facebook est simplement ignoré

    def test_skipped_is_neutral_for_health_alerts_and_cleanup_ignores_facebook(self):
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji", "facebook"]}})
        self.runs = [{"source": "kijiji", "outcome": "ok", "cards_seen": 1},
                     {"source": "facebook", "outcome": "skipped", "detail": "aucune ville Facebook configurée"}]
        for _ in range(5):
            self.hunter.run_scan()
        self.assertEqual([t for t, _ in self.sent if "panne" in t], [])     # jamais d'alerte « en panne » pour un simple réglage
        with self.pool.connection() as conn:
            conn.execute("UPDATE vehicle_deals SET last_seen_at = now() - interval '20 days'")
        self.assertEqual(self.hunter.cleanup(), 1)                          # Facebook « skipped » ne bloque pas le balayage

    def test_blocked_facebook_alerts_but_does_not_block_cleanup(self):
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji", "facebook"]}})
        self.runs = [{"source": "kijiji", "outcome": "ok", "cards_seen": 1}, {"source": "facebook", "outcome": "blocked"}]
        for _ in range(3):
            self.hunter.run_scan()
        self.assertEqual([t for t, _ in self.sent if "panne" in t], ["Leaf : source facebook en panne"])
        with self.pool.connection() as conn:
            conn.execute("UPDATE vehicle_deals SET last_seen_at = now() - interval '20 days'")
        self.assertEqual(self.hunter.cleanup(), 1)

    def test_stale_cleanup_uses_a_much_longer_window_for_facebook(self):
        self.repo.upsert_listing({**raw("leaf_facebook_1", source="facebook"), "flags": []})
        self.repo.upsert_listing({**raw("leaf_test_2"), "flags": []})
        with self.pool.connection() as conn:
            conn.execute("UPDATE vehicle_deals SET last_seen_at = now() - interval '40 days'")
        self.assertEqual(self.repo.mark_stale_sold(14), 1)                               # 40 jours : Kijiji vendue, Facebook encore là
        self.assertEqual(self.repo.active_ids("facebook"), ["leaf_facebook_1"])
        with self.pool.connection() as conn:
            conn.execute("UPDATE vehicle_deals SET last_seen_at = now() - interval '70 days' WHERE source = 'facebook'")
        self.assertEqual(self.repo.mark_stale_sold(14), 1)                               # 70 jours : une annonce Facebook ne reste pas « active » pour toujours
        self.assertEqual(self.repo.active_ids("facebook"), [])

    def test_a_facebook_card_seen_again_is_kept_fresh_and_stale_ones_leave_the_market_statistics(self):
        self.repo.upsert_listing({**raw("leaf_facebook_9", source="facebook"), "flags": []})
        with self.pool.connection() as conn:
            conn.execute("UPDATE vehicle_deals SET last_seen_at = now() - interval '30 days'")
        self.assertEqual(self.repo.comparables(), [])                                    # vue il y a 30 jours : n'alimente plus le prix de marché
        self.assertTrue(self.repo.known_unchanged(self.UID, "leaf_facebook_9", 6000))
        self.assertEqual(len(self.repo.comparables()), 1)                                # carte revue : fraîche de nouveau
        self.assertEqual(self.repo.mark_stale_sold(14), 0)

    def test_known_unchanged_links_without_lifting_a_withdrawal(self):
        self.repo.upsert_listing({**raw("leaf_facebook_7", source="facebook"), "flags": []})
        self.assertFalse(self.repo.known_unchanged(self.UID, "leaf_facebook_7", 5999))      # prix changé : fiche à rouvrir
        self.assertFalse(self.repo.known_unchanged(self.UID, "leaf_facebook_inconnue", 6000))
        self.assertTrue(self.repo.known_unchanged(self.UID, "leaf_facebook_7", 6000))
        self.repo.mark_withdrawn(self.UID, ["leaf_facebook_7"])
        self.assertTrue(self.repo.known_unchanged(self.UID, "leaf_facebook_7", 6000))
        with self.pool.connection() as conn:
            self.assertTrue(conn.execute("SELECT withdrawn FROM user_vehicle_matches WHERE user_id=%s AND deal_id='leaf_facebook_7'",
                                         (self.UID,)).fetchone()["withdrawn"])                # retrait conservé

    # --- IA niveau 2 -------------------------------------------------------------------------
    AI_TEXT = "Pompe à chaleur. Capacité résiduelle de la batterie : 91 % (mesurée)."      # SOH écrit comme les règles ne le lisent pas
    AI_ANSWER = {"summary": "Annonce claire.", "attention": [], "facts": {
        "soh_pct": {"value": 91.0, "evidence": "Capacité résiduelle de la batterie : 91 %", "confidence": "high"},
        "heat_pump": {"value": True, "evidence": "Pompe à chaleur", "confidence": "high"},
        "chademo": {"value": True, "evidence": "port CHAdeMO neuf", "confidence": "high"}}}     # citation absente : doit être écartée

    def _with_ai(self, enabled=True, max_calls=30, answer=None):
        from backend.leaf import ai as leaf_ai
        from backend.leaf.test_leaf_ai import FakeAnalyzer
        self.analyzer = FakeAnalyzer(local=answer if answer is not None else self.AI_ANSWER)
        self.hunter._ai = leaf_ai.LeafAI(self.analyzer)
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji"]},
                          "analysisConfig": {"enabled": enabled, "max_calls_per_day": max_calls}})
        self.raws = [raw("leaf_test_1", description=self.AI_TEXT)]

    def _ai_of(self, deal_id="leaf_test_1"):
        return self.repo.get_vehicle(deal_id)

    def test_ai_analysis_is_stored_applied_with_proofs_only_and_gives_a_verdict(self):
        self._with_ai()
        self.hunter.run_scan()
        row = self._ai_of()
        ai = row["analysis"]["ai"]
        self.assertEqual(set(ai["facts"]), {"soh_pct", "heat_pump"})                    # CHAdeMO sans citation retrouvée : écarté
        self.assertEqual(ai["flags"], ["ai_unsupported_claim"])
        self.assertEqual((float(row["soh_announced"]), row["soh_evidence"]), (91.0, "Capacité résiduelle de la batterie : 91 %"))
        self.assertNotIn("soh_unknown", row["flags"])
        self.assertEqual(row["verdict"], "CANDIDAT_FORT")
        self.assertEqual(self.analyzer.calls, [("local", "leaf_t2")])

    def test_unchanged_text_and_price_costs_nothing_but_a_new_price_is_reanalyzed(self):
        self._with_ai()
        self.hunter.run_scan()
        self.hunter.run_scan()
        self.assertEqual(len(self.analyzer.calls), 1)                                    # empreinte identique : cache
        self.raws = [raw("leaf_test_1", description=self.AI_TEXT, price=5500)]
        self.hunter.run_scan()
        self.assertEqual(len(self.analyzer.calls), 2)

    def test_ai_off_applies_the_cache_for_free_and_never_calls_the_model(self):
        self._with_ai()
        self.hunter.run_scan()
        first = self.analyzer
        self._with_ai(enabled=False)
        self.hunter.run_scan()
        self.assertEqual((len(first.calls), self.analyzer.calls), (1, []))               # IA éteinte : aucun appel de plus
        self.assertEqual(self._ai_of()["verdict"], "CANDIDAT_FORT")                      # l'analyse en cache reste appliquée
        self._with_ai(enabled=False)
        self.raws = [raw("leaf_test_1", description="Texte tout autre.")]
        self.hunter.run_scan()
        row = self._ai_of()
        self.assertTrue(row["analysis"]["ai_stale"])                                     # ancienne analyse : affichée comme périmée
        self.assertNotIn("stale", row["analysis"]["ai"])                                 # ...sans modifier la copie stockée
        self.assertIsNone(row["soh_announced"])                                          # et NON appliquée au texte modifié

    def test_daily_cap_stops_the_calls_and_notifies_once(self):
        self._with_ai(max_calls=2)
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM llm_usage WHERE action = 'leaf_t2'")
            conn.execute("INSERT INTO llm_usage (source, provider, model, action) VALUES ('backend','local','m','leaf_t2'),('backend','gemini','m','leaf_t2')")
        self.addCleanup(lambda: self._purge_usage())
        self.raws = [raw(f"leaf_test_{i}", price=5000 + i, description=self.AI_TEXT) for i in range(2)]
        self.hunter.run_scan()
        self.hunter.run_scan()
        self.assertEqual(self.analyzer.calls, [])                                        # plafond déjà atteint par les appels des 24 h
        self.assertEqual([t for t, _ in self.sent if "plafond" in t].__len__(), 1)       # une seule alerte par jour
        self.assertEqual(self._ai_of()["verdict"], "A_VERIFIER")                         # verdict calculé sans IA

    def _purge_usage(self, action="leaf_t2"):
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM llm_usage WHERE action = %s", (action,))

    def test_all_models_failing_keeps_the_scan_and_the_verdict(self):
        self._with_ai(answer=(None, "hors ligne"))
        self.analyzer.gemini = (None, "quota")
        stats = self.hunter.run_scan()
        self.assertEqual(stats["kept"], 1)
        row = self._ai_of()
        self.assertNotIn("ai", row["analysis"])
        self.assertEqual(row["verdict"], "A_VERIFIER")

    def test_expert_analysis_and_ai_survive_the_next_pass(self):
        self._with_ai()
        self.hunter.run_scan()
        with self.pool.connection() as conn:
            conn.execute("UPDATE vehicle_deals SET analysis = analysis || '{\"expert\": {\"verdict\": \"ok\"}}'::jsonb")
        self._with_ai(enabled=False)
        self.hunter.run_scan()
        analysis = self._ai_of()["analysis"]
        self.assertEqual(analysis["expert"], {"verdict": "ok"})
        self.assertIn("ai", analysis)

    def test_stale_banner_is_cleared_when_the_original_text_comes_back(self):
        self._with_ai()
        self.hunter.run_scan()
        first = self.analyzer
        self._with_ai(enabled=False)
        self.raws = [raw("leaf_test_1", description=self.AI_TEXT, price=5500)]           # prix changé, IA éteinte : analyse périmée
        self.hunter.run_scan()
        self.assertTrue(self._ai_of()["analysis"]["ai_stale"])
        self.raws = [raw("leaf_test_1", description=self.AI_TEXT)]                       # le vendeur remet le prix d'origine
        self.hunter.run_scan()
        analysis = self._ai_of()["analysis"]
        self.assertNotIn("ai_stale", analysis)                                           # empreinte retrouvée : plus de bannière
        self.assertEqual((len(first.calls), analysis["ai"]["version"]), (1, 1))
        self.assertEqual(self._ai_of()["verdict"], "CANDIDAT_FORT")

    def test_unreadable_detail_reuses_the_stored_analysis_and_never_spends_a_call(self):
        self._with_ai()
        self.hunter.run_scan()
        first = self.analyzer
        stored = self._ai_of()["analysis"]["ai"]
        self._with_ai()                                                                    # nouvel analyseur : doit rester à 0 appel
        degraded = {**raw("leaf_test_1", description="Texte de la carte seulement."), "detail_unavailable": True}
        self.raws = [degraded]
        self.hunter._detail_factory = lambda: (lambda r: None)                             # fiche illisible
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji"], "read_details": True},
                          "analysisConfig": {"enabled": True, "max_calls_per_day": 30}})
        self.hunter.run_scan()
        self.assertEqual((len(first.calls), self.analyzer.calls), (1, []))
        self.assertEqual(self._ai_of()["analysis"]["ai"], stored)                          # l'analyse du texte complet est intacte

    def test_facebook_photos_are_copied_once_and_originals_kept_on_failure(self):
        uploads = []
        self.hunter._photo_uploader = lambda urls, deal_id: uploads.append((list(urls), deal_id)) or (["https://stockage.invalide/a.jpg"], ["gs://x"])
        fb = raw("leaf_facebook_5", source="facebook", image_urls=["https://scontent.fbcdn.invalide/p1.jpg"], model="leaf")
        self.raws = [fb]
        self.hunter.run_scan()
        self.assertEqual(self._ai_of("leaf_facebook_5")["image_urls"], ["https://stockage.invalide/a.jpg"])
        self.hunter.run_scan()
        self.assertEqual(len(uploads), 1)                                                  # revue : photos déjà stables, pas de seconde copie
        self.raws = [raw("leaf_test_1", image_urls=["https://exemple.invalide/k.jpg"])]
        self.hunter.run_scan()
        self.assertEqual(len(uploads), 1)                                                  # une annonce Kijiji n'est jamais copiée
        self.assertEqual(self._ai_of()["image_urls"], ["https://exemple.invalide/k.jpg"])
        self.hunter._photo_uploader = lambda urls, deal_id: (_ for _ in ()).throw(RuntimeError("stockage indisponible"))
        self.raws = [raw("leaf_facebook_6", source="facebook", image_urls=["https://scontent.fbcdn.invalide/p2.jpg"], model="leaf")]
        self.hunter.run_scan()
        self.assertEqual(self._ai_of("leaf_facebook_6")["image_urls"], ["https://scontent.fbcdn.invalide/p2.jpg"])

    def test_expert_cap_counts_answers_only_and_two_clicks_cannot_exceed_it(self):
        import threading, time
        self._expert_hunter(max_expert=1)
        pool = self.pool

        class SlowClaude:
            def __init__(self, inner):
                self.inner = inner

            def _call_claude_json(self, model, parts, **kw):
                time.sleep(0.3)
                with pool.connection() as conn:                                            # le vrai client écrit sa ligne à la fin de l'appel
                    conn.execute("INSERT INTO llm_usage (source, provider, model, action, ok) VALUES ('backend','anthropic','m','leaf_t3', true)")
                return self.inner._call_claude_json(model, parts, **kw)

            def __getattr__(self, name):
                return getattr(self.inner, name)
        self.hunter._ai.analyzer = SlowClaude(self.claude)
        self.addCleanup(lambda: self._purge_usage("leaf_t3"))
        with pool.connection() as conn:
            conn.execute("DELETE FROM llm_usage WHERE action = 'leaf_t3'")
            conn.execute("INSERT INTO llm_usage (source, provider, model, action, ok) VALUES ('backend','anthropic','m','leaf_t3', false)")   # échec : ne compte pas
        results = []

        def click():
            try:
                self.hunter.analyze_deal("leaf_test_1")
                results.append("ok")
            except RuntimeError as e:
                results.append(str(e)[:8])
        threads = [threading.Thread(target=click) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sorted(results), ["Plafond ", "ok"])                              # un seul appel payant, malgré deux clics simultanés

    # --- Ré-analyse d'une annonce déjà stockée ------------------------------------------------------
    def _stored(self, **extra):
        """Annonce stockée par un ancien passage : sans SOH ni barres (les règles d'alors ne lisaient pas ces formulations)."""
        self.repo.upsert_listing({**raw("leaf_test_1", description="Voiture propre.", **extra), "flags": ["soh_unknown"]})
        self.repo.record_match(self.UID, "leaf_test_1")

    def _reread(self, description):
        self.hunter._detail_factory = lambda: (lambda r: {"description": description})       # fiche relue

    def test_reanalyze_applies_the_current_rules_to_a_stored_listing(self):
        self._stored()
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji"]}})
        self._reread("Voiture propre. Santé de la batterie : 11 barres sur 12, 91 % selon LeafSpy. Pompe à chaleur.")
        self.hunter.command_handlers()["LEAF_REANALYZE"]({"dealId": "leaf_test_1"})
        row = self._ai_of()
        self.assertEqual((float(row["soh_announced"]), row["capacity_bars"], row["verdict"]), (91.0, 11, "CANDIDAT_FORT"))
        self.assertNotIn("soh_unknown", row["flags"])

    def test_reanalyze_withdraws_a_listing_that_no_longer_passes_and_says_why(self):
        self._stored()
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji"]}})
        self._reread("Santé : 6 barres sur 12 (~50 % sur LeafSpy).")
        with self.assertRaisesRegex(RuntimeError, "soh_below_80"):
            self.hunter.command_handlers()["LEAF_REANALYZE"]({"dealId": "leaf_test_1"})
        self.assertTrue(self._withdrawn())                                                # retirée de la liste de l'utilisateur
        self.assertEqual(self.repo.get_vehicle("leaf_test_1")["status"], "active")        # fait global inchangé

    def test_reanalyze_restores_a_listing_that_passes_again(self):
        self._stored()
        self.repo.mark_withdrawn(self.UID, ["leaf_test_1"])
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji"]}})
        self._reread("Voiture propre, aucun accident.")
        self.hunter.command_handlers()["LEAF_REANALYZE"]({"dealId": "leaf_test_1"})
        self.assertFalse(self._withdrawn())

    def test_reanalyze_forces_a_new_ai_call_even_when_nothing_changed(self):
        self._with_ai()
        self.hunter.run_scan()
        self.assertEqual(len(self.analyzer.calls), 1)
        self._reread(self.AI_TEXT)                                                         # même texte : le cache suffirait pour un passage
        self.hunter.command_handlers()["LEAF_REANALYZE"]({"dealId": "leaf_test_1"})
        self.assertEqual(len(self.analyzer.calls), 2)                                      # mais la ré-analyse demandée refait l'appel
        self.hunter.run_scan()
        self.assertEqual(len(self.analyzer.calls), 2)                                      # un passage ordinaire reste gratuit

    def test_reanalyze_errors_are_explicit_and_nothing_is_overwritten(self):
        self._stored()
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji"]}})
        before = self._ai_of()["description"]
        self.hunter._detail_factory = lambda: (lambda r: None)                            # fiche illisible
        with self.assertRaisesRegex(RuntimeError, "illisible"):
            self.hunter.command_handlers()["LEAF_REANALYZE"]({"dealId": "leaf_test_1"})
        self.assertEqual(self._ai_of()["description"], before)
        with self.assertRaisesRegex(RuntimeError, "introuvable"):
            self.hunter.command_handlers()["LEAF_REANALYZE"]({"dealId": "leaf_test_inconnue"})
        with self.assertRaisesRegex(RuntimeError, "non précisée"):
            self.hunter.command_handlers()["LEAF_REANALYZE"]({})

    def test_facebook_reanalysis_uses_the_stored_text_without_any_fetch(self):
        self.repo.upsert_listing({**raw("leaf_test_1", source="facebook", description="Nissan Leaf SV 2017. Santé 6 barres sur 12."),
                                  "flags": [], "year": None})
        self.repo.record_match(self.UID, "leaf_test_1")
        self._set_config({"enabled": True, "scanConfig": {"sources": ["facebook"]}})
        self.hunter._detail_factory = lambda: (_ for _ in ()).throw(AssertionError("aucune relecture pour Facebook"))
        self.hunter.command_handlers()["LEAF_REANALYZE"]({"dealId": "leaf_test_1"})
        row = self._ai_of()
        self.assertEqual((row["capacity_bars"], row["verdict"]), (6, "BATTERIE_DOUTEUSE"))

    def test_refresh_with_force_ai_reanalyzes_every_kept_listing(self):
        self._with_ai()
        self.hunter.run_scan()
        self.hunter.command_handlers()["LEAF_REFRESH"]({"forceAi": True})
        self.assertEqual(len(self.analyzer.calls), 2)
        self.hunter.command_handlers()["LEAF_REFRESH"](None)
        self.assertEqual(len(self.analyzer.calls), 2)

    def test_strong_candidate_gets_a_priority_notification(self):
        self._with_ai()
        self.hunter.run_scan()
        self.assertEqual([t for t, _ in self.sent], ["Leaf : candidat fort"])

    # --- Expert (niveau 3) : commande LEAF_ANALYZE ------------------------------------------------
    def _expert_hunter(self, enabled=True, max_expert=5, result=None, error=None):
        from backend.leaf import ai as leaf_ai
        from backend.leaf.test_leaf_expert import FakeClaude, raw as expert_raw
        self.claude = FakeClaude(result if result is not None else expert_raw(), error)
        self.hunter._ai = leaf_ai.LeafAI(self.claude)
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji"]},
                          "analysisConfig": {"enabled": enabled, "max_expert_per_day": max_expert}})
        self.raws = [raw("leaf_test_1", description="Facture disponible pour la batterie. Pompe à chaleur.")]
        self.hunter.run_scan()

    def test_expert_stores_its_opinion_and_it_survives_the_next_pass(self):
        self._expert_hunter()
        opinion = self.hunter.command_handlers()["LEAF_ANALYZE"]({"dealId": "leaf_test_1"})
        stored = self._ai_of()["analysis"]["expert"]
        self.assertEqual(stored["opinion"], "Annonce sérieuse, batterie récente.")
        self.assertIn("leafspy", " ".join(stored["seller_questions"]).lower())           # question LeafSpy ajoutée par le code
        self.assertEqual(self.claude.calls[0][1], "leaf_t3")
        self.hunter.run_scan()
        self.assertEqual(self._ai_of()["analysis"]["expert"]["opinion"], stored["opinion"])

    def test_expert_refusals_are_explicit(self):
        handler = lambda: self.hunter.command_handlers()["LEAF_ANALYZE"]({"dealId": "leaf_test_1"})
        self._expert_hunter(enabled=False)
        with self.assertRaisesRegex(RuntimeError, "éteinte"):
            handler()
        self.assertEqual(self.claude.calls, [])                                          # aucun appel payant
        self._expert_hunter(max_expert=1)
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM llm_usage WHERE action = 'leaf_t3'")
            conn.execute("INSERT INTO llm_usage (source, provider, model, action) VALUES ('backend','anthropic','m','leaf_t3')")
        self.addCleanup(lambda: self._purge_usage("leaf_t3"))
        with self.assertRaisesRegex(RuntimeError, "Plafond"):
            handler()
        with self.assertRaisesRegex(RuntimeError, "introuvable"):
            self.hunter.command_handlers()["LEAF_ANALYZE"]({"dealId": "leaf_test_inconnue"})
        with self.assertRaisesRegex(RuntimeError, "non précisée"):
            self.hunter.command_handlers()["LEAF_ANALYZE"]({})

    def test_expert_failure_fails_the_command_and_stores_nothing(self):
        self._expert_hunter(result=None, error="ANTHROPIC_API_KEY n'est pas configurée.")
        self.claude.result = None
        with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY"):
            self.hunter.command_handlers()["LEAF_ANALYZE"]({"dealId": "leaf_test_1"})
        self.assertNotIn("expert", self._ai_of()["analysis"])

    def test_expert_only_for_listings_the_user_can_see(self):
        self._expert_hunter()
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM user_vehicle_matches WHERE deal_id = 'leaf_test_1'")
        with self.assertRaisesRegex(RuntimeError, "introuvable"):
            self.hunter.command_handlers()["LEAF_ANALYZE"]({"dealId": "leaf_test_1"})

    def test_every_leaf_handler_is_an_accepted_api_command_type(self):
        from backend.api import input_guard
        self.assertTrue(set(self.hunter.command_handlers()) <= input_guard.COMMAND_TYPES)

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
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji"]}})
        handlers = self.hunter.command_handlers()
        self.assertEqual(set(handlers), {"LEAF_REFRESH", "LEAF_CLEANUP", "LEAF_ANALYZE", "LEAF_REANALYZE"})
        self.hunter.run_scan()
        with self.pool.connection() as conn:
            conn.execute("UPDATE vehicle_deals SET last_seen_at = now() - interval '20 days'")
        handlers["LEAF_CLEANUP"](None)
        self.assertEqual(self.repo.active_ids(), [])
        with mock.patch.dict(os.environ, {"LEAF_ENABLED": "false"}):
            with self.assertRaises(RuntimeError):
                handlers["LEAF_REFRESH"](None)

    def test_cleanup_waits_when_a_source_is_not_healthy(self):
        self._set_config({"enabled": True, "scanConfig": {"sources": ["kijiji"]}})
        self.hunter.run_scan()
        with self.pool.connection() as conn:
            conn.execute("UPDATE vehicle_deals SET last_seen_at = now() - interval '20 days'")
        self.runs, self.raws = [{"source": "kijiji", "outcome": "blocked", "detail": "429"}], []
        self.hunter.run_scan()
        self.assertEqual(self.hunter.cleanup(), 0)
        self.assertEqual(self.repo.active_ids(), ["leaf_test_1"])

    def _withdrawn(self, uid=None):
        with self.pool.connection() as conn:
            return conn.execute("SELECT withdrawn FROM user_vehicle_matches WHERE user_id = %s AND deal_id = 'leaf_test_1'",
                                (uid or self.UID,)).fetchone()["withdrawn"]

    def test_known_listing_that_no_longer_passes_is_withdrawn_for_this_user_only(self):
        from backend.leaf.hunter import LeafHunter
        with self.pool.connection() as conn:
            conn.execute("INSERT INTO users (uid) VALUES ('u-leaf-other') ON CONFLICT DO NOTHING")
        self.hunter.run_scan()
        self.repo.record_match("u-leaf-other", "leaf_test_1")
        self.raws = [raw("leaf_test_1", price=9000)]                   # hors budget POUR CET utilisateur : « ignorée »
        self.hunter.run_scan()
        self.assertTrue(self._withdrawn())
        self.assertFalse(self._withdrawn("u-leaf-other"))              # l'autre utilisateur la voit toujours
        self.assertEqual(self.repo.get_vehicle("leaf_test_1")["status"], "active")   # le statut global ne bouge pas
        self.raws = [raw("leaf_test_1", price=6000)]
        self.hunter.run_scan()
        self.assertFalse(self._withdrawn())                            # retenue de nouveau : retrait levé

    def test_unreadable_detail_does_not_erase_what_a_full_read_stored(self):
        full = raw("leaf_test_1", soh_announced=92.0, soh_evidence="SOH 92 %", vin="VIN123", description="texte complet",
                   image_urls=["https://exemple.invalide/p.jpg"])
        self.repo.upsert_listing({**full, "flags": [], "analysis_marker": 1, "mentions": {"heat_pump": True}})
        degraded = {**raw("leaf_test_1", price=5800), "detail_unavailable": True, "flags": ["soh_unknown", "detail_unavailable"],
                    "image_urls": [], "description": ""}
        self.assertEqual(self.repo.upsert_listing(degraded)["action"], "price_drop")
        row = self.repo.get_vehicle("leaf_test_1")
        self.assertEqual((float(row["price"]), float(row["soh_announced"]), row["soh_evidence"], row["vin"]),
                         (5800.0, 92.0, "SOH 92 %", "VIN123"))
        self.assertEqual((row["flags"], row["image_urls"], row["description"]), ([], ["https://exemple.invalide/p.jpg"], "texte complet"))
        self.assertEqual(row["analysis"]["mentions"], {"heat_pump": True})

    def test_refresh_command_fails_loudly_on_error_or_overlap(self):
        refresh = self.hunter.command_handlers()["LEAF_REFRESH"]
        self.hunter._lock.acquire()
        try:
            with self.assertRaises(RuntimeError):
                refresh(None)
        finally:
            self.hunter._lock.release()

        def boom(scan):
            raise RuntimeError("base injoignable")
        self.hunter._collector = boom
        with self.assertRaises(RuntimeError):
            refresh(None)

    def test_unchanged_pass_does_not_bump_timestamp_nor_notify(self):
        import psycopg
        self.hunter.run_scan()
        before = self.repo.get_vehicle("leaf_test_1")["timestamp"]
        with psycopg.connect(URL, autocommit=True) as listener:
            listener.execute("LISTEN vehicle_changes")
            self.hunter.run_scan()
            events = list(listener.notifies(timeout=0.5))
        self.assertEqual(self.repo.get_vehicle("leaf_test_1")["timestamp"], before)
        self.assertEqual(events, [])

    def test_background_loop_is_unique_follows_the_current_hunter_and_can_be_stopped(self):
        from backend.leaf import hunter as hmod
        self.addCleanup(hmod.stop_background, self.UID)
        with mock.patch.object(hmod, "LOOP_TICK_S", 0.05):
            self.assertTrue(self.hunter.ensure_background())
            first_thread = hmod._BACKGROUND[self.UID][0]
            newer = hmod.LeafHunter(self.repo, self.UID)             # le watchdog reconstruit le bot : nouveau hunter
            self.assertFalse(newer.ensure_background())              # pas de second fil...
            self.assertIs(hmod._CURRENT[self.UID], newer)            # ...mais la boucle suit le hunter COURANT (bon logger)
            self.assertIs(hmod._BACKGROUND[self.UID][0], first_thread)
            hmod.stop_background(self.UID)
            first_thread.join(3)
            self.assertFalse(first_thread.is_alive())
            self.assertNotIn(self.UID, hmod._BACKGROUND)
            self.assertTrue(self.hunter.ensure_background())          # après l'arrêt : un nouveau fil peut démarrer

    def test_missed_pass_is_retried_soon_not_after_a_full_period(self):
        from backend.leaf import hunter as hmod
        calls = []
        self.hunter.run_scan = lambda *a, **k: calls.append(1)       # None : passage manqué (verrou pris, erreur)
        self.addCleanup(hmod.stop_background, self.UID)
        with mock.patch.object(hmod, "LOOP_TICK_S", 0.05), mock.patch.object(hmod, "RETRY_AFTER_NONE_S", 0.3), \
                mock.patch.object(hmod.threading.Event, "wait", lambda self, t=None: __import__("time").sleep(min(t or 0, 0.05)) or self.is_set()):
            self.hunter.ensure_background()
            __import__("time").sleep(1.2)
            hmod.stop_background(self.UID)
        self.assertGreaterEqual(len(calls), 2)                       # retenté après RETRY_AFTER_NONE_S, pas une fois par période


if __name__ == "__main__":
    unittest.main()
