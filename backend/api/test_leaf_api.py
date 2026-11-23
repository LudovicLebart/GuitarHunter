"""API Leaf Hunter (`/leaf/*`) : vraie base Postgres, se saute si injoignable. Données INVENTÉES (dépôt public)."""
import asyncio
import json
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

    # --- réglages de recherche -------------------------------------------------------------------
    BODY = {"enabled": True, "scan": {"frequency": 180, "min_price": 2000, "max_price": 6500, "max_km": 130000, "pages": 2,
                                      "years": [2017, 2018], "sources": ["kijiji"], "read_details": True,
                                      "home": {"latitude": 45.6, "longitude": -73.4, "name": "Ville-Test"}, "radius_km": 90},
            "notify": {"enabled": True, "new": False, "price_drop": True}}

    def test_config_defaults_then_save_and_read_back(self):
        c = self.client.get("/leaf/config").json()
        self.assertEqual((c["enabled"], c["scan"]["max_price"], c["scan"]["home"]["name"]), (False, 7500, "Saint-Bruno-de-Montarville"))
        r = self.client.put("/leaf/config", json=self.BODY)
        self.assertEqual(r.status_code, 200, r.text)
        c = self.client.get("/leaf/config").json()
        self.assertEqual((c["enabled"], c["scan"]["max_price"], c["scan"]["years"], c["scan"]["sources"], c["scan"]["radius_km"],
                          c["notify"]["new"]), (True, 6500, [2017, 2018], ["kijiji"], 90, False))

    def test_config_is_stored_in_the_shape_the_bot_reads_and_keeps_other_keys(self):
        async def seed_extra():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("UPDATE users SET config = '{\"leafConfig\": {\"autreCle\": {\"x\": 1}}, \"scanConfig\": {\"keep\": true}}' "
                                   "WHERE uid = $1", ME)
            finally:
                await conn.close()

        async def read():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                return await conn.fetchval("SELECT config::text FROM users WHERE uid = $1", ME)
            finally:
                await conn.close()
        asyncio.run(seed_extra())
        self.assertEqual(self.client.put("/leaf/config", json=self.BODY).status_code, 200)
        import json as _json
        stored = _json.loads(asyncio.run(read()))
        self.assertEqual(stored["leafConfig"]["scanConfig"]["max_price"], 6500)
        self.assertEqual(stored["leafConfig"]["autreCle"], {"x": 1})            # clé voisine de leafConfig conservée
        self.assertEqual(stored["scanConfig"], {"keep": True})                  # configuration des guitares intacte

    def test_config_out_of_bounds_is_refused(self):
        def put(**scan):
            return self.client.put("/leaf/config", json={"scan": {**self.BODY["scan"], **scan}}).status_code
        self.assertEqual(put(frequency=5), 422)
        self.assertEqual(put(pages=9), 422)
        self.assertEqual(put(min_price=9000), 422)                     # max (6500) < min
        self.assertEqual(put(years=[1999]), 422)
        self.assertEqual(put(sources=["carvana"]), 422)
        self.assertEqual(put(sources=[]), 422)
        self.assertEqual(put(home={"latitude": 200, "longitude": 0}), 422)
        self.assertEqual(put(), 200)

    def test_ai_settings_are_off_by_default_validated_and_stored_for_the_bot(self):
        c = self.client.get("/leaf/config").json()
        self.assertEqual(c["analysis"], {"enabled": False, "max_calls_per_day": 30, "max_expert_per_day": 5,
                                       "max_photo_calls_per_day": 20, "providers": ["local", "gemini"]})
        ok = {**self.BODY, "analysis": {"enabled": True, "max_calls_per_day": 12, "max_expert_per_day": 3,
                                        "max_photo_calls_per_day": 9, "providers": ["gemini"]}}
        self.assertEqual(self.client.put("/leaf/config", json=ok).status_code, 200)
        self.assertEqual(self.client.get("/leaf/config").json()["analysis"], ok["analysis"])
        for bad in ({"max_calls_per_day": 0}, {"max_calls_per_day": 501}, {"max_expert_per_day": 0}, {"max_expert_per_day": 51}, {"max_photo_calls_per_day": 0}, {"max_photo_calls_per_day": 201}, {"providers": []}, {"providers": ["gpt"]}):
            self.assertEqual(self.client.put("/leaf/config", json={**self.BODY, "analysis": {"enabled": True, **bad}}).status_code, 422, bad)

        async def read():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                return await conn.fetchval("SELECT config->'leafConfig'->'analysisConfig'->>'max_calls_per_day' FROM users WHERE uid = $1", ME)
            finally:
                await conn.close()
        self.assertEqual(asyncio.run(read()), "12")                      # clé `analysisConfig`, celle que lit le bot

    def test_list_and_detail_expose_verdict_and_ai_analysis(self):
        async def seed():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("UPDATE vehicle_deals SET verdict = 'CANDIDAT_FORT', analysis = $1::text::jsonb WHERE id = 'leaf_api_1'",
                                   json.dumps({"verdict_reasons": ["SOH annoncé 91 %"], "ai": {"summary": "Annonce claire.", "facts": {}, "model": "m", "provider": "local"}}))
            finally:
                await conn.close()
        asyncio.run(seed())
        row = self.client.get("/leaf/deals").json()[0]
        self.assertEqual((row["verdict"], row["analysis"]["verdict_reasons"]), ("CANDIDAT_FORT", ["SOH annoncé 91 %"]))
        self.assertEqual(self.client.get("/leaf/deals/leaf_api_1").json()["analysis"]["ai"]["summary"], "Annonce claire.")

    def test_prompts_default_save_reset_and_survive_a_settings_save(self):
        r = self.client.get("/leaf/prompts").json()
        self.assertEqual(r["prompts"], {"extract": None, "expert": None, "photo": None})
        self.assertIn("Règles strictes", r["defaults"]["extract"])
        self.assertNotIn("Réponds UNIQUEMENT", r["defaults"]["extract"])                   # le contrat JSON n'est pas éditable
        saved = self.client.put("/leaf/prompts", json={"extract": "  Consigne perso  ", "expert": "", "photo": None}).json()
        self.assertEqual(saved["prompts"], {"extract": "Consigne perso", "expert": None, "photo": None})
        self.client.put("/leaf/config", json=self.BODY)                                    # enregistrer les réglages ne doit pas effacer les prompts
        self.assertEqual(self.client.get("/leaf/prompts").json()["prompts"]["extract"], "Consigne perso")
        self.assertEqual(self.client.get("/leaf/config").json()["prompts"]["extract"], "Consigne perso")
        reset = self.client.put("/leaf/prompts", json={}).json()
        self.assertEqual(reset["prompts"], {"extract": None, "expert": None, "photo": None})

    def test_prompts_are_bounded_and_respect_the_allow_list(self):
        self.assertEqual(self.client.put("/leaf/prompts", json={"extract": "x" * 8001}).status_code, 422)
        self.assertEqual(self.client.put("/leaf/prompts", json={"extract": "x" * 8000}).status_code, 200)
        with mock.patch.dict(os.environ, {"LEAF_ALLOWED_UIDS": OTHER}):
            self.assertEqual(self.client.get("/leaf/prompts").status_code, 403)
            self.assertEqual(self.client.put("/leaf/prompts", json={}).status_code, 403)

    def test_leaf_commands_are_accepted_by_the_api_and_the_analyze_payload_is_checked(self):
        # Régression (2026-11-23) : la liste blanche de `input_guard` refusait LEAF_REFRESH, donc « Actualiser » échouait en 422.
        for type_, payload in (("LEAF_REFRESH", None), ("LEAF_CLEANUP", None), ("LEAF_ANALYZE", {"dealId": "leaf_kijiji_123"}),
                               ("LEAF_ANALYZE", {"dealId": "leaf_autohebdo_my-2017_ab12"}), ("LEAF_REANALYZE", {"dealId": "leaf_kijiji_123"}),
                               ("LEAF_REFRESH", {"forceAi": True})):
            r = self.client.post("/commands", json={"type": type_, "payload": payload})
            self.assertEqual(r.status_code, 201, (type_, r.text))
        for bad in (None, {}, {"dealId": 3}, {"dealId": "guitare_1"}, {"dealId": "leaf_x_" + "a" * 200}, "leaf_kijiji_1"):
            for type_ in ("LEAF_ANALYZE", "LEAF_REANALYZE"):
                self.assertEqual(self.client.post("/commands", json={"type": type_, "payload": bad}).status_code, 422, (type_, bad))
        self.assertEqual(self.client.post("/commands", json={"type": "LEAF_REFRESH", "payload": {"forceAi": "oui"}}).status_code, 422)
        asyncio.run(self._clear_commands())

    async def _clear_commands(self):
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute("DELETE FROM commands WHERE user_id = $1", ME)
        finally:
            await conn.close()

    def test_config_respects_the_allow_list(self):
        with mock.patch.dict(os.environ, {"LEAF_ALLOWED_UIDS": OTHER}):
            self.assertEqual(self.client.get("/leaf/config").status_code, 403)
            self.assertEqual(self.client.put("/leaf/config", json=self.BODY).status_code, 403)

    def test_allow_list_blocks_other_accounts(self):
        with mock.patch.dict(os.environ, {"LEAF_ALLOWED_UIDS": OTHER}):
            self.assertEqual(self.client.get("/leaf/deals").status_code, 403)
        with mock.patch.dict(os.environ, {"LEAF_ALLOWED_UIDS": f"{OTHER}, {ME}"}):
            self.assertEqual(self.client.get("/leaf/deals").status_code, 200)


if __name__ == "__main__":
    unittest.main()
