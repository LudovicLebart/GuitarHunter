"""Tests d'intégration pour la tranche "commandes" du Chantier A (Postgres/FastAPI).

Contrairement au reste du backend (Firestore/Gemini, jamais accessibles depuis un
environnement de dev), Postgres peut tourner localement — ces tests parlent à une vraie
base, pas des mocks. Ils se sautent proprement (`unittest.SkipTest`) si aucun Postgres
n'est joignable via DATABASE_URL, pour ne pas casser un environnement (CI ou local) qui n'en
a pas encore un — voir FIRESTORE_MIGRATION_PLAN.md, ce chantier n'a pas encore d'infra CI dédiée.

Auth Firebase non testée ici (pas d'accès réel, comme le reste du projet) : la dépendance
`get_current_uid` est court-circuitée via `app.dependency_overrides` — ces tests valident le
contrat SQL/HTTP de la tranche commandes, pas la vérification de token elle-même.
"""
import asyncio
import unittest

import asyncpg
from fastapi.testclient import TestClient

from backend.api.db import DATABASE_URL
from backend.api.main import app
from backend.api.auth import get_current_uid


def _pg_reachable() -> bool:
    async def _check():
        conn = await asyncpg.connect(DATABASE_URL, timeout=2)
        await conn.close()

    try:
        asyncio.run(_check())
        return True
    except Exception:
        return False


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestCommandsAPI(unittest.TestCase):
    def setUp(self):
        self._uid = "test-uid-1"
        app.dependency_overrides[get_current_uid] = lambda: self._uid
        self.client = TestClient(app)
        self.client.__enter__()  # déclenche le lifespan (init_pool)

        async def _seed_user():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute(
                    "INSERT INTO users (uid) VALUES ($1), ($2) ON CONFLICT (uid) DO NOTHING",
                    "test-uid-1", "test-uid-2",
                )
            finally:
                await conn.close()

        asyncio.run(_seed_user())

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()

        async def _cleanup():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("DELETE FROM commands WHERE user_id IN ('test-uid-1', 'test-uid-2')")
                await conn.execute("DELETE FROM users WHERE uid IN ('test-uid-1', 'test-uid-2')")
            finally:
                await conn.close()

        asyncio.run(_cleanup())

    def test_create_and_get_command_roundtrip(self):
        resp = self.client.post("/commands", json={"type": "REFRESH", "payload": None})
        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()
        self.assertEqual(body["type"], "REFRESH")
        self.assertEqual(body["status"], "pending")

        get_resp = self.client.get(f"/commands/{body['id']}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["status"], "pending")

    def test_create_command_with_dict_payload(self):
        payload = {"dealId": "abc123", "forceExpert": False, "userComment": "essai"}
        resp = self.client.post("/commands", json={"type": "ANALYZE_DEAL", "payload": payload})
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(resp.json()["payload"], payload)

    def test_isolation_between_users(self):
        """Une commande créée par un utilisateur est invisible pour un autre (remplace les
        Firestore Security Rules — voir backend/api/auth.py)."""
        resp = self.client.post("/commands", json={"type": "REFRESH", "payload": None})
        command_id = resp.json()["id"]

        app.dependency_overrides[get_current_uid] = lambda: "test-uid-2"
        other_resp = self.client.get(f"/commands/{command_id}")
        self.assertEqual(other_resp.status_code, 404)

    def test_pending_command_visible_to_bot_side_repo(self):
        """Le bot lira directement Postgres (pas l'API HTTP) une fois la bascule faite —
        vérifie que commands_repo.list_pending_commands() voit bien ce que l'API a écrit.

        Connexion directe indépendante du pool de l'API (lié à la boucle asyncio interne du
        TestClient) : un nouvel event loop ici ne peut pas réutiliser ce pool
        ("attached to a different loop"), donc on ouvre une connexion asyncpg à part —
        exactement ce que ferait le process bot, séparé du process API en production."""
        from backend.api import commands_repo

        self.client.post("/commands", json={"type": "SCAN_URL", "payload": "https://example.com/x"})

        async def _check():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                return await commands_repo.list_pending_commands(conn, "test-uid-1")
            finally:
                await conn.close()

        rows = asyncio.run(_check())
        self.assertTrue(any(r["type"] == "SCAN_URL" for r in rows))


if __name__ == "__main__":
    unittest.main()
