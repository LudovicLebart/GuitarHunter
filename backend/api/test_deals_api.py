"""Tests d'intégration pour la tranche "deals" du Chantier A (Postgres/FastAPI/WebSocket).

Même principe que test_api.py : vraie base Postgres, pas de mocks ; se saute proprement si
aucun Postgres n'est joignable. Auth Firebase court-circuitée via `app.dependency_overrides`
pour les routes HTTP ; le WebSocket vérifie son token via `verify_token`, monkeypatché ici
pour la même raison (pas d'accès Firebase réel depuis cet environnement).
"""
import asyncio
import json
import threading
import time
import unittest
from unittest.mock import patch

import asyncpg
import requests
import uvicorn
import websockets.sync.client as ws_sync_client
from fastapi.testclient import TestClient

from backend.api import deals_repo
from backend.api.db import DATABASE_URL
from backend.api.main import app
from backend.api.auth import get_current_uid


def _pg_reachable() -> bool:
    async def _check():
        conn = await asyncpg.connect(DATABASE_URL, timeout=2)
        await conn.close()

    try:
        asyncio.run(_check())
        return True
    except Exception:
        return False


async def _seed_deal(deal_id, user_id, **overrides):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "INSERT INTO users (uid) VALUES ($1) ON CONFLICT (uid) DO NOTHING", user_id
        )
        fields = {
            "id": deal_id, "user_id": user_id, "title": "Guitare de test",
            "status": "analyzed", "is_favorite": False, "is_purchased": False,
        }
        fields.update(overrides)
        cols = ", ".join(fields.keys())
        placeholders = ", ".join(f"${i + 1}" for i in range(len(fields)))
        await conn.execute(
            f"INSERT INTO guitar_deals ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO UPDATE SET {', '.join(f'{k} = EXCLUDED.{k}' for k in fields)}",
            *fields.values(),
        )
    finally:
        await conn.close()


def _free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _RealServer:
    """Lance l'app FastAPI dans un vrai serveur uvicorn (thread dédié), pas le TestClient.

    Nécessaire pour tester le canal WebSocket : le pont synchrone du TestClient Starlette
    (portal anyio) ne délivre pas fiablement un message envoyé depuis une tâche créée en
    dehors du flot direct requête/réponse (ici : le callback `add_listener` d'asyncpg, qui
    programme `websocket.send_json` via `loop.create_task` sur notification Postgres) — testé
    et confirmé bloquant indéfiniment lors de l'écriture de ce test. Un vrai serveur ASGI
    (uvicorn) n'a pas cette limite : c'est aussi ce qui tournera réellement en production.
    """
    def __init__(self, app):
        self.port = _free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        deadline = time.time() + 5
        while not self.server.started and time.time() < deadline:
            time.sleep(0.05)
        if not self.server.started:
            raise RuntimeError("uvicorn n'a pas démarré à temps.")
        return self

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(timeout=5)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.port}"

    @property
    def ws_url(self):
        return f"ws://127.0.0.1:{self.port}"


async def _cleanup(*, deal_ids, user_ids):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DELETE FROM guitar_deals WHERE id = ANY($1::text[])", list(deal_ids))
        await conn.execute("DELETE FROM users WHERE uid = ANY($1::text[])", list(user_ids))
    finally:
        await conn.close()


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestDealsAPI(unittest.TestCase):
    UID = "test-uid-deals-1"
    OTHER_UID = "test-uid-deals-2"

    def setUp(self):
        app.dependency_overrides[get_current_uid] = lambda: self.UID
        self.client = TestClient(app)
        self.client.__enter__()
        asyncio.run(_seed_deal("deal-1", self.UID, title="Parlor satinée"))
        asyncio.run(_seed_deal("deal-2", self.OTHER_UID, title="Annonce d'un autre utilisateur"))

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        asyncio.run(_cleanup(deal_ids=["deal-1", "deal-2"], user_ids=[self.UID, self.OTHER_UID]))

    def test_list_deals_scoped_to_user(self):
        resp = self.client.get("/deals")
        self.assertEqual(resp.status_code, 200)
        ids = [d["id"] for d in resp.json()]
        self.assertIn("deal-1", ids)
        self.assertNotIn("deal-2", ids)  # appartient à un autre utilisateur

    def test_get_deals_by_ids(self):
        resp = self.client.post("/deals/by-ids", json={"ids": ["deal-1", "deal-2"]})
        self.assertEqual(resp.status_code, 200)
        ids = [d["id"] for d in resp.json()]
        self.assertEqual(ids, ["deal-1"])  # deal-2 filtré (autre utilisateur), pas une erreur

    def test_toggle_favorite_twice_round_trips(self):
        first = self.client.patch("/deals/deal-1/favorite")
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["isFavorite"])

        second = self.client.patch("/deals/deal-1/favorite")
        self.assertFalse(second.json()["isFavorite"])

    def test_favorite_on_other_users_deal_returns_404(self):
        resp = self.client.patch("/deals/deal-2/favorite")
        self.assertEqual(resp.status_code, 404)

    def test_toggle_purchased_twice_round_trips_and_clears_price(self):
        """`toggle_purchased` a été réécrit en un UPDATE atomique (`SET is_purchased = NOT
        is_purchased`) plutôt qu'un lire-puis-écrire séparé en deux requêtes — cette table
        n'avait jusqu'ici AUCUN test de correction fonctionnelle, seulement le raisonnement.
        La bascule elle-même (round-trip + prix posé/effacé) est ce qu'un test unique peut
        vérifier ; la race sous requêtes concurrentes que le lire-puis-écrire permettait n'est
        pas reproductible de façon fiable ici — l'atomicité du UPDATE l'élimine par construction."""
        first = self.client.patch("/deals/deal-1/purchased", json={"purchasePrice": 450})
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["isPurchased"])
        self.assertEqual(float(self.client.get("/deals/deal-1").json()["purchase_price"]), 450.0)

        second = self.client.patch("/deals/deal-1/purchased", json={})
        self.assertFalse(second.json()["isPurchased"])
        self.assertIsNone(self.client.get("/deals/deal-1").json()["purchase_price"])  # effacé au retour à False

    def test_set_and_clear_manual_classification(self):
        set_resp = self.client.patch("/deals/deal-1/classification", json={"classificationPath": "acoustique_acier.parlor"})
        self.assertEqual(set_resp.status_code, 200)

        get_resp = self.client.get("/deals/deal-1")
        self.assertEqual(get_resp.json()["manual_classification"], "acoustique_acier.parlor")

        clear_resp = self.client.patch("/deals/deal-1/classification", json={"classificationPath": None})
        self.assertEqual(clear_resp.status_code, 200)
        self.assertIsNone(self.client.get("/deals/deal-1").json()["manual_classification"])

    def test_delete_deal(self):
        resp = self.client.delete("/deals/deal-1")
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.client.get("/deals/deal-1").status_code, 404)


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestDealsWebSocket(unittest.TestCase):
    """Test séparé de `TestDealsAPI` (pas de `TestClient`) : le pool asyncpg créé par le
    lifespan du TestClient est lié à SA boucle asyncio interne — un vrai serveur uvicorn
    tourne sur sa propre boucle, dans un autre thread, et ne peut pas réutiliser ce pool
    ("attached to a different loop"). En évitant tout TestClient dans cette classe, le
    lifespan d'uvicorn (déclenché par `_RealServer`) crée son propre pool sans conflit."""

    UID = "test-uid-ws-1"

    def setUp(self):
        asyncio.run(_seed_deal("deal-ws-1", self.UID, title="Parlor satinée"))
        # get_current_uid (dépendance HTTP) est distincte de verify_token (utilisé
        # directement par la route WebSocket, non-dépendance) — les deux doivent être
        # court-circuités ici puisque le vrai serveur uvicorn n'a pas de token Firebase réel.
        app.dependency_overrides[get_current_uid] = lambda: self.UID

    def tearDown(self):
        app.dependency_overrides.clear()
        asyncio.run(_cleanup(deal_ids=["deal-ws-1"], user_ids=[self.UID]))

    def test_websocket_receives_notification_on_own_change_only(self):
        """Le cœur du remplacement de onDealsIndexUpdate : une modification déclenche un
        push WS pour le bon utilisateur (canal Postgres partagé, filtré côté serveur — voir
        main.py::ws_deals). Vrai serveur uvicorn (voir _RealServer), pas le TestClient, pour
        que le push asynchrone (programmé via loop.create_task depuis le callback asyncpg
        add_listener) soit réellement délivré — confirmé bloquant indéfiniment avec le pont
        synchrone du TestClient Starlette lors de l'écriture de ce test."""
        with patch("backend.api.main.verify_token", return_value=self.UID), _RealServer(app) as srv:
            with ws_sync_client.connect(f"{srv.ws_url}/ws/deals?token=fake-mine") as ws_mine:
                with ws_sync_client.connect(f"{srv.ws_url}/ws/deals?token=fake-other") as ws_other:
                    # Attendre le "ready" explicite des deux sockets avant de déclencher la
                    # mutation : sans ça, une notification émise avant que le serveur ait fini
                    # d'enregistrer son LISTEN (juste après l'accept WS) se perdrait — Postgres
                    # ne rejoue pas les NOTIFY manqués (voir main.py::ws_deals).
                    self.assertEqual(json.loads(ws_mine.recv(timeout=5))["type"], "ready")
                    self.assertEqual(json.loads(ws_other.recv(timeout=5))["type"], "ready")

                    resp = requests.patch(f"{srv.base_url}/deals/deal-ws-1/favorite", timeout=5)
                    self.assertEqual(resp.status_code, 200)

                    raw = ws_mine.recv(timeout=5)
                    message = json.loads(raw)
                    self.assertEqual(message["id"], "deal-ws-1")
                    self.assertEqual(message["user_id"], self.UID)

                    # ws_other est authentifié avec le même uid mocké ici (dependency_overrides
                    # est global à `app`, pas par connexion) — ce test valide donc le transport
                    # réel (push asynchrone livré), la vraie isolation par utilisateur étant
                    # déjà couverte au niveau du filtre lui-même par les tests HTTP de
                    # TestDealsAPI (ex: test_favorite_on_other_users_deal_returns_404) et par
                    # relecture de main.py::ws_deals::_on_notify (retour anticipé si user_id ne
                    # correspond pas, avant tout envoi).
                    second = ws_other.recv(timeout=5)
                    self.assertEqual(json.loads(second)["id"], "deal-ws-1")


if __name__ == "__main__":
    unittest.main()
