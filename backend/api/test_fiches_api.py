"""Tests d'intégration de l'API des fiches techniques de restauration (lot C) : vraie base Postgres, se saute proprement
si injoignable (même principe que test_restoration_api.py). Les fiches sont insérées directement en SQL, sans passer
par le chargeur, pour tester l'API seule."""
import asyncio
import time
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
FICHES = ("fiche:api-truss", "fiche:api-action", "fiche:api-neck", "fiche:api-extra")
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

    finally:
        await conn.close()


async def _cleanup():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DELETE FROM restoration_plan_items WHERE deal_id = $1", DEAL)
        await conn.execute("DELETE FROM user_deal_matches WHERE deal_id = $1", DEAL)
        await conn.execute("DELETE FROM guitar_deals WHERE id = $1", DEAL)
        # TOUTES les fiches (pas seulement les nôtres) : d'autres tests de la base de connaissances laissent les leurs dans la même
        # base jetable, et ces tests-ci supposent un catalogue de fiches maîtrisé (ordre d'exécution indifférent).
        await conn.execute("DELETE FROM guitar_knowledge WHERE kind = 'fiche' OR id = ANY($1::text[])", [*FICHES, BRAND])
        await conn.execute("DELETE FROM users WHERE uid = ANY($1::text[])", [BUYER, VIEWER, STRANGER])
    finally:
        await conn.close()


class _FichesBase(unittest.TestCase):
    """Base (sans test) : base seedée, client authentifié comme `self.uid`."""
    uid = BUYER

    def _search(self, body):
        """Recherche de fiches pour l'annonce de test : la question part dans le CORPS d'un POST."""
        return self.client.post(f"/deals/{DEAL}/fiches/search", json=body)

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

    def test_get_one_returns_body_and_sources(self):
        resp = self.client.get("/fiches/api-neck")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["body_md"], "# Neck reset")
        self.assertEqual(body["sources"][0]["publisher"], "StewMac")
        self.assertNotIn("concerne", body)

    def test_unknown_invalid_or_brand_slugs_are_404(self):
        for slug in ("inconnue", "API-TRUSS", "..%2Fx", "manual:api-gibson", "api-gibson", "api-truss%0A", "api_truss"):
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

    def test_a_dead_fiche_link_is_not_returned_in_the_plan(self):
        item_id = self.client.post(f"/deals/{DEAL}/restoration-plan", json={"label": "x", "ficheSlug": "api-action"}).json()["id"]
        async def drop():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("DELETE FROM guitar_knowledge WHERE id = 'fiche:api-action'")
            finally:
                await conn.close()
        asyncio.run(drop())
        item = self.client.get(f"/deals/{DEAL}/restoration-plan").json()[0]
        self.assertEqual(item["id"], item_id)
        self.assertIsNone(item["fiche_slug"])

    def test_patching_a_missing_step_is_404_even_with_an_unknown_fiche(self):
        resp = self.client.patch(f"/deals/{DEAL}/restoration-plan/999999999", json={"ficheSlug": "inconnue"})
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_patching_another_field_leaves_the_fiche_link_alone(self):
        item_id = self.client.post(f"/deals/{DEAL}/restoration-plan", json={"label": "x", "ficheSlug": "api-truss"}).json()["id"]
        self.client.patch(f"/deals/{DEAL}/restoration-plan/{item_id}", json={"notes": "n"})
        self.assertEqual(self.client.get(f"/deals/{DEAL}/restoration-plan").json()[0]["fiche_slug"], "api-truss")

    # --- fiches d'une annonce --------------------------------------------------------------------
    def test_deal_fiches_are_ranked_question_then_step_link_then_listing(self):
        self.client.post(f"/deals/{DEAL}/restoration-plan", json={"label": "Régler le manche", "ficheSlug": "api-action"})
        resp = self._search({"q": "mon truss rod coincé, que faire ?"})
        self.assertEqual(resp.status_code, 200, resp.text)
        found = [(f["slug"], f["reason"], f["matchedOn"]) for f in resp.json()]
        self.assertEqual(found, [("api-truss", "question", "truss rod coince"),
                                 ("api-action", "etape", None),
                                 # « neck reset » figure dans la description de l'annonce
                                 ("api-neck", "annonce", "neck reset")])

    def test_the_current_question_is_never_crowded_out_by_step_links(self):
        self.client.post(f"/deals/{DEAL}/restoration-plan", json={"label": "a", "ficheSlug": "api-action"})
        self.client.post(f"/deals/{DEAL}/restoration-plan", json={"label": "b", "ficheSlug": "api-neck"})
        only = self._search({"q": "truss rod coincé", "limit": 1}).json()
        self.assertEqual([f["slug"] for f in only], ["api-truss"])

    def test_every_fiche_exposes_its_status_and_confidence(self):
        """Les brouillons sont servis (décision produit) : le client doit pouvoir les signaler."""
        for f in self.client.get("/fiches").json() + self._search({"q": "action haute"}).json():
            self.assertIn(f["statut"], ("brouillon", "en_revision", "validee"))
            self.assertIn(f["confidence"], ("sourced", "single_source"))
        self.assertEqual(self.client.get("/fiches/api-action").json()["statut"], "brouillon")

    def test_a_stale_alias_index_never_crowds_out_a_valid_fiche(self):
        params = {"q": "action haute et truss rod coincé", "limit": 1}
        self.assertEqual(self._search(params).json()[0]["slug"], "api-truss")   # réchauffe l'index
        async def drop():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("DELETE FROM guitar_knowledge WHERE id = 'fiche:api-truss'")      # sans invalider le cache
            finally:
                await conn.close()
        asyncio.run(drop())
        found = self._search(params).json()
        self.assertEqual([f["slug"] for f in found], ["api-action"])

    def test_the_alias_index_sees_a_new_fiche_without_a_restart(self):
        self._search({"q": "micro bourdonne"})                      # réchauffe l'index
        async def add():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("""INSERT INTO guitar_knowledge (id, kind, name, relevance, source, kb_version, curated)
                                      VALUES ('fiche:api-extra', 'fiche', 'Micro qui bourdonne', 'guitars', 'manual', 0, true)""")
                await conn.execute("""INSERT INTO guitar_knowledge_fiche (knowledge_id, body_md, categorie, statut, revision, content_hash)
                                      VALUES ('fiche:api-extra', '# x', 'electronique', 'brouillon', '2026-10-15', 'h')""")
                await conn.execute("INSERT INTO guitar_knowledge_alias VALUES ('micro bourdonne', 'fiche:api-extra', 'x', 'fiche')")
            finally:
                await conn.close()
        asyncio.run(add())
        fiches_repo._index["at"] = time.monotonic() - 3600        # la fenêtre de vérification est écoulée
        slugs = [f["slug"] for f in self._search({"q": "mon micro bourdonne"}).json()]
        self.assertIn("api-extra", slugs)

    def test_deal_fiches_never_return_a_brand_and_respect_limit(self):
        resp = self._search({"q": "gibson truss rod coincé action haute", "limit": 1})
        self.assertEqual(len(resp.json()), 1)
        everything = self._search({"q": "gibson truss rod coincé action haute", "limit": 20}).json()
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
        slugs = [f["slug"] for f in self._search({}).json()]
        self.assertNotIn("api-action", slugs)

    def test_the_question_travels_in_the_body_never_in_the_url(self):
        """L'ancienne route GET (`?q=…`) n'existe plus : la question ne peut plus finir dans les journaux d'accès."""
        self.assertEqual(self.client.get(f"/deals/{DEAL}/fiches", params={"q": "ma question"}).status_code, 404)   # route retirée
        self.assertEqual(self.client.get(f"/deals/{DEAL}/fiches/search", params={"q": "ma question"}).status_code, 405)
        ok = self._search({"q": "truss rod coincé"})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertNotIn("truss", str(ok.request.url))                  # la question n'est pas dans l'URL de la requête envoyée

    def test_search_validates_the_body(self):
        self.assertEqual(self._search({"q": "x" * 2001}).status_code, 422)
        self.assertEqual(self._search({"limit": 0}).status_code, 422)
        self.assertEqual(self._search({"limit": 21}).status_code, 422)
        self.assertEqual(self._search({"q": None}).status_code, 200)
        self.assertEqual(self._search({}).status_code, 200)

    def test_a_stranger_cannot_read_the_fiches_of_a_deal(self):
        self.uid = STRANGER
        self.assertEqual(self._search({}).status_code, 404)


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
        found = self._search({"q": "truss rod coincé"}).json()
        slugs = [f["slug"] for f in found]
        self.assertIn("api-truss", slugs)
        self.assertNotIn("api-action", slugs)
        self.assertTrue(all(f["reason"] in ("question", "annonce") for f in found))


class TestFicheIdHelpers(unittest.TestCase):
    def test_id_and_slug_round_trip(self):
        self.assertEqual(gk.fiche_id("reglage-action"), "fiche:reglage-action")
        self.assertEqual(gk.fiche_slug("fiche:reglage-action"), "reglage-action")

    def test_fiche_slug_refuses_an_id_that_is_not_a_fiche(self):
        for bad in ("manual:gibson", "wd:Q123", "", "fiche"):
            with self.assertRaises(ValueError, msg=bad):
                gk.fiche_slug(bad)

    def test_slug_format_is_one_strict_rule(self):
        for bad in ("", "A", "a b", "../x", "a" * 81, None, 3, "abc\n", "reglage_action", "truss-1.2", "réglage", "-x"):
            self.assertFalse(gk.valid_fiche_slug(bad), repr(bad))
        for good in ("neck-reset-2", "a", "a" * 80, "0-9"):
            self.assertTrue(gk.valid_fiche_slug(good), good)
        self.assertIs(fiches_repo.valid_slug, gk.valid_fiche_slug)


if __name__ == "__main__":
    unittest.main()
