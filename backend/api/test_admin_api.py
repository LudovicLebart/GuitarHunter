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
    await _run("DELETE FROM llm_usage WHERE action = 'chat_cost_test'")
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

    def test_chat_cost_by_model_user_and_alert(self):
        # 1 M tokens d'entrée + 100 k de sortie sur Sonnet = 2 $ + 1 $ = 3 $ → dépasse le seuil de 2 $ du jour.
        asyncio.run(_run(
            "INSERT INTO llm_usage (source, provider, model, action, user_ref, input_tokens, output_tokens) "
            "VALUES ('chat', 'anthropic', 'claude-sonnet-5-5', 'chat_cost_test', $1, 1000000, 100000), "
            "('chat', 'gemini', 'modele-inconnu', 'chat_cost_test', $1, 10, 10)", TARGET_UID))
        resp = self.client.get("/admin/chat-cost?days=7")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        sonnet = next(m for m in body["byModel"] if m["model"] == "claude-sonnet-5-5")
        self.assertGreaterEqual(sonnet["cost"], 3.0)
        self.assertGreaterEqual(body["estimatedCalls"], 1)
        self.assertIn("modele-inconnu", body["unpricedModels"])
        user = next(u for u in body["byUser"] if u["uid"] == TARGET_UID)
        self.assertEqual(user["email"], "cible@example.com")
        self.assertTrue(body["today"]["alert"])
        self.assertEqual(body["today"]["threshold"], 2.0)

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


class _FakePool:
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, *_a):
        return self.rows


class TestCostAlert(unittest.TestCase):
    ROW = {"model": "claude-sonnet-5-5", "input_tokens": 1_000_000, "cached_tokens": 0, "cache_write_tokens": 0,
           "output_tokens": 100_000}  # 3 $ : au-dessus du seuil de 2 $

    def setUp(self):
        from backend.api import cost_alert
        self.cost_alert = cost_alert
        cost_alert._alerted_on = None
        self.sent = []
        self.patches = [patch.object(cost_alert, "_send_ntfy", lambda t, ti, m: self.sent.append((t, ti, m))),
                        patch.dict("os.environ", {"NTFY_TOPIC": "topic-test"})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.cost_alert._alerted_on = None

    def test_alert_sent_once_per_day_when_threshold_exceeded(self):
        pool = _FakePool([self.ROW])
        self.assertTrue(asyncio.run(self.cost_alert.maybe_alert(pool, "2026-11-01")))
        self.assertFalse(asyncio.run(self.cost_alert.maybe_alert(pool, "2026-11-01")))  # déjà prévenu aujourd'hui
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(asyncio.run(self.cost_alert.maybe_alert(pool, "2026-11-02")))  # nouveau jour, nouvelle alerte
        self.assertEqual(len(self.sent), 2)

    def test_no_alert_below_threshold_or_without_topic(self):
        small = dict(self.ROW, input_tokens=1000, output_tokens=100)
        self.assertFalse(asyncio.run(self.cost_alert.maybe_alert(_FakePool([small]), "2026-11-01")))
        with patch.dict("os.environ", {"NTFY_TOPIC": ""}):
            self.assertFalse(asyncio.run(self.cost_alert.maybe_alert(_FakePool([self.ROW]), "2026-11-03")))
        self.assertEqual(self.sent, [])

    def test_unknown_model_counts_at_highest_known_price(self):
        pool = _FakePool([dict(self.ROW, model="gemini-2.5-pro", input_tokens=600_000, output_tokens=0)])  # 2,4 $ au tarif Opus
        self.assertTrue(asyncio.run(self.cost_alert.maybe_alert(pool, "2026-11-04")))


class TestLlmPricing(unittest.TestCase):
    def test_cost_usd_uses_cache_factor_and_ignores_unknown_models(self):
        from backend.api import llm_pricing
        self.assertAlmostEqual(llm_pricing.cost_usd("claude-sonnet-5-5", 1_000_000, 0, 100_000), 3.0)
        # 800 k tokens lus dans le cache à 5 % du prix d'entrée de l'Opus (4 $) : 200 k × 4 + 800 k × 0,2 + 10 k × 20, en millionièmes.
        self.assertAlmostEqual(llm_pricing.cost_usd("claude-opus-5-5", 1_000_000, 800_000, 10_000), 0.8 + 0.16 + 0.2)
        self.assertIsNone(llm_pricing.cost_usd("modele-inconnu", 10, 0, 10))
        # Repli prudent : tarif de l'Opus (le plus haut), jamais 0 $.
        self.assertAlmostEqual(llm_pricing.cost_usd("modele-inconnu", 1_000_000, 0, 0, fallback=True), 4.0)

    def test_cache_write_is_billed_above_input_price(self):
        from backend.api import llm_pricing
        # 1 M tokens d'entrée tous écrits dans le cache (TTL 5 min) sur Sonnet : 2 $ × 1,25 = 2,50 $ (pas 2 $).
        self.assertAlmostEqual(llm_pricing.cost_usd("claude-sonnet-5-5", 1_000_000, 0, 0, cache_write_tokens=1_000_000), 2.5)
        self.assertAlmostEqual(llm_pricing.cost_usd("claude-sonnet-5-5", 1_000_000, 0, 0, cache_write_tokens=1_000_000, cache_ttl="1h"), 4.0)

    def test_provider_of(self):
        from backend.api.usage_repo import provider_of
        self.assertEqual(provider_of("claude-opus-5-5"), "anthropic")
        self.assertEqual(provider_of("gemini-3.1-pro-preview"), "gemini")

