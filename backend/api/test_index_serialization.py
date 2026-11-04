"""Garde-fous perf de l'API (2026-11-03) : sérialisation des listes d'annonces, boucle d'événements, WebSocket.

Sans Postgres : `encode_rows_json` ne reçoit que des lignes (dict), les routes sont appelées via TestClient avec
`deals_repo`/`get_pool` simulés, `get_current_uid` directement. Lancer : python -m unittest backend.api.test_index_serialization
"""
import asyncio
import datetime as dt
import decimal
import gzip
import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.encoders import jsonable_encoder

from fastapi.testclient import TestClient
from uvicorn.protocols.utils import ClientDisconnected

from backend.api import auth, main


def _rows():
    tz = dt.timezone.utc
    return [
        {"id": "1", "price": decimal.Decimal("123.50"), "timestamp": dt.datetime(2026, 11, 3, 12, 0, 1, 250000, tzinfo=tz),
         "ai_analysis": {"verdict": "GOOD_DEAL", "scores": [1, 2.5, None]}, "storage_image_urls": ["https://x/é.jpg"], "is_favorite": False},
        {"id": "2", "price": None, "timestamp": dt.datetime(2026, 1, 1, 0, 0, 0, tzinfo=tz), "ai_analysis": None,
         "storage_image_urls": [], "is_favorite": True},
    ]


class IndexBodyTests(unittest.TestCase):
    def test_parite_avec_jsonable_encoder(self):
        body, gz, raw_len = main.encode_rows_json(_rows(), accept_gzip=False)
        self.assertFalse(gz)
        self.assertEqual(raw_len, len(body))
        self.assertEqual(json.loads(body), json.loads(json.dumps(jsonable_encoder(_rows()))))

    def test_colonnaire_reconstruit_les_memes_lignes(self):
        """`?format=columnar` : mêmes valeurs que la forme objets, sans répéter les noms de clés."""
        body, _, raw_len = main.encode_rows_json(_rows(), accept_gzip=False, columnar=True)
        payload = json.loads(body)
        self.assertEqual(set(payload), {"cols", "rows"})
        rebuilt = [dict(zip(payload["cols"], values)) for values in payload["rows"]]
        self.assertEqual(rebuilt, json.loads(json.dumps(jsonable_encoder(_rows()))))
        self.assertLess(raw_len, len(main.encode_rows_json(_rows(), accept_gzip=False)[0]) + 1)

    def test_colonnaire_liste_vide(self):
        body, _, _ = main.encode_rows_json([], accept_gzip=False, columnar=True)
        self.assertEqual(json.loads(body), {"cols": [], "rows": []})

    def test_repli_sans_orjson_identique(self):
        with patch.object(main, "orjson", None):
            body, _, _ = main.encode_rows_json(_rows(), accept_gzip=False)
        self.assertEqual(json.loads(body), json.loads(json.dumps(jsonable_encoder(_rows()))))

    def test_gzip_seulement_si_accepte(self):
        raw, gz_raw, raw_len = main.encode_rows_json(_rows(), accept_gzip=False)
        packed, gz_packed, packed_raw_len = main.encode_rows_json(_rows(), accept_gzip=True)
        self.assertEqual(raw_len, packed_raw_len)
        self.assertFalse(gz_raw)
        self.assertTrue(gz_packed)
        self.assertEqual(gzip.decompress(packed), raw)

    def test_valeur_refusee_par_orjson_repli_au_lieu_de_500(self):
        """orjson est strict : une clé non-str le fait échouer ; jsonable_encoder la tolère (clé -> str)."""
        rows = [{"id": "1", "ai_analysis": {1: "clé entière"}}]
        body, _, _ = main.encode_rows_json(rows, accept_gzip=False)
        self.assertEqual(json.loads(body), [{"id": "1", "ai_analysis": {"1": "clé entière"}}])


class DealsRoutesTests(unittest.TestCase):
    """Réponse réelle des routes : en-têtes, pas de double gzip avec GZipMiddleware, jsonable côté client."""

    def setUp(self):
        main.app.dependency_overrides[auth.get_current_uid] = lambda: "uid-1"
        main.app.dependency_overrides[main.get_current_uid] = lambda: "uid-1"
        self.client = TestClient(main.app)  # sans `with` : pas de lifespan, donc pas de pool Postgres
        self.pool_patch = patch.object(main, "get_pool", return_value=object())
        self.pool_patch.start()

    def tearDown(self):
        self.pool_patch.stop()
        main.app.dependency_overrides.clear()

    def test_index_gzip_une_seule_fois(self):
        with patch.object(main.deals_repo, "list_deals_index", AsyncMock(return_value=_rows() * 400)):
            resp = self.client.get("/deals/index", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-encoding"], "gzip")
        self.assertIn("Accept-Encoding", resp.headers["vary"])  # CORS peut y ajouter Origin
        self.assertEqual(len(resp.json()), 800)  # un double gzip rendrait un corps illisible

    def test_index_format_colonnaire_route(self):
        with patch.object(main.deals_repo, "list_deals_index", AsyncMock(return_value=_rows())):
            resp = self.client.get("/deals/index?format=columnar", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual([r[payload["cols"].index("id")] for r in payload["rows"]], ["1", "2"])

    def test_index_sans_accept_encoding_reste_en_clair(self):
        with patch.object(main.deals_repo, "list_deals_index", AsyncMock(return_value=_rows())):
            resp = self.client.get("/deals/index", headers={"Accept-Encoding": "identity"})
        self.assertNotIn("content-encoding", resp.headers)
        self.assertEqual([d["id"] for d in resp.json()], ["1", "2"])

    def test_by_ids_et_liste_complete_passent_par_le_meme_chemin(self):
        with patch.object(main.deals_repo, "get_deals_by_ids", AsyncMock(return_value=_rows())):
            resp = self.client.post("/deals/by-ids", json={"ids": ["1", "2"]}, headers={"Accept-Encoding": "gzip"})
        self.assertEqual(resp.headers["content-encoding"], "gzip")
        self.assertEqual(len(resp.json()), 2)
        with patch.object(main.deals_repo, "list_deals", AsyncMock(return_value=_rows())):
            resp = self.client.get("/deals", headers={"Accept-Encoding": "identity"})
        self.assertEqual(len(resp.json()), 2)

    def test_index_incremental_transmet_les_ids(self):
        mock = AsyncMock(return_value=_rows()[:1])
        with patch.object(main.deals_repo, "list_deals_index", mock):
            resp = self.client.get("/deals/index", params={"ids": " 1, 2 ,,3"}, headers={"Accept-Encoding": "identity"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(mock.await_args.kwargs["ids"], ["1", "2", "3"])
        with patch.object(main.deals_repo, "list_deals_index", mock):
            self.client.get("/deals/index")
        self.assertIsNone(mock.await_args.kwargs["ids"])  # sans ?ids= : lecture complète comme avant

    def test_index_incremental_refuse_trop_d_ids(self):
        ids = ",".join(str(i) for i in range(main._INDEX_IDS_MAX + 1))
        with patch.object(main.deals_repo, "list_deals_index", AsyncMock(return_value=[])) as mock:
            resp = self.client.get("/deals/index", params={"ids": ids})
        self.assertEqual(resp.status_code, 400)
        mock.assert_not_awaited()

    def test_perf_mesure_le_meme_chemin(self):
        with patch.object(main.deals_repo, "list_deals_index", AsyncMock(return_value=_rows())),              patch.object(main, "is_admin_uid", return_value=True):
            resp = self.client.get("/deals/index", params={"perf": 1}, headers={"Accept-Encoding": "gzip"})
        self.assertEqual(resp.headers["content-encoding"], "gzip")
        self.assertIn("ser;dur=", resp.headers["server-timing"])
        self.assertIn('rows;desc="2"', resp.headers["server-timing"])


class IndexQueryTests(unittest.TestCase):
    def test_filtre_ids_garde_la_jointure_de_visibilite(self):
        """Un id notifié mais non visible pour l'utilisateur ne doit pas sortir : la jointure `user_deal_matches` reste."""
        from backend.api import deals_repo
        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])
        asyncio.run(deals_repo.list_deals_index(pool, "uid-1", ids=["a", "b"]))
        query, *params = pool.fetch.await_args.args
        self.assertIn("JOIN user_deal_matches udm", query)
        self.assertIn("gd.id = ANY($2::text[])", query)
        self.assertEqual(params, ["uid-1", ["a", "b"]])
        asyncio.run(deals_repo.list_deals_index(pool, "uid-1"))
        self.assertNotIn("ANY(", pool.fetch.await_args.args[0])


class WebSocketDisconnectTests(unittest.TestCase):
    def test_client_parti_pendant_ready_ne_leve_pas_et_libere_la_connexion(self):
        """uvicorn lève ClientDisconnected (OSError) si le téléphone coupe pendant l'envoi : avant, trace d'erreur."""
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.send_json = AsyncMock(side_effect=ClientDisconnected())
        conn = MagicMock()
        conn.add_listener = AsyncMock()
        conn.remove_listener = AsyncMock()
        conn.close = AsyncMock()
        with patch.object(main, "verify_token", return_value="uid-1"),              patch.object(main.asyncpg, "connect", AsyncMock(return_value=conn)):
            asyncio.run(main.ws_user_config(ws, token="t"))  # ne doit pas lever
        conn.close.assert_awaited_once()  # connexion LISTEN libérée (pas de fuite)


class EventLoopTests(unittest.TestCase):
    def test_verify_token_lent_ne_bloque_pas_la_boucle(self):
        """Avant : `verify_token` (synchrone) tournait sur la boucle et figeait toute l'API."""
        def slow_verify(_token):
            time.sleep(0.6)
            return "uid-1"

        async def scenario():
            worst = 0.0
            async def ticker():
                nonlocal worst
                last = time.perf_counter()
                for _ in range(20):
                    await asyncio.sleep(0.02)
                    now = time.perf_counter()
                    worst = max(worst, now - last - 0.02)
                    last = now
            with patch.object(auth, "verify_token", slow_verify):
                uid, _ = await asyncio.gather(auth.get_current_uid("Bearer abc"), ticker())
            return uid, worst

        uid, worst = asyncio.run(scenario())
        self.assertEqual(uid, "uid-1")
        self.assertLess(worst, 0.25, f"boucle bloquée {worst:.2f}s")


if __name__ == "__main__":
    unittest.main()
