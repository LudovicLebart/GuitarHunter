"""Tests d'intégration pour la tranche "annonces partagées" (dernière) du Chantier A. Même
principe que les autres : vraie base Postgres, se saute proprement si injoignable.
"""
import asyncio
import unittest

import asyncpg

from backend.api.db import DATABASE_URL
from backend.api.main import app
from backend.api.auth import get_current_uid
from backend.api.test_deals_api import _pg_reachable


async def _cleanup(*, deal_ids):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DELETE FROM shared_deals WHERE id = ANY($1::text[])", list(deal_ids))
    finally:
        await conn.close()


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestSharedDealsAPI(unittest.TestCase):
    UID = "test-uid-shared-1"
    DEAL_ID = "shared-deal-1"

    def setUp(self):
        from fastapi.testclient import TestClient
        app.dependency_overrides[get_current_uid] = lambda: self.UID
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        asyncio.run(_cleanup(deal_ids=[self.DEAL_ID]))

    def test_upsert_then_public_read_roundtrip(self):
        resp = self.client.put(f"/shared-deals/{self.DEAL_ID}", json={
            "title": "Martin D-28", "price": 2500, "location": "Montréal, QC",
            "verdict": "GOOD_DEAL", "scores": {"price_score": 8}, "tier3_summary": "Bel état général.",
        })
        self.assertEqual(resp.status_code, 204, resp.text)

        # Lecture publique : aucun override d'auth nécessaire, la route n'a pas de Depends.
        app.dependency_overrides.clear()
        read = self.client.get(f"/shared-deals/{self.DEAL_ID}")
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.json()["title"], "Martin D-28")
        self.assertEqual(read.json()["scores"]["price_score"], 8)
        self.assertEqual(read.json()["tier3_summary"], "Bel état général.")

    def test_upsert_replaces_entire_snapshot_not_merge(self):
        self.client.put(f"/shared-deals/{self.DEAL_ID}", json={"title": "A", "verdict": "GOOD_DEAL"})
        self.client.put(f"/shared-deals/{self.DEAL_ID}", json={"title": "B"})  # pas de verdict cette fois

        app.dependency_overrides.clear()
        read = self.client.get(f"/shared-deals/{self.DEAL_ID}")
        self.assertEqual(read.json()["title"], "B")
        self.assertIsNone(read.json()["verdict"])  # remplacé, pas fusionné avec l'ancien

    def test_get_unknown_shared_deal_returns_404(self):
        app.dependency_overrides.clear()
        resp = self.client.get("/shared-deals/does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_write_requires_auth(self):
        app.dependency_overrides.clear()
        resp = self.client.put(f"/shared-deals/{self.DEAL_ID}", json={"title": "x"})
        # Sans override et sans en-tête Authorization : FastAPI rejette avant même d'atteindre
        # get_current_uid (Header(...) obligatoire) -> 422, pas 401 (réservé à un token présent
        # mais invalide/mal formé, voir auth.py::get_current_uid).
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
