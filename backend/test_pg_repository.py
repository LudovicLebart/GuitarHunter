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
            conn.execute("DELETE FROM guitar_deals WHERE user_id IN (%s, %s)", (self.UID, self.OTHER_UID))
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
            {"title": "Parlor satinée", "price": 450, "description": "Belle guitare", "link": "https://x"},
            {"verdict": "GOOD_DEAL", "deal_score": 8, "brand": "Gibson"},
        )
        deal = self.repo.get_deal_by_id(self.DEAL_ID)
        self.assertEqual(deal["title"], "Parlor satinée")
        self.assertEqual(deal["status"], "analyzed")
        self.assertEqual(deal["description"], "Belle guitare")
        self.assertIsNone(deal["imageUrl"])  # jamais écrit, toujours None

    def test_create_new_deal_rejected_verdict_sets_status(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "REJECTED"})
        self.assertEqual(self.repo.get_deal_by_id(self.DEAL_ID)["status"], "rejected")

    def test_create_new_deal_does_not_reassign_ownership_of_another_users_deal(self):
        """`guitar_deals.id` est une clé globale (id de l'annonce marketplace, pas scopée par
        utilisateur) : deux bots (deux users) peuvent tomber sur la même annonce publique. Le
        second `create_new_deal` sur le même `deal_id` ne doit PAS réassigner la ligne à l'autre
        utilisateur (bug de revue de code — `ON CONFLICT DO UPDATE` sans garde de propriétaire)."""
        self.repo.create_new_deal(self.DEAL_ID, {"title": "Original owner's title"}, {"verdict": "GOOD_DEAL"})

        self.other_repo.create_new_deal(self.DEAL_ID, {"title": "Intruder's title"}, {"verdict": "GOOD_DEAL"})

        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT user_id, title FROM guitar_deals WHERE id = %s", (self.DEAL_ID,)
            ).fetchone()
        self.assertEqual(row["user_id"], self.UID)
        self.assertEqual(row["title"], "Original owner's title")
        # L'autre utilisateur ne voit tout simplement pas l'annonce d'un autre.
        self.assertIsNone(self.other_repo.get_deal_by_id(self.DEAL_ID))

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

    def test_get_active_listings_returns_row_like_objects(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x", "link": "https://x"}, {"verdict": "GOOD_DEAL"})
        listings = self.repo.get_active_listings()
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].id, self.DEAL_ID)
        self.assertEqual(listings[0].to_dict()["link"], "https://x")

    def test_delete_listing(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "GOOD_DEAL"})
        self.repo.delete_listing(self.DEAL_ID)
        self.assertIsNone(self.repo.get_deal_by_id(self.DEAL_ID))

    def test_retry_queue_and_mark_all_for_reanalysis(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "GOOD_DEAL"})
        count = self.repo.mark_all_for_reanalysis()
        self.assertEqual(count, 1)

        docs = self.repo.get_retry_queue_listings()
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].id, self.DEAL_ID)
        self.assertEqual(docs[0].to_dict()["title"], "x")

    def test_manual_analysis_overrides_reapplied_on_next_analysis(self):
        self.repo.create_new_deal(self.DEAL_ID, {"title": "x"}, {"verdict": "GOOD_DEAL"})
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE guitar_deals SET manual_analysis_overrides = %s WHERE id = %s",
                (Jsonb({"brand": "Corrigé Manuellement"}), self.DEAL_ID),
            )
        self.repo.update_deal_analysis(self.DEAL_ID, {"verdict": "GOOD_DEAL", "brand": "IA"})
        self.assertEqual(self.repo.get_deal_by_id(self.DEAL_ID)["brand"], "Corrigé Manuellement")

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


if __name__ == "__main__":
    unittest.main()
