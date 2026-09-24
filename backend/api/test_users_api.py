"""Tests d'intégration pour la tranche "config utilisateur / botStatus" du Chantier A
(Phase A.2) — remplace onBotConfigUpdate/updateUserConfig (firestoreService.js).

Même principe que test_deals_api.py : vraie base Postgres, pas de mocks ; se saute proprement
si aucun Postgres n'est joignable. Le WebSocket est testé avec un vrai serveur uvicorn (pas le
TestClient), pour la même raison que test_deals_api.py::TestDealsWebSocket.
"""
import asyncio
import json
import unittest
from unittest.mock import patch

import asyncpg
import requests
import websockets.sync.client as ws_sync_client
from fastapi.testclient import TestClient

from backend.api.db import DATABASE_URL, _register_json_codecs
from backend.api.main import app
from backend.api.auth import get_current_uid
from backend.api.test_deals_api import _pg_reachable, _RealServer


async def _cleanup(*, user_ids):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DELETE FROM users WHERE uid = ANY($1::text[])", list(user_ids))
    finally:
        await conn.close()


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestUsersConfigAPI(unittest.TestCase):
    UID = "test-uid-config-1"
    OTHER_UID = "test-uid-config-2"

    def setUp(self):
        app.dependency_overrides[get_current_uid] = lambda: self.UID
        self.client = TestClient(app)
        self.client.__enter__()

        async def _seed():
            conn = await asyncpg.connect(DATABASE_URL)
            await _register_json_codecs(conn)
            try:
                await conn.execute(
                    "INSERT INTO users (uid, config) VALUES ($1, $2) ON CONFLICT (uid) DO NOTHING",
                    self.UID, {"scanConfig": {"frequency": 60, "maxPrice": 500}, "exclusionKeywords": ["case"]},
                )
            finally:
                await conn.close()

        asyncio.run(_seed())

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        asyncio.run(_cleanup(user_ids=[self.UID, self.OTHER_UID]))

    def test_get_config_merges_bot_status(self):
        resp = self.client.get("/users/me/config")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["botStatus"], "idle")
        self.assertEqual(body["scanConfig"], {"frequency": 60, "maxPrice": 500})

    def test_get_config_404_when_user_not_bootstrapped_yet(self):
        app.dependency_overrides[get_current_uid] = lambda: "test-uid-config-never-seen"
        resp = self.client.get("/users/me/config")
        self.assertEqual(resp.status_code, 404)

    def test_patch_config_deep_merges_nested_object(self):
        """Équivalent `setDoc(doc, unflatten(newConfig), { merge: true })` côté Firestore : ne
        touche que les clés présentes dans le patch, à N'IMPORTE quelle profondeur — `maxPrice`
        ne doit pas disparaître alors que seul `frequency` est modifié."""
        resp = self.client.patch("/users/me/config", json={"scanConfig": {"frequency": 30}})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["scanConfig"], {"frequency": 30, "maxPrice": 500})
        self.assertEqual(body["exclusionKeywords"], ["case"])  # inchangé, clé de premier niveau absente du patch

        refetch = self.client.get("/users/me/config").json()
        self.assertEqual(refetch["scanConfig"]["frequency"], 30)

    def test_patch_config_replaces_arrays_wholesale(self):
        """Un tableau n'est jamais fusionné élément par élément (comme Firestore merge:true) —
        seule une clé de premier niveau ABSENTE du patch est préservée."""
        resp = self.client.patch("/users/me/config", json={"exclusionKeywords": ["neuf"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["exclusionKeywords"], ["neuf"])

    def test_patch_config_404_when_user_not_bootstrapped_yet(self):
        app.dependency_overrides[get_current_uid] = lambda: "test-uid-config-never-seen"
        resp = self.client.patch("/users/me/config", json={"scanConfig": {"frequency": 30}})
        self.assertEqual(resp.status_code, 404)


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestUsersConfigWebSocket(unittest.TestCase):
    UID = "test-uid-config-ws-1"

    def setUp(self):
        async def _seed():
            conn = await asyncpg.connect(DATABASE_URL)
            await _register_json_codecs(conn)
            try:
                await conn.execute(
                    "INSERT INTO users (uid, config) VALUES ($1, $2) ON CONFLICT (uid) DO NOTHING",
                    self.UID, {"scanConfig": {"frequency": 60}},
                )
            finally:
                await conn.close()

        asyncio.run(_seed())
        app.dependency_overrides[get_current_uid] = lambda: self.UID

    def tearDown(self):
        app.dependency_overrides.clear()
        asyncio.run(_cleanup(user_ids=[self.UID]))

    def test_websocket_receives_notification_on_own_config_change_only(self):
        with patch("backend.api.main.verify_token", return_value=self.UID), _RealServer(app) as srv:
            with ws_sync_client.connect(f"{srv.ws_url}/ws/users/me/config?token=fake-mine") as ws_mine:
                with ws_sync_client.connect(f"{srv.ws_url}/ws/users/me/config?token=fake-other") as ws_other:
                    self.assertEqual(json.loads(ws_mine.recv(timeout=5))["type"], "ready")
                    self.assertEqual(json.loads(ws_other.recv(timeout=5))["type"], "ready")

                    resp = requests.patch(
                        f"{srv.base_url}/users/me/config", json={"scanConfig": {"frequency": 45}}, timeout=5
                    )
                    self.assertEqual(resp.status_code, 200)

                    message = json.loads(ws_mine.recv(timeout=5))
                    self.assertEqual(message["user_id"], self.UID)

                    second = json.loads(ws_other.recv(timeout=5))
                    self.assertEqual(second["user_id"], self.UID)


if __name__ == "__main__":
    unittest.main()
