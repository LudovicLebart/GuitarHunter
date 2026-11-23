"""API Leaf Hunter (`/leaf/*`) : vraie base Postgres, se saute si injoignable. Données INVENTÉES (dépôt public)."""
import asyncio
import os
import unittest
from unittest import mock

import asyncpg
from fastapi.testclient import TestClient

from backend.api.auth import get_current_uid
from backend.api.db import DATABASE_URL
from backend.api.main import app
from backend.api.test_deals_api import _pg_reachable

ME, OTHER = "test-uid-leaf-api-me", "test-uid-leaf-api-other"


async def _seed():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        for uid in (ME, OTHER):
            await conn.execute("INSERT INTO users (uid) VALUES ($1) ON CONFLICT DO NOTHING", uid)
        await conn.execute("INSERT INTO vehicle_deals (id, source, title, price, year, km, flags, analysis, status) VALUES "
                           "('leaf_api_1','test','2017 Leaf SV',6000,2017,90000,'[\"soh_unknown\"]','{\"winter_fit\":{\"verdict\":\"ok\"}}','active'),"
                           "('leaf_api_2','test','2016 Leaf S',5000,2016,120000,'[]','{}','sold') ON CONFLICT DO NOTHING")
        await conn.execute("INSERT INTO user_vehicle_matches (user_id, deal_id) VALUES ($1,'leaf_api_1'),($1,'leaf_api_2') ON CONFLICT DO NOTHING", ME)
        await conn.execute("INSERT INTO vehicle_price_history (deal_id, price) VALUES ('leaf_api_1',6200),('leaf_api_1',6000)")
        await conn.execute("INSERT INTO scrape_runs (user_id, source, outcome, cards_seen) VALUES ($1,'leaf_kijiji','ok',12),($1,'kijiji','ok',3)", ME)
    finally:
        await conn.close()


async def _cleanup():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DELETE FROM scrape_runs WHERE user_id = ANY($1::text[])", [ME, OTHER])
        await conn.execute("DELETE FROM vehicle_deals WHERE id LIKE 'leaf_api_%'")
        await conn.execute("DELETE FROM users WHERE uid = ANY($1::text[])", [ME, OTHER])
    finally:
        await conn.close()


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestLeafAPI(unittest.TestCase):
    uid = ME

    def setUp(self):
        app.dependency_overrides[get_current_uid] = lambda: self.uid
        self.client = TestClient(app)
        self.client.__enter__()
        asyncio.run(_cleanup())
        asyncio.run(_seed())

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        asyncio.run(_cleanup())

    def test_list_hides_sold_by_default_and_exposes_columns(self):
        rows = self.client.get("/leaf/deals").json()
        self.assertEqual([r["id"] for r in rows], ["leaf_api_1"])
        self.assertEqual((rows[0]["price"], rows[0]["year"], rows[0]["flags"], rows[0]["analysis"]["winter_fit"]["verdict"],
                          rows[0]["is_favorite"]), (6000, 2017, ["soh_unknown"], "ok", False))
        self.assertEqual([r["id"] for r in self.client.get("/leaf/deals?includeSold=true").json()], ["leaf_api_2", "leaf_api_1"])

    def test_other_user_sees_nothing_and_cannot_touch(self):
        self.uid = OTHER
        self.assertEqual(self.client.get("/leaf/deals").json(), [])
        self.assertEqual(self.client.get("/leaf/deals/leaf_api_1").status_code, 404)
        self.assertEqual(self.client.patch("/leaf/deals/leaf_api_1/state", json={"isFavorite": True}).status_code, 404)

    def test_detail_includes_price_history(self):
        d = self.client.get("/leaf/deals/leaf_api_1").json()
        self.assertEqual([h["price"] for h in d["priceHistory"]], [6200, 6000])

    def test_state_patch_is_partial_and_rejected_hides_from_list(self):
        r = self.client.patch("/leaf/deals/leaf_api_1/state", json={"isFavorite": True, "notes": "à voir"}).json()
        self.assertEqual((r["is_favorite"], r["notes"], r["is_rejected"]), (True, "à voir", False))
        r = self.client.patch("/leaf/deals/leaf_api_1/state", json={"checklist": {"leafspy": True}}).json()
        self.assertEqual((r["is_favorite"], r["notes"], r["checklist"]), (True, "à voir", {"leafspy": True}))
        self.client.patch("/leaf/deals/leaf_api_1/state", json={"isRejected": True})
        self.assertEqual(self.client.get("/leaf/deals").json(), [])
        self.assertEqual(len(self.client.get("/leaf/deals?includeRejected=true").json()), 1)

    def test_state_validation(self):
        self.assertEqual(self.client.patch("/leaf/deals/leaf_api_1/state", json={}).status_code, 422)
        self.assertEqual(self.client.patch("/leaf/deals/leaf_api_1/state", json={"isFavorite": None}).status_code, 422)
        self.assertEqual(self.client.patch("/leaf/deals/leaf_api_1/state", json={"notes": "x" * 5001}).status_code, 422)

    def test_withdrawn_by_filters_is_hidden_and_not_confused_with_sold(self):
        async def withdraw():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("UPDATE user_vehicle_matches SET withdrawn = true WHERE user_id = $1 AND deal_id = 'leaf_api_1'", ME)
            finally:
                await conn.close()
        asyncio.run(withdraw())
        self.assertEqual(self.client.get("/leaf/deals").json(), [])                                  # actives et non écartées : rien
        self.assertEqual([r["id"] for r in self.client.get("/leaf/deals?includeSold=true").json()], ["leaf_api_2"])  # « vendues » seulement
        rows = self.client.get("/leaf/deals?includeRejected=true").json()
        self.assertEqual([(r["id"], r["withdrawn"]) for r in rows], [("leaf_api_1", True)])           # écartées par les filtres

    def test_runs_only_leaf_sources(self):
        runs = self.client.get("/leaf/runs").json()
        self.assertEqual([(r["source"], r["outcome"], r["cards_seen"]) for r in runs], [("leaf_kijiji", "ok", 12)])

    def test_allow_list_blocks_other_accounts(self):
        with mock.patch.dict(os.environ, {"LEAF_ALLOWED_UIDS": OTHER}):
            self.assertEqual(self.client.get("/leaf/deals").status_code, 403)
        with mock.patch.dict(os.environ, {"LEAF_ALLOWED_UIDS": f"{OTHER}, {ME}"}):
            self.assertEqual(self.client.get("/leaf/deals").status_code, 200)


if __name__ == "__main__":
    unittest.main()
