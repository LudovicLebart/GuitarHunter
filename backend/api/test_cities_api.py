"""Tests d'intégration pour la tranche "villes" du Chantier A. Même principe que
test_chat_api.py/test_restoration_api.py : vraie base Postgres, se saute proprement si injoignable.

Le catalogue partagé (`cities`) n'est écrit par aucun repo de cette tranche (reste à
bot.py::add_city_auto() côté Firestore jusqu'à la bascule) — les tests le seedent directement
en SQL brut, comme _seed_deal_and_user le fait pour guitar_deals dans les tranches précédentes.
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


async def _seed_user_and_city(user_id, city_id, name="Montréal", needs_review=False):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("INSERT INTO users (uid) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
        await conn.execute(
            "INSERT INTO cities (id, name, latitude, longitude, needs_review) VALUES ($1, $2, 45.5, -73.5, $3) "
            "ON CONFLICT (id) DO NOTHING",
            city_id, name, needs_review,
        )
    finally:
        await conn.close()


async def _cleanup(*, city_ids, user_ids):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DELETE FROM user_city_prefs WHERE city_id = ANY($1::text[])", list(city_ids))
        await conn.execute("DELETE FROM cities WHERE id = ANY($1::text[])", list(city_ids))
        await conn.execute("DELETE FROM users WHERE uid = ANY($1::text[])", list(user_ids))
    finally:
        await conn.close()


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestCitiesAPI(unittest.TestCase):
    UID = "test-uid-cities-1"
    CITY_ID = "city-1"
    OTHER_CITY_ID = "city-2"

    def setUp(self):
        app.dependency_overrides[get_current_uid] = lambda: self.UID
        self.client = TestClient(app)
        self.client.__enter__()
        asyncio.run(_seed_user_and_city(self.UID, self.CITY_ID, "Montréal"))
        asyncio.run(_seed_user_and_city(self.UID, self.OTHER_CITY_ID, "Longueuil", needs_review=True))

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        asyncio.run(_cleanup(city_ids=[self.CITY_ID, self.OTHER_CITY_ID], user_ids=[self.UID]))

    def test_list_cities_defaults_to_not_scannable(self):
        resp = self.client.get("/cities")
        self.assertEqual(resp.status_code, 200)
        by_id = {c["id"]: c for c in resp.json()}
        self.assertFalse(by_id[self.CITY_ID]["is_scannable"])
        self.assertIsNone(by_id[self.CITY_ID]["kijiji_radius_km"])
        self.assertTrue(by_id[self.OTHER_CITY_ID]["needs_review"])

    def test_toggle_scannable_twice_round_trips(self):
        first = self.client.patch(f"/cities/{self.CITY_ID}/scannable")
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["isScannable"])

        second = self.client.patch(f"/cities/{self.CITY_ID}/scannable")
        self.assertFalse(second.json()["isScannable"])

    def test_toggle_scannable_unknown_city_returns_404(self):
        resp = self.client.patch("/cities/does-not-exist/scannable")
        self.assertEqual(resp.status_code, 404)

    def test_set_kijiji_radius_does_not_activate_scannable(self):
        resp = self.client.patch(f"/cities/{self.CITY_ID}/kijiji-radius", json={"radiusKm": 40})
        self.assertEqual(resp.status_code, 200)

        listing = {c["id"]: c for c in self.client.get("/cities").json()}
        self.assertEqual(float(listing[self.CITY_ID]["kijiji_radius_km"]), 40.0)
        self.assertFalse(listing[self.CITY_ID]["is_scannable"])  # pas d'activation implicite

    def test_clear_kijiji_radius_with_null(self):
        self.client.patch(f"/cities/{self.CITY_ID}/kijiji-radius", json={"radiusKm": 40})
        resp = self.client.patch(f"/cities/{self.CITY_ID}/kijiji-radius", json={"radiusKm": None})
        self.assertEqual(resp.status_code, 200)

        listing = {c["id"]: c for c in self.client.get("/cities").json()}
        self.assertIsNone(listing[self.CITY_ID]["kijiji_radius_km"])

    def test_delete_city_pref_resets_to_not_scannable(self):
        self.client.patch(f"/cities/{self.CITY_ID}/scannable")  # active
        resp = self.client.delete(f"/cities/{self.CITY_ID}/pref")
        self.assertEqual(resp.status_code, 204)

        listing = {c["id"]: c for c in self.client.get("/cities").json()}
        self.assertFalse(listing[self.CITY_ID]["is_scannable"])
        # La ville reste dans le catalogue partagé (deleteCity ne touche jamais `cities`).
        self.assertIn(self.CITY_ID, listing)


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestCitiesWebSocket(unittest.TestCase):
    """Classe séparée du TestClient, même raison que TestDealsWebSocket/TestChatWebSocket."""

    UID = "test-uid-cities-ws-1"
    CITY_ID = "city-ws-1"

    def setUp(self):
        asyncio.run(_seed_user_and_city(self.UID, self.CITY_ID))
        app.dependency_overrides[get_current_uid] = lambda: self.UID

    def tearDown(self):
        app.dependency_overrides.clear()
        asyncio.run(_cleanup(city_ids=[self.CITY_ID], user_ids=[self.UID]))

    def test_websocket_receives_own_pref_change(self):
        with patch("backend.api.main.verify_token", return_value=self.UID), _RealServer(app) as srv:
            with ws_sync_client.connect(f"{srv.ws_url}/ws/cities?token=fake") as ws:
                self.assertEqual(json.loads(ws.recv(timeout=5))["type"], "ready")

                resp = requests.patch(f"{srv.base_url}/cities/{self.CITY_ID}/scannable", timeout=5)
                self.assertEqual(resp.status_code, 200, resp.text)

                message = json.loads(ws.recv(timeout=5))
                self.assertEqual(message["type"], "city_pref_changed")
                self.assertEqual(message["cityId"], self.CITY_ID)


if __name__ == "__main__":
    unittest.main()
