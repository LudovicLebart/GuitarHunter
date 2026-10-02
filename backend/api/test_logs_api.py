"""Tests d'intégration de `GET /logs` (LogViewer, migration Firestore → Postgres).

Même principe que test_users_api.py : vraie base Postgres, pas de mocks ; se saute proprement
si aucun Postgres n'est joignable.
"""
import asyncio
import unittest

import asyncpg
from fastapi.testclient import TestClient

from backend.api.auth import get_current_uid
from backend.api.db import DATABASE_URL
from backend.api.main import app
from backend.api.test_deals_api import _pg_reachable


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestLogsAPI(unittest.TestCase):
    UID = "test-uid-logs-1"
    OTHER_UID = "test-uid-logs-2"

    def setUp(self):
        app.dependency_overrides[get_current_uid] = lambda: self.UID
        self.client = TestClient(app)
        self.client.__enter__()

        async def _seed():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                for uid in (self.UID, self.OTHER_UID):
                    await conn.execute("INSERT INTO users (uid) VALUES ($1) ON CONFLICT (uid) DO NOTHING", uid)
                await conn.execute("DELETE FROM logs WHERE user_id = ANY($1::text[])", [self.UID, self.OTHER_UID])
                for i in range(5):
                    await conn.execute(
                        "INSERT INTO logs (user_id, message, level) VALUES ($1, $2, 'INFO')", self.UID, f"mine-{i}",
                    )
                await conn.execute(
                    "INSERT INTO logs (user_id, message, level) VALUES ($1, 'other-user', 'ERROR')", self.OTHER_UID,
                )
            finally:
                await conn.close()

        asyncio.run(_seed())

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()

        async def _cleanup():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("DELETE FROM users WHERE uid = ANY($1::text[])", [self.UID, self.OTHER_UID])
            finally:
                await conn.close()

        asyncio.run(_cleanup())

    def test_returns_only_own_logs_oldest_first(self):
        resp = self.client.get("/logs")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([r["message"] for r in resp.json()], [f"mine-{i}" for i in range(5)])

    def test_limit_keeps_the_most_recent(self):
        resp = self.client.get("/logs?limit=2")
        self.assertEqual([r["message"] for r in resp.json()], ["mine-3", "mine-4"])

    def test_row_shape(self):
        row = self.client.get("/logs?limit=1").json()[0]
        self.assertEqual(set(row), {"id", "message", "level", "created_at"})

    def test_limit_out_of_bounds_is_rejected(self):
        self.assertEqual(self.client.get("/logs?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/logs?limit=5000").status_code, 422)


if __name__ == "__main__":
    unittest.main()
