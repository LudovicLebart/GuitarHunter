"""Tests d'intégration de l'API des fiches techniques de restauration (lot C) : vraie base Postgres, se saute proprement
si injoignable (même principe que test_restoration_api.py). Les fiches sont insérées directement en SQL, sans passer
par le chargeur, pour tester l'API seule."""
import asyncio
import unittest

import asyncpg
from fastapi.testclient import TestClient

from backend import guitar_knowledge as gk
from backend.api import fiches_repo
from backend.api.auth import get_current_uid
from backend.api.db import DATABASE_URL
from backend.api.main import app
from backend.api.test_deals_api import _pg_reachable

BUYER = "test-uid-fiches-buyer"
VIEWER = "test-uid-fiches-viewer"
STRANGER = "test-uid-fiches-stranger"
DEAL = "fiches-deal-1"
FICHES = ("fiche:api-truss", "fiche:api-action", "fiche:api-neck")
BRAND = "manual:api-gibson"


async def _seed():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        for uid in (BUYER, VIEWER, STRANGER):
            await conn.execute("INSERT INTO users (uid) VALUES ($1) ON CONFLICT DO NOTHING", uid)
        await conn.execute(
            """INSERT INTO guitar_deals (id, title, description, is_purchased, purchased_by_user_id)
               VALUES ($1, 'Gibson Les Paul 1975', 'Belle guitare, le manche demande un neck reset un jour', true, $2)
               ON CONFLICT (id) DO NOTHING""", DEAL, BUYER)
        for uid in (BUYER, VIEWER):
            await conn.execute("INSERT INTO user_deal_matches (user_id, deal_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", uid, DEAL)
        await conn.execute(
            """INSERT INTO guitar_knowledge (id, kind, name, relevance, source, kb_version, curated)
               VALUES ($1, 'brand', 'Gibson', 'guitars', 'manual', 1, true) ON CONFLICT (id) DO NOTHING""", BRAND)
        await conn.execute("INSERT INTO guitar_knowledge_alias VALUES ('gibson', $1, 'Gibson', 'manual') ON CONFLICT DO NOTHING", BRAND)
        rows = [
            ("fiche:api-truss", "Ajuster le truss rod", "reglage", "sourced", ["truss rod coince", "ajuster le truss rod"]),
            ("fiche:api-action", "Ajuster l'action", "reglage", "single_source", ["action haute", "ajuster l action"]),
            ("fiche:api-neck", "Neck reset", "structurel", "sourced", ["neck reset"]),
        ]
        for kid, name, categorie, confidence, aliases in rows:
            await conn.execute(
                """INSERT INTO guitar_knowledge (id, kind, name, description, relevance, source, kb_version, curated, confidence)
                   VALUES ($1, 'fiche', $2, 'Résumé de ' || $2, 'guitars', 'manual', 0, true, $3) ON CONFLICT (id) DO NOTHING""",
                kid, name, confidence)
            await conn.execute(
                """INSERT INTO guitar_knowledge_fiche (knowledge_id, body_md, categorie, difficulte, duree, statut, revision, content_hash)
                   VALUES ($1, '# ' || $2, $3, 2, '30 min', 'brouillon', '2026-10-15', 'h') ON CONFLICT (knowledge_id) DO NOTHING""",
                kid, name, categorie)
            for alias in aliases:
                await conn.execute("INSERT INTO guitar_knowledge_alias VALUES ($1, $2, $1, 'fiche') ON CONFLICT DO NOTHING", alias, kid)
            await conn.execute(
                """INSERT INTO guitar_knowledge_source (knowledge_id, url, kind, publisher, excerpt, origin)
                   VALUES ($1, 'https://stewmac.com/' || $1, 'other', 'StewMac', '[résumé] x', 'fiche') ON CONFLICT DO NOTHING""", kid)
        await conn.execute("INSERT INTO guitar_knowledge_link (from_id, to_id, rel, origin) VALUES ($1, 'fiche:api-neck', 'fiche_pour', 'fiche') "
                           "ON CONFLICT DO NOTHING", BRAND)
    finally:
        await conn.close()


async def _cleanup():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DELETE FROM restoration_plan_items WHERE deal_id = $1", DEAL)
        await conn.execute("DELETE FROM user_deal_matches WHERE deal_id = $1", DEAL)
        await conn.execute("DELETE FROM guitar_deals WHERE id = $1", DEAL)
        await conn.execute("DELETE FROM guitar_knowledge WHERE id = ANY($1::text[])", [*FICHES, BRAND])
        await conn.execute("DELETE FROM users WHERE uid = ANY($1::text[])", [BUYER, VIEWER, STRANGER])
    finally:
        await conn.close()


class _FichesBase(unittest.TestCase):
    """Base (sans test) : base seedée, client authentifié comme `self.uid`."""
    uid = BUYER

    def setUp(self):
        app.dependency_overrides[get_current_uid] = lambda: self.uid
        self.client = TestClient(app)
        self.client.__enter__()
        asyncio.run(_cleanup())
        asyncio.run(_seed())
        fiches_repo.invalidate_cache()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        asyncio.run(_cleanup())
        fiches_repo.invalidate_cache()


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestFichesAPI(_FichesBase):
    """L'acheteur de l'annonce."""

    # --- catalogue -------------------------------------------------------------------------------
    def test_list_returns_only_fiches_never_brands(self):
        resp = self.client.get("/fiches")
        self.assertEqual(resp.status_code, 200, resp.text)
        slugs = {f["slug"] for f in resp.json()}
        self.assertEqual(slugs, {"api-truss", "api-action", "api-neck"})
        first = next(f for f in resp.json() if f["slug"] == "api-truss")
        self.assertEqual((first["titre"], first["categorie"], first["statut"], first["confidence"]),
                         ("Ajuster le truss rod", "reglage", "brouillon", "sourced"))
        self.assertNotIn("body_md", first)

    def test_list_filters_by_category(self):
        slugs = {f["slug"] for f in self.client.get("/fiches", params={"categorie": "structurel"}).json()}
        self.assertEqual(slugs, {"api-neck"})

    def test_get_one_returns_body_sources_and_brands(self):
        resp = self.client.get("/fiches/api-neck")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["body_md"], "# Neck reset")
        self.assertEqual(body["sources"][0]["publisher"], "StewMac")
        self.assertEqual([c["name"] for c in body["concerne"]], ["Gibson"])

    def test_unknown_invalid_or_brand_slugs_are_404(self):
        for slug in ("inconnue", "API-TRUSS", "..%2Fx", "manual:api-gibson", "api-gibson"):
            self.assertEqual(self.client.get(f"/fiches/{slug}").status_code, 404, slug)

    def test_authentication_is_required(self):
        app.dependency_overrides.clear()
        self.assertIn(self.client.get("/fiches").status_code, (401, 422))

    # --- lien étape → fiche ----------------------------------------------------------------------
    def test_a_step_can_link_to_a_fiche_and_unlink(self):
        created = self.client.post(f"/deals/{DEAL}/restoration-plan", json={"label": "Régler le manche", "ficheSlug": "api-truss"})
        self.assertEqual(created.status_code, 201, created.text)
        item = self.client.get(f"/deals/{DEAL}/restoration-plan").json()[0]
        self.assertEqual(item["fiche_slug"], "api-truss")
        self.assertEqual(self.client.patch(f"/deals/{DEAL}/restoration-plan/{item['id']}", json={"ficheSlug": "api-action"}).status_code, 200)
        self.assertEqual(self.client.get(f"/deals/{DEAL}/restoration-plan").json()[0]["fiche_slug"], "api-action")
        self.assertEqual(self.client.patch(f"/deals/{DEAL}/restoration-plan/{item['id']}", json={"ficheSlug": None}).status_code, 200)
        self.assertIsNone(self.client.get(f"/deals/{DEAL}/restoration-plan").json()[0]["fiche_slug"])

    def test_an_unknown_fiche_slug_is_refused_on_create_and_patch(self):
        self.assertEqual(self.client.post(f"/deals/{DEAL}/restoration-plan", json={"label": "x", "ficheSlug": "inconnue"}).status_code, 422)
        item_id = self.client.post(f"/deals/{DEAL}/restoration-plan", json={"label": "x"}).json()["id"]
        self.assertEqual(self.client.patch(f"/deals/{DEAL}/restoration-plan/{item_id}", json={"ficheSlug": "inconnue"}).status_code, 422)
        # une marque n'est pas une fiche : son slug n'est jamais accepté
        self.assertEqual(self.client.patch(f"/deals/{DEAL}/restoration-plan/{item_id}", json={"ficheSlug": "api-gibson"}).status_code, 422)
        self.assertIsNone(self.client.get(f"/deals/{DEAL}/restoration-plan").json()[0]["fiche_slug"])

    def test_patching_another_field_leaves_the_fiche_link_alone(self):
        item_id = self.client.post(f"/deals/{DEAL}/restoration-plan", json={"label": "x", "ficheSlug": "api-truss"}).json()["id"]
        self.client.patch(f"/deals/{DEAL}/restoration-plan/{item_id}", json={"notes": "n"})
        self.assertEqual(self.client.get(f"/deals/{DEAL}/restoration-plan").json()[0]["fiche_slug"], "api-truss")

    # --- fiches d'une annonce --------------------------------------------------------------------
    def test_deal_fiches_put_linked_steps_first_then_text_matches(self):
        self.client.post(f"/deals/{DEAL}/restoration-plan", json={"label": "Régler le manche", "ficheSlug": "api-action"})
        resp = self.client.get(f"/deals/{DEAL}/fiches", params={"q": "mon truss rod coincé, que faire ?"})
        self.assertEqual(resp.status_code, 200, resp.text)
        found = [(f["slug"], f["reason"], f["matchedOn"]) for f in resp.json()]
        self.assertEqual(found[0], ("api-action", "etape", None))
        self.assertIn(("api-truss", "texte", "truss rod coince"), found)
        # le texte de l'annonce (« neck reset » dans la description) compte aussi
        self.assertIn("api-neck", [f[0] for f in found])

    def test_deal_fiches_never_return_a_brand_and_respect_limit(self):
        resp = self.client.get(f"/deals/{DEAL}/fiches", params={"q": "gibson truss rod coincé action haute", "limit": 1})
        self.assertEqual(len(resp.json()), 1)
        everything = self.client.get(f"/deals/{DEAL}/fiches", params={"q": "gibson truss rod coincé action haute", "limit": 20}).json()
        self.assertNotIn("api-gibson", [f["slug"] for f in everything])
        self.assertTrue(all(f["slug"].startswith("api-") for f in everything))

    def test_a_removed_fiche_linked_to_a_step_is_ignored(self):
        self.client.post(f"/deals/{DEAL}/restoration-plan", json={"label": "x", "ficheSlug": "api-action"})
        async def drop():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("DELETE FROM guitar_knowledge WHERE id = 'fiche:api-action'")
            finally:
                await conn.close()
        asyncio.run(drop())
        fiches_repo.invalidate_cache()
        slugs = [f["slug"] for f in self.client.get(f"/deals/{DEAL}/fiches").json()]
        self.assertNotIn("api-action", slugs)

    def test_a_stranger_cannot_read_the_fiches_of_a_deal(self):
        self.uid = STRANGER
        self.assertEqual(self.client.get(f"/deals/{DEAL}/fiches").status_code, 404)


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestFichesAPIAsViewer(_FichesBase):
    """Une personne qui VOIT l'annonce sans l'avoir achetée : elle reçoit les fiches reconnues dans le texte, mais ni les
    étapes ni les libellés du plan, qui appartiennent à l'acheteur."""
    uid = VIEWER

    def test_viewer_gets_text_matches_but_not_the_buyers_steps(self):
        async def add_step():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("INSERT INTO restoration_plan_items (deal_id, label, fiche_slug) VALUES ($1, 'Régler le manche', 'api-action')", DEAL)
            finally:
                await conn.close()
        asyncio.run(add_step())
        found = self.client.get(f"/deals/{DEAL}/fiches", params={"q": "truss rod coincé"}).json()
        slugs = [f["slug"] for f in found]
        self.assertIn("api-truss", slugs)
        self.assertNotIn("api-action", slugs)
        self.assertTrue(all(f["reason"] == "texte" for f in found))


class TestFicheIdHelpers(unittest.TestCase):
    def test_id_and_slug_round_trip_and_slug_validation(self):
        self.assertEqual(gk.fiche_id("reglage-action"), "fiche:reglage-action")
        self.assertEqual(gk.fiche_slug("fiche:reglage-action"), "reglage-action")
        for bad in ("", "A", "a b", "../x", "a" * 81, None, 3):
            self.assertFalse(fiches_repo.valid_slug(bad), repr(bad))
        self.assertTrue(fiches_repo.valid_slug("neck-reset-2"))


if __name__ == "__main__":
    unittest.main()
