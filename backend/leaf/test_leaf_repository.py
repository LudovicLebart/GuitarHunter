"""Dépôt Leaf côté bot (psycopg) et côté API (asyncpg) contre un Postgres JETABLE (`KB_TEST_DATABASE_URL`, base vidée).
Données INVENTÉES uniquement (dépôt public). Se saute sans la variable."""
import asyncio
import os
import unittest

URL = os.getenv("KB_TEST_DATABASE_URL")
SCHEMA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api", "schema.sql")


def _schema():
    with open(SCHEMA, encoding="utf-8") as fh:
        return fh.read()


def listing(id_="leaf_test_1", price=6000, **extra):
    base = {"id": id_, "source": "test", "source_id": id_[-1], "url": "https://exemple.invalide/1", "title": "2017 Nissan Leaf SV",
            "description": "annonce de test", "price": price, "year": 2017, "trim": "SV", "km": 90000,
            "battery_kwh_low": 30, "battery_kwh_high": 30, "battery_source": "inferred", "city": "Ville-Test",
            "latitude": 45.5, "longitude": -73.5, "image_urls": ["https://exemple.invalide/p.jpg"],
            "flags": ["soh_unknown"], "battery_score": None, "winter_fit": {"verdict": "ok", "low_km": 90},
            "mentions": {"heat_pump": True}}
    base.update(extra)
    return base


@unittest.skipUnless(URL, "définir KB_TEST_DATABASE_URL (base Postgres JETABLE)")
class TestLeafRepository(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        from backend.leaf.repository import LeafRepository
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute(_schema())
            conn.execute("TRUNCATE vehicle_deals, user_vehicle_matches, user_vehicle_state, vehicle_price_history CASCADE")
            conn.execute("INSERT INTO users (uid) VALUES ('u-leaf-1'), ('u-leaf-2') ON CONFLICT DO NOTHING")
        self.pool = ConnectionPool(URL, min_size=1, max_size=3, kwargs={"row_factory": dict_row}, open=True)
        self.addCleanup(self.pool.close)
        self.repo = LeafRepository(self.pool)

    def test_new_then_unchanged_then_price_changes(self):
        self.assertEqual(self.repo.upsert_listing(listing())["action"], "new")
        self.assertEqual(self.repo.upsert_listing(listing())["action"], "unchanged")
        r = self.repo.upsert_listing(listing(price=5500))
        self.assertEqual((r["action"], r["previous_price"]), ("price_drop", 6000.0))
        row = self.repo.get_vehicle("leaf_test_1")
        self.assertEqual((float(row["price"]), float(row["original_price"]), float(row["price_drop_amount"])),
                         (5500.0, 6000.0, 500.0))
        self.assertEqual(self.repo.upsert_listing(listing(price=5800))["action"], "price_up")
        self.assertIsNone(self.repo.get_vehicle("leaf_test_1")["price_drop_amount"])
        self.assertEqual([float(h["price"]) for h in self.repo.price_history("leaf_test_1")], [6000.0, 5500.0, 5800.0])

    def test_fields_are_mapped(self):
        self.repo.upsert_listing(listing())
        row = self.repo.get_vehicle("leaf_test_1")
        self.assertEqual((row["location"], row["link"], row["year"], row["km"]),
                         ("Ville-Test", "https://exemple.invalide/1", 2017, 90000))
        self.assertEqual(row["flags"], ["soh_unknown"])
        self.assertEqual(row["analysis"]["mentions"], {"heat_pump": True})
        self.assertNotIn("battery_score", row["analysis"])    # None : pas stocké

    def test_sold_then_seen_again_is_active(self):
        self.repo.upsert_listing(listing())
        self.assertEqual(self.repo.mark_sold(["leaf_test_1"]), 1)
        self.assertEqual(self.repo.mark_sold(["leaf_test_1"]), 0)
        self.assertEqual(self.repo.active_ids(), [])
        self.repo.upsert_listing(listing())
        self.assertEqual(self.repo.active_ids("test"), ["leaf_test_1"])
        self.assertIsNone(self.repo.get_vehicle("leaf_test_1")["sold_at"])

    def test_record_match_is_idempotent_and_per_user(self):
        self.repo.upsert_listing(listing())
        self.assertTrue(self.repo.record_match("u-leaf-1", "leaf_test_1"))
        self.assertFalse(self.repo.record_match("u-leaf-1", "leaf_test_1"))
        self.assertTrue(self.repo.record_match("u-leaf-2", "leaf_test_1"))

    def test_withdrawal_is_per_user_and_lifted_by_record_match(self):
        self.repo.upsert_listing(listing())
        self.repo.record_match("u-leaf-1", "leaf_test_1")
        self.repo.record_match("u-leaf-2", "leaf_test_1")
        self.assertEqual(self.repo.mark_withdrawn("u-leaf-1", ["leaf_test_1", "inconnue"]), 1)
        self.assertEqual(self.repo.mark_withdrawn("u-leaf-1", ["leaf_test_1"]), 0)
        with self.pool.connection() as conn:
            rows = {r["user_id"]: r["withdrawn"] for r in conn.execute("SELECT user_id, withdrawn FROM user_vehicle_matches").fetchall()}
        self.assertEqual(rows, {"u-leaf-1": True, "u-leaf-2": False})
        self.assertFalse(self.repo.record_match("u-leaf-1", "leaf_test_1"))       # lien déjà connu : pas « nouveau »...
        with self.pool.connection() as conn:
            self.assertFalse(conn.execute("SELECT withdrawn FROM user_vehicle_matches WHERE user_id='u-leaf-1'").fetchone()["withdrawn"])

    def test_comparables_only_complete_active_rows(self):
        self.repo.upsert_listing(listing())
        self.repo.upsert_listing(listing("leaf_test_2", km=None))
        self.assertEqual(self.repo.comparables(), [{"year": 2017, "km": 90000, "price": 6000.0}])

    def test_schema_is_replayable(self):
        import psycopg
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute(_schema())


@unittest.skipUnless(URL, "définir KB_TEST_DATABASE_URL (base Postgres JETABLE)")
class TestLeafApiRepo(unittest.TestCase):
    def setUp(self):
        import psycopg
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute(_schema())
            conn.execute("TRUNCATE vehicle_deals, user_vehicle_matches, user_vehicle_state, vehicle_price_history CASCADE")
            conn.execute("INSERT INTO users (uid) VALUES ('u-leaf-1'), ('u-leaf-2') ON CONFLICT DO NOTHING")
            conn.execute("INSERT INTO vehicle_deals (id, source, price, year, km) VALUES "
                         "('d1','test',6000,2017,90000), ('d2','test',5000,2016,120000)")
            conn.execute("INSERT INTO user_vehicle_matches (user_id, deal_id) VALUES ('u-leaf-1','d1'), ('u-leaf-1','d2')")
            conn.execute("INSERT INTO vehicle_price_history (deal_id, price) VALUES ('d1', 6200), ('d1', 6000)")

    def _run(self, coro_fn):
        from backend.api import leaf_repo
        from backend.api.db import _register_json_codecs     # mêmes codecs JSON que le pool réel de l'API
        import asyncpg

        async def go():
            pool = await asyncpg.create_pool(URL, min_size=1, max_size=2, init=_register_json_codecs)
            try:
                return await coro_fn(leaf_repo, pool)
            finally:
                await pool.close()
        return asyncio.run(go())

    def test_list_is_scoped_to_user_and_sorted_by_price(self):
        async def f(repo, pool):
            return ([r["id"] for r in await repo.list_deals(pool, "u-leaf-1")],
                    [r["id"] for r in await repo.list_deals(pool, "u-leaf-2")])
        self.assertEqual(self._run(f), (["d2", "d1"], []))

    def test_state_updates_only_given_fields_and_hides_rejected(self):
        async def f(repo, pool):
            a = await repo.set_state(pool, "u-leaf-1", "d1", is_favorite=True, notes="à voir")
            b = await repo.set_state(pool, "u-leaf-1", "d1", is_rejected=True)
            visible = [r["id"] for r in await repo.list_deals(pool, "u-leaf-1")]
            with_rej = [r["id"] for r in await repo.list_deals(pool, "u-leaf-1", include_rejected=True)]
            return a, b, visible, with_rej
        a, b, visible, with_rej = self._run(f)
        self.assertEqual((a["is_favorite"], a["notes"], a["is_rejected"]), (True, "à voir", False))
        self.assertEqual((b["is_favorite"], b["notes"], b["is_rejected"]), (True, "à voir", True))   # champs non fournis conservés
        self.assertEqual((visible, with_rej), (["d2"], ["d2", "d1"]))

    def test_checklist_roundtrip(self):
        async def f(repo, pool):
            return await repo.set_state(pool, "u-leaf-1", "d1", checklist={"leafspy": True})
        self.assertEqual(self._run(f)["checklist"], {"leafspy": True})

    def test_invisible_deal_cannot_be_read_or_written(self):
        async def f(repo, pool):
            return (await repo.get_deal(pool, "u-leaf-2", "d1"), await repo.set_state(pool, "u-leaf-2", "d1", is_favorite=True),
                    await repo.price_history(pool, "u-leaf-2", "d1"))
        self.assertEqual(self._run(f), (None, None, None))

    def test_unknown_field_is_refused_and_history_is_ordered(self):
        async def f(repo, pool):
            hist = await repo.price_history(pool, "u-leaf-1", "d1")
            try:
                await repo.set_state(pool, "u-leaf-1", "d1", price=1)
            except ValueError:
                return [float(h["price"]) for h in hist], True
            return [], False
        self.assertEqual(self._run(f), ([6200.0, 6000.0], True))


if __name__ == "__main__":
    unittest.main()
