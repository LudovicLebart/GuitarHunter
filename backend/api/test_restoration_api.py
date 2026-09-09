"""Tests d'intégration pour la tranche "plan de restauration" du Chantier A. Même principe que
test_chat_api.py : vraie base Postgres, se saute proprement si injoignable.
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
from backend.api.test_deals_api import _pg_reachable, _RealServer


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
        await conn.execute("DELETE FROM restoration_plan_items WHERE deal_id = ANY($1::text[])", list(deal_ids))
        await conn.execute("DELETE FROM guitar_deals WHERE id = ANY($1::text[])", list(deal_ids))
        await conn.execute("DELETE FROM users WHERE uid = ANY($1::text[])", list(user_ids))
    finally:
        await conn.close()


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestRestorationPlanAPI(unittest.TestCase):
    UID = "test-uid-plan-1"
    OTHER_UID = "test-uid-plan-2"
    DEAL_ID = "plan-deal-1"

    def setUp(self):
        app.dependency_overrides[get_current_uid] = lambda: self.UID
        self.client = TestClient(app)
        self.client.__enter__()
        asyncio.run(_seed_deal_and_user(self.DEAL_ID, self.UID))
        asyncio.run(_seed_deal_and_user("plan-deal-other", self.OTHER_UID))

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        asyncio.run(_cleanup(deal_ids=[self.DEAL_ID, "plan-deal-other"], user_ids=[self.UID, self.OTHER_UID]))

    def test_add_and_list_items(self):
        resp = self.client.post(f"/deals/{self.DEAL_ID}/restoration-plan", json={
            "label": "Refret", "category": "frettes", "estimatedCost": 150.0,
        })
        self.assertEqual(resp.status_code, 201, resp.text)

        listing = self.client.get(f"/deals/{self.DEAL_ID}/restoration-plan")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()), 1)
        item = listing.json()[0]
        self.assertEqual(item["label"], "Refret")
        self.assertEqual(item["status"], "pending")
        self.assertEqual(float(item["estimated_cost"]), 150.0)

    def test_patch_status_sets_and_clears_completed_at(self):
        create = self.client.post(f"/deals/{self.DEAL_ID}/restoration-plan", json={"label": "Nettoyage"})
        item_id = create.json()["id"]

        done = self.client.patch(f"/deals/{self.DEAL_ID}/restoration-plan/{item_id}", json={"status": "done"})
        self.assertEqual(done.status_code, 200)
        listing = self.client.get(f"/deals/{self.DEAL_ID}/restoration-plan").json()
        self.assertIsNotNone(listing[0]["completed_at"])

        reopened = self.client.patch(f"/deals/{self.DEAL_ID}/restoration-plan/{item_id}", json={"status": "in_progress"})
        self.assertEqual(reopened.status_code, 200)
        listing = self.client.get(f"/deals/{self.DEAL_ID}/restoration-plan").json()
        self.assertIsNone(listing[0]["completed_at"])

    def test_patch_clears_field_explicitly_set_to_null(self):
        create = self.client.post(f"/deals/{self.DEAL_ID}/restoration-plan", json={
            "label": "Refret", "notes": "à faire vite",
        })
        item_id = create.json()["id"]

        resp = self.client.patch(f"/deals/{self.DEAL_ID}/restoration-plan/{item_id}", json={"notes": None})
        self.assertEqual(resp.status_code, 200)
        listing = self.client.get(f"/deals/{self.DEAL_ID}/restoration-plan").json()
        self.assertIsNone(listing[0]["notes"])

    def test_delete_item(self):
        create = self.client.post(f"/deals/{self.DEAL_ID}/restoration-plan", json={"label": "x"})
        item_id = create.json()["id"]

        resp = self.client.delete(f"/deals/{self.DEAL_ID}/restoration-plan/{item_id}")
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.client.get(f"/deals/{self.DEAL_ID}/restoration-plan").json(), [])

    def test_reorder_items(self):
        ids = []
        for label in ["A", "B", "C"]:
            create = self.client.post(f"/deals/{self.DEAL_ID}/restoration-plan", json={"label": label})
            ids.append(create.json()["id"])

        resp = self.client.patch(
            f"/deals/{self.DEAL_ID}/restoration-plan/order",
            json={"orderedItemIds": list(reversed(ids))},
        )
        self.assertEqual(resp.status_code, 200)

        listing = self.client.get(f"/deals/{self.DEAL_ID}/restoration-plan").json()
        self.assertEqual([item["id"] for item in listing], list(reversed(ids)))

    def test_add_photo_is_deduplicated_and_remove_photo(self):
        create = self.client.post(f"/deals/{self.DEAL_ID}/restoration-plan", json={"label": "x"})
        item_id = create.json()["id"]
        url = "https://storage.example/photo.jpg"

        self.client.post(f"/deals/{self.DEAL_ID}/restoration-plan/{item_id}/photos", json={"url": url})
        self.client.post(f"/deals/{self.DEAL_ID}/restoration-plan/{item_id}/photos", json={"url": url})  # doublon ignoré

        listing = self.client.get(f"/deals/{self.DEAL_ID}/restoration-plan").json()
        self.assertEqual(listing[0]["photo_urls"], [url])

        self.client.request("DELETE", f"/deals/{self.DEAL_ID}/restoration-plan/{item_id}/photos", json={"url": url})
        listing = self.client.get(f"/deals/{self.DEAL_ID}/restoration-plan").json()
        self.assertEqual(listing[0]["photo_urls"], [])

    def test_isolated_from_other_users_deal(self):
        resp = self.client.get("/deals/plan-deal-other/restoration-plan")
        self.assertEqual(resp.status_code, 404)

    def test_mutations_reject_item_id_from_another_users_deal(self):
        """IDOR trouvé en revue de code : les mutations ne filtraient QUE sur `item_id` (clé
        primaire globale, trivialement énumérable), jamais sur `deal_id` — un attaquant
        propriétaire de self.DEAL_ID (passe _require_deal_owner) pouvait donc modifier/supprimer
        l'étape de restauration d'une annonce appartenant à un AUTRE utilisateur."""
        app.dependency_overrides[get_current_uid] = lambda: self.OTHER_UID
        create = self.client.post("/deals/plan-deal-other/restoration-plan", json={"label": "original"})
        self.assertEqual(create.status_code, 201, create.text)
        other_item_id = create.json()["id"]

        app.dependency_overrides[get_current_uid] = lambda: self.UID
        patch = self.client.patch(f"/deals/{self.DEAL_ID}/restoration-plan/{other_item_id}", json={"label": "hacked"})
        self.assertEqual(patch.status_code, 404)

        photo = self.client.post(f"/deals/{self.DEAL_ID}/restoration-plan/{other_item_id}/photos", json={
            "url": "https://storage.example/hacked.jpg",
        })
        self.assertEqual(photo.status_code, 404)

        delete = self.client.delete(f"/deals/{self.DEAL_ID}/restoration-plan/{other_item_id}")
        self.assertEqual(delete.status_code, 404)

        # Réordonnancement (bulk, sans 404 individuel) : un id étranger glissé dans la liste
        # ne doit toucher AUCUNE ligne hors de self.DEAL_ID — vérifié en confirmant que l'étape
        # d'autrui garde son ordre d'origine (None, jamais assigné) après coup.
        reorder = self.client.patch(f"/deals/{self.DEAL_ID}/restoration-plan/order", json={
            "orderedItemIds": [other_item_id],
        })
        self.assertEqual(reorder.status_code, 200)

        # L'étape d'origine n'a subi AUCUNE des tentatives ci-dessus.
        app.dependency_overrides[get_current_uid] = lambda: self.OTHER_UID
        listing = self.client.get("/deals/plan-deal-other/restoration-plan").json()
        self.assertEqual(listing[0]["label"], "original")
        self.assertEqual(listing[0]["photo_urls"], None)
        self.assertIsNone(listing[0]["item_order"])
        app.dependency_overrides[get_current_uid] = lambda: self.UID


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestRestorationPlanWebSocket(unittest.TestCase):
    """Classe séparée du TestClient, même raison que TestDealsWebSocket/TestChatWebSocket."""

    UID = "test-uid-plan-ws-1"
    DEAL_ID = "plan-ws-deal-1"

    def setUp(self):
        asyncio.run(_seed_deal_and_user(self.DEAL_ID, self.UID))
        app.dependency_overrides[get_current_uid] = lambda: self.UID

    def tearDown(self):
        app.dependency_overrides.clear()
        asyncio.run(_cleanup(deal_ids=[self.DEAL_ID], user_ids=[self.UID]))

    def test_websocket_receives_new_item_and_deletion_for_this_deal_only(self):
        with patch("backend.api.main.verify_token", return_value=self.UID), _RealServer(app) as srv:
            with ws_sync_client.connect(f"{srv.ws_url}/ws/deals/{self.DEAL_ID}/restoration-plan?token=fake") as ws:
                self.assertEqual(json.loads(ws.recv(timeout=5))["type"], "ready")

                resp = requests.post(
                    f"{srv.base_url}/deals/{self.DEAL_ID}/restoration-plan",
                    json={"label": "Refret"},
                    timeout=5,
                )
                self.assertEqual(resp.status_code, 201, resp.text)
                item_id = resp.json()["id"]

                created = json.loads(ws.recv(timeout=5))
                self.assertEqual(created["deal_id"], self.DEAL_ID)
                self.assertEqual(created["id"], item_id)

                del_resp = requests.delete(
                    f"{srv.base_url}/deals/{self.DEAL_ID}/restoration-plan/{item_id}", timeout=5,
                )
                self.assertEqual(del_resp.status_code, 204)

                deleted = json.loads(ws.recv(timeout=5))
                self.assertEqual(deleted["id"], item_id)
                self.assertTrue(deleted["deleted"])


if __name__ == "__main__":
    unittest.main()
