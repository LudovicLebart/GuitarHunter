"""Tests d'intégration de `PostgresRepository` contre un vrai Postgres local — même principe que
`backend/api/test_*.py` (pas de mock côté Postgres), se saute proprement si injoignable. Phase A.1
de la bascule (voir docs/management/plans/FIRESTORE_MIGRATION_PLAN.md §5.3) : ce repository n'est
PAS encore branché sur `backend/bot.py`, construit et testé en isolation.
"""
import unittest

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.api.db import DATABASE_URL as _ASYNC_DSN  # même DSN par défaut, juste pour le fallback lisible
from backend.pg_repository import PostgresRepository, _Row


def _sync_dsn() -> str:
    import os
    return os.getenv("DATABASE_URL", _ASYNC_DSN)


def _pg_reachable() -> bool:
    try:
        with psycopg.connect(_sync_dsn(), connect_timeout=2):
            pass
        return True
    except Exception:
        return False


class _Pool:
    """Pool minimal à une connexion — suffisant pour des tests séquentiels, sans dépendre de
    `psycopg_pool` (déjà exercé indirectement par `backend/pg_db.py`, pas la peine de le
    redémarrer par test)."""
    def __init__(self, dsn):
        self._conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)

    def connection(self):
        return _NoCloseConnectionCtx(self._conn)

    def close(self):
        self._conn.close()


class _NoCloseConnectionCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc):
        return False


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({_sync_dsn()}) depuis cet environnement.")
class TestPostgresRepository(unittest.TestCase):
    UID = "test-uid-pgrepo-1"
    OTHER_UID = "test-uid-pgrepo-2"
    DEAL_ID = "pgrepo-deal-1"
    CITY_ID = "pgrepo-city-1"

    def setUp(self):
        with open("backend/api/schema.sql", encoding="utf-8") as f:
            schema_sql = f.read()
        self.pool = _Pool(_sync_dsn())
        with self.pool.connection() as conn:
            conn.execute(schema_sql)
            conn.execute("INSERT INTO users (uid) VALUES (%s) ON CONFLICT (uid) DO NOTHING", (self.UID,))
            conn.execute("INSERT INTO users (uid) VALUES (%s) ON CONFLICT (uid) DO NOTHING", (self.OTHER_UID,))
        self.repo = PostgresRepository(self.pool, self.UID)
        self.other_repo = PostgresRepository(self.pool, self.OTHER_UID)

    def tearDown(self):
        with self.pool.connection() as conn:
            # Catalogue partagé (2026-09-19) : plus de user_id sur guitar_deals, nettoyage par
            # préfixe d'id (DEAL_ID = "pgrepo-deal-1", + variantes "-other"/"-2" utilisées par
            # certains tests) — CASCADE supprime aussi les lignes user_deal_matches/user_deal_state.
            conn.execute("DELETE FROM guitar_deals WHERE id LIKE 'pgrepo-deal%'")
            conn.execute("DELETE FROM user_city_prefs WHERE user_id = %s", (self.UID,))
            conn.execute("DELETE FROM cities WHERE id = %s", (self.CITY_ID,))
            conn.execute("DELETE FROM commands WHERE user_id = %s", (self.UID,))
            conn.execute("DELETE FROM logs WHERE user_id = %s", (self.UID,))
            conn.execute("DELETE FROM users WHERE uid IN (%s, %s)", (self.UID, self.OTHER_UID))
        self.pool.close()

    # ---------------------------------------------------------------- structure / config

    def test_ensure_initial_structure_creates_once_then_preserves(self):
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM users WHERE uid = %s", (self.UID,))

        self.repo.ensure_initial_structure({"scanConfig": {"frequency": 60}, "exclusionKeywords": ["case"]})
        config = self.repo.get_user_config()
        self.assertEqual(config["scanConfig"], {"frequency": 60})
        self.assertEqual(config["botStatus"], "idle")

        # Un second appel NE DOIT PAS écraser la config déjà en place (comme Firestore : "Config preserved").
        self.repo.ensure_initial_structure({"scanConfig": {"frequency": 999}})
        config_after = self.repo.get_user_config()
        self.assertEqual(config_after["scanConfig"], {"frequency": 60})

        with self.pool.connection() as conn:
            conn.execute("INSERT INTO users (uid) VALUES (%s) ON CONFLICT (uid) DO NOTHING", (self.UID,))

    def test_update_bot_status(self):
        self.repo.update_bot_status("scanning")
        self.assertEqual(self.repo.get_user_config()["botStatus"], "scanning")

    # ---------------------------------------------------------------- deals

    def test_create_new_deal_then_get_deal_by_id(self):
        self.repo.create_new_deal(
            self.DEAL_ID,
            {
                "title": "Parlor satinée", "price": 450, "description": "Belle guitare",
                "link": "https://x", "published_at_ts": 1757000000,
            },
            {"verdict": "GOOD_DEAL", "deal_score": 8, "brand": "Gibson"},
        )
        deal = self.repo.get_deal_by_id(self.DEAL_ID)
        self.assertEqual(deal["title"], "Parlor satinée")
        self.assertEqual(deal["status"], "analyzed")
        self.assertEqual(deal["description"], "Belle guitare")
        self.assertEqual(deal["published_at_ts"], 1757000000)
        self.assertIsNone(deal["imageUrl"])  # jamais écrit, toujours None

    def test_create_new_deal_rejected_verdict_sets_status(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "REJECTED"})
        self.assertEqual(self.repo.get_deal_by_id(self.DEAL_ID)["status"], "rejected")

    def test_create_new_deal_is_shared_and_visible_to_both_users(self):
        """2026-09-19 : `guitar_deals` est un catalogue PARTAGÉ — deux bots (deux users) qui
        tombent sur la même annonce réelle voient tous les deux la MÊME ligne (une seule analyse,
        pas de duplication), et chacun a sa propre entrée `user_deal_matches` (visibilité dans
        son propre fil), même si un seul des deux l'a réellement créée en premier."""
        self.repo.create_new_deal(self.DEAL_ID, {"title": "Titre original"}, {"verdict": "GOOD_DEAL"})
        # bot.py::handle_deal_found appelle record_deal_match dès que get_deal_by_id trouve une
        # ligne existante — même sans ré-analyse (voir JOURNAL.md 2026-09-19).
        self.other_repo.record_deal_match(self.DEAL_ID)

        with self.pool.connection() as conn:
            count = conn.execute("SELECT count(*) AS n FROM guitar_deals WHERE id = %s", (self.DEAL_ID,)).fetchone()
        self.assertEqual(count["n"], 1)  # une seule ligne, pas de doublon par utilisateur
        self.assertEqual(self.repo.get_deal_by_id(self.DEAL_ID)["title"], "Titre original")
        self.assertEqual(self.other_repo.get_deal_by_id(self.DEAL_ID)["title"], "Titre original")

        with self.pool.connection() as conn:
            matched_uids = {
                r["user_id"] for r in conn.execute(
                    "SELECT user_id FROM user_deal_matches WHERE deal_id = %s", (self.DEAL_ID,)
                ).fetchall()
            }
        self.assertEqual(matched_uids, {self.UID, self.OTHER_UID})

    def test_update_deal_analysis_touches_only_ai_columns(self):
        """Ne doit PAS altérer les colonnes issues de deal_data (title/price/...) — seulement
        aiAnalysis + status/timestamp, comme le `.update()` partiel Firestore d'origine."""
        self.repo.create_new_deal(self.DEAL_ID, {"title": "Original", "price": 100}, {"verdict": "GOOD_DEAL"})
        self.repo.update_deal_analysis(self.DEAL_ID, {"verdict": "BAD_DEAL", "brand": "Fender"})

        deal = self.repo.get_deal_by_id(self.DEAL_ID)
        self.assertEqual(deal["verdict"], "BAD_DEAL")
        self.assertEqual(deal["brand"], "Fender")
        self.assertEqual(deal["title"], "Original")  # inchangé
        self.assertEqual(float(deal["price"]), 100.0)  # inchangé
        self.assertEqual(deal["status"], "analyzed")

    def test_update_deal_data_and_analysis_only_touches_present_keys(self):
        self.repo.create_new_deal(
            self.DEAL_ID, {"title": "Original", "price": 100, "location": "Québec"}, {"verdict": "GOOD_DEAL"}
        )
        # Seul `price` est présent dans deal_data ici -> `location` ne doit PAS être touché.
        self.repo.update_deal_data_and_analysis(self.DEAL_ID, {"price": 80}, {"verdict": "GOOD_DEAL"})

        deal = self.repo.get_deal_by_id(self.DEAL_ID)
        self.assertEqual(float(deal["price"]), 80.0)
        self.assertEqual(deal["location"], "Québec")  # inchangé

    def test_update_deal_status_sold_sets_sold_at(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "GOOD_DEAL"})
        self.repo.update_deal_status(self.DEAL_ID, "sold")
        deal = self.repo.get_deal_by_id(self.DEAL_ID)
        self.assertEqual(deal["status"], "sold")
        self.assertIsNotNone(deal["sold_at"])

    def test_update_deal_status_with_error_merges_into_ai_analysis_raw_without_corrupting_it(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "GOOD_DEAL", "brand": "Gibson"})
        self.repo.update_deal_status(self.DEAL_ID, "analysis_failed", "boom")
        deal = self.repo.get_deal_by_id(self.DEAL_ID)
        self.assertEqual(deal["status"], "analysis_failed")
        self.assertEqual(deal["ai_analysis_raw"]["error"], "boom")
        self.assertEqual(deal["ai_analysis_raw"]["verdict"], "GOOD_DEAL")  # pas écrasé (pas d'ArrayUnion-sur-objet)

    def test_purge_rejected_images_clears_column_even_without_matching_blobs(self):
        """Une ligne candidate sans blob Storage restant (déjà supprimé, ou jamais uploadé) doit
        quand même voir `storage_image_urls` remis à NULL, sinon elle reste éligible au filtre
        `WHERE storage_image_urls IS NOT NULL` et est resélectionnée indéfiniment (boucle infinie
        — bug de revue de code, la remise à NULL n'avait lieu qu'à l'intérieur de `if blobs:`)."""
        class _EmptyBucket:
            def list_blobs(self, prefix):
                return []

        self.repo.create_new_deal(
            self.DEAL_ID, {"title": "x", "storageImageUrls": ["gs://old/1.jpg"]}, {"verdict": "BAD_DEAL"}
        )
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE guitar_deals SET \"timestamp\" = now() - interval '60 days' WHERE id = %s",
                (self.DEAL_ID,),
            )
        repo_with_bucket = PostgresRepository(self.pool, self.UID, bucket=_EmptyBucket())

        purged = repo_with_bucket.purge_rejected_images(retention_days=30)

        self.assertEqual(purged, 0)
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT storage_image_urls FROM guitar_deals WHERE id = %s", (self.DEAL_ID,)
            ).fetchone()
        self.assertIsNone(row["storage_image_urls"])

    def test_mark_deal_as_sold_with_reason_appends_to_sold_notes(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "GOOD_DEAL"})
        self.repo.mark_deal_as_sold(self.DEAL_ID, "Annonce indisponible")
        deal = self.repo.get_deal_by_id(self.DEAL_ID)
        self.assertEqual(deal["status"], "sold")
        self.assertEqual(len(deal["sold_notes"]), 1)
        self.assertEqual(deal["sold_notes"][0]["info"], "Annonce indisponible")

    def test_get_deals_index_snapshot_returns_abbreviated_keys(self):
        self.repo.create_new_deal(
            self.DEAL_ID, {"title": "Parlor", "price": 300, "latitude": 46.8, "longitude": -71.2, "location": "Québec"},
            {"verdict": "GOOD_DEAL"},
        )
        snapshot = self.repo.get_deals_index_snapshot()
        entry = snapshot[self.DEAL_ID]
        self.assertEqual(entry, {"title": "Parlor", "p": 300, "la": 46.8, "lo": -71.2, "l": "Québec"})

    def test_update_deal_analysis_does_not_grant_visibility_to_an_unrelated_user(self):
        """Correctif 2026-09-20 (revue de code) : `update_deal_analysis` ne doit PAS enregistrer
        de match — sinon un utilisateur dont le thread traite la file GLOBALE `retry_analysis`
        (`process_retry_queue`) se verrait attribuer la visibilité d'annonces que son propre scan
        n'a jamais trouvées."""
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "GOOD_DEAL"})
        # other_repo n'a JAMAIS vu cette annonce (pas de record_deal_match/create_new_deal pour lui).
        self.other_repo.update_deal_analysis(self.DEAL_ID, {"verdict": "BAD_DEAL"})

        with self.pool.connection() as conn:
            match = conn.execute(
                "SELECT 1 FROM user_deal_matches WHERE user_id = %s AND deal_id = %s",
                (self.OTHER_UID, self.DEAL_ID),
            ).fetchone()
        self.assertIsNone(match)

    def test_get_active_listings_returns_row_like_objects(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x", "link": "https://x"}, {"verdict": "GOOD_DEAL"})
        listings = self.repo.get_active_listings()
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].id, self.DEAL_ID)
        self.assertEqual(listings[0].to_dict()["link"], "https://x")

    def test_delete_listing(self):
        """2026-09-19 : `delete_listing` retire la visibilité/les préférences de CET utilisateur
        uniquement (`user_deal_matches`/`user_deal_state`) — l'annonce partagée elle-même reste
        en base, potentiellement visible pour d'autres utilisateurs."""
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "GOOD_DEAL"})
        self.other_repo.record_deal_match(self.DEAL_ID)
        self.repo.toggle_favorite(self.DEAL_ID, True)

        self.repo.delete_listing(self.DEAL_ID)

        # L'annonce globale survit (l'autre utilisateur la voit toujours).
        self.assertIsNotNone(self.repo.get_deal_by_id(self.DEAL_ID))
        with self.pool.connection() as conn:
            match_still_there = conn.execute(
                "SELECT 1 FROM user_deal_matches WHERE user_id = %s AND deal_id = %s",
                (self.OTHER_UID, self.DEAL_ID),
            ).fetchone()
        self.assertIsNotNone(match_still_there)
        # Mais plus dans le fil ni les préférences de celui qui a "supprimé".
        with self.pool.connection() as conn:
            self.assertIsNone(conn.execute(
                "SELECT 1 FROM user_deal_matches WHERE user_id = %s AND deal_id = %s", (self.UID, self.DEAL_ID),
            ).fetchone())
            self.assertIsNone(conn.execute(
                "SELECT 1 FROM user_deal_state WHERE user_id = %s AND deal_id = %s", (self.UID, self.DEAL_ID),
            ).fetchone())

    def test_retry_queue_and_mark_all_for_reanalysis(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "GOOD_DEAL"})
        count = self.repo.mark_all_for_reanalysis()
        self.assertEqual(count, 1)

        docs = self.repo.get_retry_queue_listings()
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].id, self.DEAL_ID)
        self.assertEqual(docs[0].to_dict()["title"], "x")

    def test_get_not_promoted_listings(self):
        """Rattrapage Chantier G (2026-09-19) : voir bot.py::reevaluate_not_promoted."""
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {
            "verdict": "NOT_PROMOTED", "gatekeeperClassification": "guitare.electrique",
        })
        other_id = self.DEAL_ID + "-other"
        self.repo.create_new_deal(other_id, {"title": "y"}, {"verdict": "GOOD_DEAL"})

        docs = self.repo.get_not_promoted_listings()
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].id, self.DEAL_ID)
        self.assertEqual(docs[0].to_dict()["gatekeeper_classification"], "guitare.electrique")

    def test_manual_analysis_overrides_reapplied_on_next_analysis(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "GOOD_DEAL"})
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE guitar_deals SET manual_analysis_overrides = %s WHERE id = %s",
                (Jsonb({"brand": "Corrigé Manuellement"}), self.DEAL_ID),
            )
        self.repo.update_deal_analysis(self.DEAL_ID, {"verdict": "GOOD_DEAL", "brand": "IA"})
        self.assertEqual(self.repo.get_deal_by_id(self.DEAL_ID)["brand"], "Corrigé Manuellement")

    def test_toggle_favorite_and_rejected_are_per_user(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "GOOD_DEAL"})
        self.other_repo.record_deal_match(self.DEAL_ID)

        self.repo.toggle_favorite(self.DEAL_ID, True)
        self.other_repo.toggle_rejected(self.DEAL_ID, True)

        with self.pool.connection() as conn:
            mine = conn.execute(
                "SELECT is_favorite, is_rejected FROM user_deal_state WHERE user_id = %s AND deal_id = %s",
                (self.UID, self.DEAL_ID),
            ).fetchone()
            other = conn.execute(
                "SELECT is_favorite, is_rejected FROM user_deal_state WHERE user_id = %s AND deal_id = %s",
                (self.OTHER_UID, self.DEAL_ID),
            ).fetchone()
        self.assertEqual(mine, {"is_favorite": True, "is_rejected": False})
        self.assertEqual(other, {"is_favorite": False, "is_rejected": True})

    def test_toggle_purchased_is_global(self):
        """Achat GLOBAL (décidé le 2026-09-19) : une fois achetée par un utilisateur, l'annonce
        est indisponible pour tous — `purchased_by_user_id` fixe qui a le droit au chat/plan de
        restauration côté API."""
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "GOOD_DEAL"})

        self.repo.toggle_purchased(self.DEAL_ID, True, purchase_price=350)

        deal_from_other = self.other_repo.get_deal_by_id(self.DEAL_ID)
        self.assertTrue(deal_from_other["is_purchased"])
        self.assertEqual(deal_from_other["purchased_by_user_id"], self.UID)
        self.assertEqual(float(deal_from_other["purchase_price"]), 350.0)

        # L'autre utilisateur ne peut pas "désacheter" l'annonce de quelqu'un d'autre.
        self.other_repo.toggle_purchased(self.DEAL_ID, False)
        still_purchased = self.repo.get_deal_by_id(self.DEAL_ID)
        self.assertTrue(still_purchased["is_purchased"])
        self.assertEqual(still_purchased["purchased_by_user_id"], self.UID)

        self.repo.toggle_purchased(self.DEAL_ID, False)
        released = self.repo.get_deal_by_id(self.DEAL_ID)
        self.assertFalse(released["is_purchased"])
        self.assertIsNone(released["purchased_by_user_id"])

    # ---------------------------------------------------------------- villes

    def test_add_city_to_catalog_partial_upsert_then_set_pref_then_get_cities(self):
        self.repo.add_city_to_catalog(self.CITY_ID, {"name": "Québec", "latitude": 46.8, "longitude": -71.2})
        self.repo.set_city_user_pref(self.CITY_ID, True)

        cities = self.repo.get_cities()
        self.assertEqual(len(cities), 1)
        self.assertEqual(cities[0]["name"], "Québec")
        self.assertTrue(cities[0]["isScannable"])

        catalog = self.repo.get_all_catalog_cities()
        self.assertIn(self.CITY_ID, catalog)

    def test_add_city_to_catalog_merge_does_not_clear_untouched_fields(self):
        self.repo.add_city_to_catalog(self.CITY_ID, {"name": "Québec", "latitude": 46.8, "longitude": -71.2})
        self.repo.add_city_to_catalog(self.CITY_ID, {"needsReview": True})  # merge=True : ne doit pas effacer latitude/longitude
        catalog = self.repo.get_all_catalog_cities()
        self.assertEqual(catalog[self.CITY_ID]["latitude"], 46.8)
        self.assertTrue(catalog[self.CITY_ID]["needsReview"])

    def test_city_pref_inactive_by_default_not_returned_by_get_cities(self):
        self.repo.add_city_to_catalog(self.CITY_ID, {"name": "Québec"})
        # Jamais de set_city_user_pref -> absence de ligne == non scannable (voir schema.sql).
        self.assertEqual(self.repo.get_cities(), [])

    # ---------------------------------------------------------------- commandes

    def test_pending_commands_and_mark_completed_failed(self):
        with self.pool.connection() as conn:
            row1 = conn.execute(
                "INSERT INTO commands (user_id, type, payload) VALUES (%s, 'REFRESH', NULL) RETURNING id",
                (self.UID,),
            ).fetchone()
            row2 = conn.execute(
                "INSERT INTO commands (user_id, type, payload) VALUES (%s, 'SCAN_URL', %s) RETURNING id",
                (self.UID, Jsonb({"url": "https://x"})),
            ).fetchone()

        pending = self.repo.get_pending_commands()
        self.assertEqual({p.id for p in pending}, {str(row1["id"]), str(row2["id"])})
        by_id = {p.id: p.to_dict() for p in pending}
        self.assertEqual(by_id[str(row2["id"])]["payload"], {"url": "https://x"})

        self.repo.mark_command_completed(row1["id"])
        self.repo.mark_command_failed(row2["id"], "boom")

        with self.pool.connection() as conn:
            statuses = {
                r["id"]: r["status"] for r in conn.execute(
                    "SELECT id, status FROM commands WHERE user_id = %s", (self.UID,)
                ).fetchall()
            }
        self.assertEqual(statuses[row1["id"]], "completed")
        self.assertEqual(statuses[row2["id"]], "failed")

        with self.pool.connection() as conn:
            conn.execute("DELETE FROM commands WHERE user_id = %s", (self.UID,))

    # ---------------------------------------------------------------- logs

    def test_delete_all_logs(self):
        with self.pool.connection() as conn:
            conn.execute("INSERT INTO logs (user_id, message) VALUES (%s, 'a'), (%s, 'b')", (self.UID, self.UID))
        count = self.repo.delete_all_logs()
        self.assertEqual(count, 2)
        with self.pool.connection() as conn:
            remaining = conn.execute("SELECT count(*) AS n FROM logs WHERE user_id = %s", (self.UID,)).fetchone()
        self.assertEqual(remaining["n"], 0)


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({_sync_dsn()}) depuis cet environnement.")
class TestScrapeRuns(unittest.TestCase):
    """Suivi de santé des scrapers (table `scrape_runs`, voir backend/scrape_health.py)."""
    UID = "test-uid-scrape-runs-1"
    OTHER_UID = "test-uid-scrape-runs-2"

    def setUp(self):
        with open("backend/api/schema.sql", encoding="utf-8") as f:
            schema_sql = f.read()
        self.pool = _Pool(_sync_dsn())
        with self.pool.connection() as conn:
            conn.execute(schema_sql)
            for uid in (self.UID, self.OTHER_UID):
                conn.execute("INSERT INTO users (uid) VALUES (%s) ON CONFLICT (uid) DO NOTHING", (uid,))
        self.repo = PostgresRepository(self.pool, self.UID)
        self.other_repo = PostgresRepository(self.pool, self.OTHER_UID)

    def tearDown(self):
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM users WHERE uid IN (%s, %s)", (self.UID, self.OTHER_UID))  # CASCADE -> scrape_runs
        self.pool.close()

    def _run(self, outcome, city_id="110", source="facebook", repo=None):
        return (repo or self.repo).record_scrape_run(source, city_id, "Bromont", "guitar", outcome, None,
                                                     cards_seen=10, out_of_list=2, kept=1, duration_ms=500)

    def test_recent_outcomes_are_newest_first_and_scoped_by_user_source_and_city(self):
        for o in ("ok", "geo_mismatch", "blocked"):
            self._run(o)
        self._run("error", city_id="999")
        self._run("error", source="kijiji")
        self._run("error", repo=self.other_repo)
        self.assertEqual(self.repo.recent_scrape_outcomes("facebook", "110", 10), ["blocked", "geo_mismatch", "ok"])
        self.assertEqual(self.repo.recent_scrape_outcomes("facebook", "110", 2), ["blocked", "geo_mismatch"])

    def test_last_ok_run(self):
        self.assertIsNone(self.repo.last_ok_scrape_run("facebook", "110"))
        self._run("blocked")
        self.assertIsNone(self.repo.last_ok_scrape_run("facebook", "110"))
        self._run("ok")
        self.assertRegex(self.repo.last_ok_scrape_run("facebook", "110"), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$")

    def test_alert_cooldown_follows_the_marked_run(self):
        run_id = self._run("geo_mismatch")
        self.assertFalse(self.repo.was_scrape_alerted_recently("facebook", "110", 6))
        self.repo.mark_scrape_run_alerted(run_id)
        self.assertTrue(self.repo.was_scrape_alerted_recently("facebook", "110", 6))
        self.assertFalse(self.repo.was_scrape_alerted_recently("facebook", "999", 6))
        self.assertFalse(self.other_repo.was_scrape_alerted_recently("facebook", "110", 6))
        with self.pool.connection() as conn:
            conn.execute("UPDATE scrape_runs SET alerted_at = now() - interval '7 hours' WHERE id = %s", (run_id,))
        self.assertFalse(self.repo.was_scrape_alerted_recently("facebook", "110", 6))

    def test_run_without_city_id_is_supported(self):
        self.repo.record_scrape_run("kijiji", None, "X", "q", "error", "boom")
        self.assertEqual(self.repo.recent_scrape_outcomes("kijiji", None, 5), ["error"])

    def test_purge_removes_only_old_rows(self):
        old_id = self._run("error")
        self._run("ok")
        with self.pool.connection() as conn:
            conn.execute("UPDATE scrape_runs SET created_at = now() - interval '100 days' WHERE id = %s", (old_id,))
        self.repo.purge_scrape_runs(90)
        self.assertEqual(self.repo.recent_scrape_outcomes("facebook", "110", 10), ["ok"])


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({_sync_dsn()}) depuis cet environnement.")
class TestCityFbLocationId(unittest.TestCase):
    """Colonne `cities.fb_location_id` (2026-10-23) : ID Facebook réel quand `cities.id` ne l'est pas."""
    UID = "test-uid-fbloc"
    ID_FIXED, ID_PLAIN = "pgrepo-fbloc-1", "pgrepo-fbloc-2"

    def setUp(self):
        with open("backend/api/schema.sql", encoding="utf-8") as f:
            schema_sql = f.read()
        self.pool = _Pool(_sync_dsn())
        with self.pool.connection() as conn:
            conn.execute(schema_sql)
            conn.execute("INSERT INTO users (uid) VALUES (%s) ON CONFLICT (uid) DO NOTHING", (self.UID,))
            conn.execute("DELETE FROM cities WHERE id LIKE 'pgrepo-fbloc-%'")
        self.repo = PostgresRepository(self.pool, self.UID)

    def tearDown(self):
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM cities WHERE id LIKE 'pgrepo-fbloc-%'")
            conn.execute("DELETE FROM users WHERE uid = %s", (self.UID,))
        self.pool.close()

    def test_get_cities_exposes_fb_location_id_or_none(self):
        self.repo.add_city_to_catalog(self.ID_FIXED, {"name": "Bromont test", "fbLocationId": "103111009728836"})
        self.repo.add_city_to_catalog(self.ID_PLAIN, {"name": "Granby test"})
        self.repo.set_city_user_pref(self.ID_FIXED, True)
        self.repo.set_city_user_pref(self.ID_PLAIN, True)
        by_id = {c["id"]: c for c in self.repo.get_cities()}
        self.assertEqual(by_id[self.ID_FIXED]["fbLocationId"], "103111009728836")
        self.assertIsNone(by_id[self.ID_PLAIN]["fbLocationId"])

    def test_catalog_listing_exposes_it(self):
        self.repo.add_city_to_catalog(self.ID_FIXED, {"name": "Bromont test", "fbLocationId": "42"})
        self.assertEqual(self.repo.get_all_catalog_cities()[self.ID_FIXED]["fbLocationId"], "42")

    def test_partial_merge_neither_clears_nor_requires_it(self):
        self.repo.add_city_to_catalog(self.ID_FIXED, {"name": "Bromont test", "latitude": 45.3, "fbLocationId": "42"})
        self.repo.add_city_to_catalog(self.ID_FIXED, {"latitude": 45.4})          # merge partiel sans fbLocationId
        city = self.repo.get_all_catalog_cities()[self.ID_FIXED]
        self.assertEqual((city["latitude"], city["fbLocationId"]), (45.4, "42"))
        self.repo.add_city_to_catalog(self.ID_FIXED, {"fbLocationId": "43"})      # et l'inverse
        city = self.repo.get_all_catalog_cities()[self.ID_FIXED]
        self.assertEqual((city["latitude"], city["fbLocationId"]), (45.4, "43"))

    def test_two_cities_can_share_one_facebook_id(self):
        self.repo.add_city_to_catalog(self.ID_FIXED, {"name": "Saint-Hubert test", "fbLocationId": "77"})
        self.repo.add_city_to_catalog(self.ID_PLAIN, {"name": "Longueuil test", "fbLocationId": "77"})
        catalog = self.repo.get_all_catalog_cities()
        self.assertEqual(catalog[self.ID_FIXED]["fbLocationId"], catalog[self.ID_PLAIN]["fbLocationId"])


if __name__ == "__main__":
    unittest.main()
