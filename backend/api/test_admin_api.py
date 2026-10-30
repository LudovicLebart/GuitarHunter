"""Tests d'intégration du Dashboard Administrateur (2026-10-11) et de `POST /users/me` : vraie base
Postgres, se saute proprement si injoignable (voir test_deals_api.py). Firebase Auth est remplacé par
un dictionnaire (`admin_repo._firebase_users_by_uid`) : aucun accès réseau.
"""
import asyncio
import unittest
from unittest.mock import patch

import asyncpg
from fastapi.testclient import TestClient

from backend.api import admin_repo
from backend.api.auth import get_admin_uid, get_current_uid
from backend.api.db import DATABASE_URL, _register_json_codecs
from backend.api.main import app
from backend.api.test_deals_api import _pg_reachable

ADMIN_UID = "test-admin-1"
TARGET_UID = "test-admin-target-1"
NEW_UID = "test-admin-new-1"


async def _run(sql, *args):
    conn = await asyncpg.connect(DATABASE_URL)
    await _register_json_codecs(conn)
    try:
        return await conn.fetch(sql, *args)
    finally:
        await conn.close()


async def _seed():
    await _run("INSERT INTO users (uid, config) VALUES ($1, $2) ON CONFLICT (uid) DO NOTHING",
               ADMIN_UID, {})
    await _run("INSERT INTO users (uid, bot_status, config) VALUES ($1, 'idle', $2) ON CONFLICT (uid) DO UPDATE SET bot_status='idle', config=$2",
               TARGET_UID, {"scanConfig": {"frequency": 60, "max_listings": 5}})
    await _run("INSERT INTO guitar_deals (id, title, model_used) VALUES ('adm-deal-1','x','flash-lite -> flash'), "
               "('adm-deal-2','x','flash-lite -> flash -> gemini-pro'), ('adm-deal-3','x','flash-lite'), "
               "('adm-deal-4','x','flash-lite -> flash -> claude-sonnet-5-5'), ('adm-deal-5','x','backfill_leger -> flash') ON CONFLICT (id) DO UPDATE SET model_used = EXCLUDED.model_used")
    for deal in ("adm-deal-1", "adm-deal-2", "adm-deal-3", "adm-deal-4", "adm-deal-5"):
        await _run("INSERT INTO user_deal_matches (user_id, deal_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", TARGET_UID, deal)


async def _cleanup():
    await _run("DELETE FROM user_deal_matches WHERE deal_id LIKE 'adm-deal-%'")
    await _run("DELETE FROM guitar_deals WHERE id LIKE 'adm-deal-%'")
    await _run("DELETE FROM commands WHERE user_id = ANY($1::text[])", [TARGET_UID, NEW_UID])
    await _run("DELETE FROM users WHERE uid = ANY($1::text[])", [ADMIN_UID, TARGET_UID, NEW_UID])


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestAdminAPI(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[get_admin_uid] = lambda: ADMIN_UID
        self.client = TestClient(app)
        self.client.__enter__()
        asyncio.run(_seed())
        self.auth_patch = patch.object(admin_repo, "_firebase_users_by_uid", lambda uids: {
            TARGET_UID: {"email": "cible@example.com", "lastLogin": "2026-10-10T12:00:00+00:00"},
        })
        self.auth_patch.start()

    def tearDown(self):
        self.auth_patch.stop()
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        asyncio.run(_cleanup())

    def test_list_users_merges_stats_and_firebase_identity(self):
        resp = self.client.get("/admin/users")
        self.assertEqual(resp.status_code, 200, resp.text)
        row = next(u for u in resp.json() if u["uid"] == TARGET_UID)
        self.assertEqual(row["email"], "cible@example.com")
        self.assertEqual(row["scanFrequency"], 60)
        self.assertEqual(row["maxListings"], 5)
        self.assertEqual(row["dailyVolume"], 5)
        self.assertEqual(row["reachedT2"], 3)   # 3 annonces passées par au moins 2 modèles (le backfill léger n'en fait pas partie)
        self.assertEqual(row["reachedT3"], 2)   # 1 modèle « pro » (Gemini) et 1 modèle « claude » (T3 Claude)
        self.assertGreater(row["estimatedDailyCost"], 0)

    def test_pause_creates_stop_bot_command(self):
        resp = self.client.post(f"/admin/users/{TARGET_UID}/pause")
        self.assertEqual(resp.status_code, 202, resp.text)
        rows = asyncio.run(_run("SELECT type FROM commands WHERE user_id = $1", TARGET_UID))
        self.assertEqual([r["type"] for r in rows], ["STOP_BOT"])

    def test_set_scan_frequency_merges_without_erasing_scan_config(self):
        resp = self.client.patch(f"/admin/users/{TARGET_UID}/scan-frequency", json={"minutes": 15})
        self.assertEqual(resp.status_code, 200, resp.text)
        config = asyncio.run(_run("SELECT config FROM users WHERE uid = $1", TARGET_UID))[0]["config"]
        self.assertEqual(config["scanConfig"], {"frequency": 15, "max_listings": 5})

    def test_set_scan_frequency_rejects_zero(self):
        self.assertEqual(self.client.patch(f"/admin/users/{TARGET_UID}/scan-frequency", json={"minutes": 0}).status_code, 422)

    def test_delete_user_refused_while_scanning_then_allowed(self):
        asyncio.run(_run("UPDATE users SET bot_status = 'scanning' WHERE uid = $1", TARGET_UID))
        self.assertEqual(self.client.delete(f"/admin/users/{TARGET_UID}").status_code, 409)

        asyncio.run(_run("UPDATE users SET bot_status = 'paused' WHERE uid = $1", TARGET_UID))
        self.assertEqual(self.client.delete(f"/admin/users/{TARGET_UID}").status_code, 204)
        self.assertEqual(asyncio.run(_run("SELECT uid FROM users WHERE uid = $1", TARGET_UID)), [])

    def test_admin_cannot_delete_self(self):
        self.assertEqual(self.client.delete(f"/admin/users/{ADMIN_UID}").status_code, 409)

    def test_unknown_user_returns_404(self):
        self.assertEqual(self.client.post("/admin/users/inconnu/pause").status_code, 404)

    def test_admin_routes_reject_non_admin(self):
        """Sans l'override : pas de jeton -> 401/422 (en-tête requis), jamais d'accès."""
        app.dependency_overrides.pop(get_admin_uid, None)
        resp = self.client.get("/admin/users")
        self.assertIn(resp.status_code, (401, 422))


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestEnsureUser(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[get_current_uid] = lambda: NEW_UID
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        asyncio.run(_cleanup())

    def test_post_users_me_creates_once_and_is_idempotent(self):
        first = self.client.post("/users/me")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["created"])
        asyncio.run(_run("UPDATE users SET config = $2 WHERE uid = $1", NEW_UID, {"scanConfig": {"frequency": 30}}))

        second = self.client.post("/users/me")
        self.assertFalse(second.json()["created"])
        config = asyncio.run(_run("SELECT config FROM users WHERE uid = $1", NEW_UID))[0]["config"]
        self.assertEqual(config["scanConfig"]["frequency"], 30)  # config existante jamais écrasée


if __name__ == "__main__":
    unittest.main()
