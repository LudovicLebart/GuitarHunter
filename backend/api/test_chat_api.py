"""Tests d'intégration pour la tranche "chat" du Chantier A. Même principe que
test_api.py/test_deals_api.py : vraie base Postgres, se saute proprement si injoignable.
"""
import asyncio
import json
import unittest
from unittest.mock import patch

import asyncpg
import requests
import websockets.sync.client as ws_sync_client
from fastapi.testclient import TestClient

from backend.api.db import DATABASE_URL
from backend.api.main import app
from backend.api.auth import get_current_uid
from backend.api.test_deals_api import _pg_reachable, _RealServer  # réutilisés tels quels


async def _seed_deal_and_user(deal_id, user_id):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("INSERT INTO users (uid) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
        await conn.execute(
            "INSERT INTO guitar_deals (id, user_id, title) VALUES ($1, $2, 'x') "
            "ON CONFLICT (id) DO NOTHING",
            deal_id, user_id,
        )
    finally:
        await conn.close()


async def _cleanup(*, deal_ids, user_ids):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DELETE FROM deal_chat WHERE deal_id = ANY($1::text[])", list(deal_ids))
        await conn.execute("DELETE FROM guitar_deals WHERE id = ANY($1::text[])", list(deal_ids))
        await conn.execute("DELETE FROM users WHERE uid = ANY($1::text[])", list(user_ids))
    finally:
        await conn.close()


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestChatAPI(unittest.TestCase):
    UID = "test-uid-chat-1"
    OTHER_UID = "test-uid-chat-2"
    DEAL_ID = "chat-deal-1"

    def setUp(self):
        app.dependency_overrides[get_current_uid] = lambda: self.UID
        self.client = TestClient(app)
        self.client.__enter__()
        asyncio.run(_seed_deal_and_user(self.DEAL_ID, self.UID))
        asyncio.run(_seed_deal_and_user("chat-deal-other", self.OTHER_UID))

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        asyncio.run(_cleanup(deal_ids=[self.DEAL_ID, "chat-deal-other"], user_ids=[self.UID, self.OTHER_UID]))

    def test_add_and_list_messages(self):
        resp = self.client.post(f"/deals/{self.DEAL_ID}/chat", json={
            "role": "user", "parts": [{"text": "Bonjour"}], "displayText": "Bonjour",
        })
        self.assertEqual(resp.status_code, 201, resp.text)

        listing = self.client.get(f"/deals/{self.DEAL_ID}/chat")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()), 1)
        self.assertEqual(listing.json()[0]["display_text"], "Bonjour")

    def test_replace_message(self):
        create = self.client.post(f"/deals/{self.DEAL_ID}/chat", json={
            "role": "model", "parts": [{"text": "..."}], "displayText": "...", "isError": True,
        })
        message_id = create.json()["id"]

        replace = self.client.patch(f"/deals/{self.DEAL_ID}/chat/{message_id}", json={
            "parts": [{"text": "Réponse finale"}], "displayText": "Réponse finale", "isError": False,
        })
        self.assertEqual(replace.status_code, 200)

        listing = self.client.get(f"/deals/{self.DEAL_ID}/chat").json()
        self.assertEqual(listing[0]["display_text"], "Réponse finale")
        self.assertFalse(listing[0]["is_error"])

    def test_mark_added_to_gallery(self):
        create = self.client.post(f"/deals/{self.DEAL_ID}/chat", json={
            "role": "user", "parts": [{"text": "photo"}],
        })
        message_id = create.json()["id"]

        resp = self.client.patch(
            f"/deals/{self.DEAL_ID}/chat/{message_id}/gallery",
            json={"partIndex": 2, "url": "https://storage.example/x.jpg"},
        )
        self.assertEqual(resp.status_code, 200)

        listing = self.client.get(f"/deals/{self.DEAL_ID}/chat").json()
        self.assertEqual(listing[0]["added_to_gallery_urls"], {"2": "https://storage.example/x.jpg"})

    def test_mark_restoration_proposal_status(self):
        create = self.client.post(f"/deals/{self.DEAL_ID}/chat", json={
            "role": "model", "parts": [{"text": "..."}],
            "restorationProposals": [{"label": "Refret", "status": "pending"}],
        })
        message_id = create.json()["id"]

        resp = self.client.patch(
            f"/deals/{self.DEAL_ID}/chat/{message_id}/restoration-proposal",
            json={"proposalIndex": 0, "status": "applied", "itemId": "item-1"},
        )
        self.assertEqual(resp.status_code, 200)

        listing = self.client.get(f"/deals/{self.DEAL_ID}/chat").json()
        proposal = listing[0]["restoration_proposals"][0]
        self.assertEqual(proposal["status"], "applied")
        self.assertEqual(proposal["itemId"], "item-1")
        self.assertEqual(proposal["label"], "Refret")  # champs existants préservés

    def test_chat_isolated_from_other_users_deal(self):
        resp = self.client.get("/deals/chat-deal-other/chat")
        self.assertEqual(resp.status_code, 404)


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestChatWebSocket(unittest.TestCase):
    """Classe séparée du TestClient, même raison que TestDealsWebSocket
    (backend/api/test_deals_api.py) : pool asyncpg lié à une boucle différente."""

    UID = "test-uid-chat-ws-1"
    DEAL_ID = "chat-ws-deal-1"

    def setUp(self):
        asyncio.run(_seed_deal_and_user(self.DEAL_ID, self.UID))
        app.dependency_overrides[get_current_uid] = lambda: self.UID

    def tearDown(self):
        app.dependency_overrides.clear()
        asyncio.run(_cleanup(deal_ids=[self.DEAL_ID], user_ids=[self.UID]))

    def test_websocket_receives_new_message_for_this_deal_only(self):
        with patch("backend.api.main.verify_token", return_value=self.UID), _RealServer(app) as srv:
            with ws_sync_client.connect(f"{srv.ws_url}/ws/deals/{self.DEAL_ID}/chat?token=fake") as ws:
                self.assertEqual(json.loads(ws.recv(timeout=5))["type"], "ready")

                resp = requests.post(
                    f"{srv.base_url}/deals/{self.DEAL_ID}/chat",
                    json={"role": "user", "parts": [{"text": "salut"}], "displayText": "salut"},
                    timeout=5,
                )
                self.assertEqual(resp.status_code, 201, resp.text)

                message = json.loads(ws.recv(timeout=5))
                self.assertEqual(message["deal_id"], self.DEAL_ID)
                self.assertEqual(message["id"], resp.json()["id"])


if __name__ == "__main__":
    unittest.main()
