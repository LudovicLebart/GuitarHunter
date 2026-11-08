"""Bornes des corps de requête de l'API (revue de l'API, 2026-11-07). Sans base : fonctions pures et état en mémoire."""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("FIREBASE_STORAGE_BUCKET", "test-bucket")

from fastapi import HTTPException

from backend.api import chat_claude, input_guard, main


class CommandTest(unittest.TestCase):
    def test_type_inconnu_refuse(self):
        with self.assertRaises(ValueError):
            input_guard.validate_command("DROP_TABLE", None)

    def test_types_du_bot_acceptes(self):
        for t in input_guard.COMMAND_TYPES:
            input_guard.validate_command(t, None)

    def test_charge_trop_grosse_refusee(self):
        with self.assertRaises(ValueError):
            input_guard.validate_command("ADD_CITY", {"name": "x" * 30_000})

    def test_les_types_correspondent_aux_gestionnaires_du_bot(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"), encoding="utf-8").read()
        for t in input_guard.COMMAND_TYPES:
            self.assertIn(f"'{t}'", src, t)


class SharedSnapshotTest(unittest.TestCase):
    def test_valide(self):
        input_guard.validate_shared_snapshot({"link": "https://www.kijiji.ca/v-x/1", "imageUrls": ["https://a/b.jpg"], "price": 100})

    def test_refus(self):
        for snap in ({"link": "https://evil.example/"}, {"imageUrls": ["http://a/b.jpg"]},
                     {"storageImageUrls": ["https://a/b.jpg"] * 21}, {"price": float("nan")},
                     {"description": "x" * 250_000}):
            with self.assertRaises(ValueError, msg=str(snap)[:40]):
                input_guard.validate_shared_snapshot(snap)


class OverridesTest(unittest.TestCase):
    def test_valide(self):
        input_guard.validate_analysis_overrides({"verdict": "GOOD_DEAL", "deal_score": 7, "also_qualifies_pepite": True,
                                                 "estimated_gross_margin": 250.5, "brand": None})

    def test_refus(self):
        for fields in ({"deal_score": 11}, {"deal_score": "8"}, {"brand": "x" * 600}, {"color": ["a"]},
                       {"estimated_gross_margin": float("inf")}, {"verdict": {"a": 1}}):
            with self.assertRaises(ValueError, msg=str(fields)):
                input_guard.validate_analysis_overrides(fields)


class MoneyAndTextTest(unittest.TestCase):
    def test_montants(self):
        input_guard.check_money(None)
        input_guard.check_money(0)
        for bad in (-1, float("nan"), True, "5", 10 ** 9):
            with self.assertRaises(ValueError):
                input_guard.check_money(bad)

    def test_etape_de_restauration(self):
        input_guard.validate_restoration_item("Refret", "frets", "notes", 120, None)
        with self.assertRaises(ValueError):
            input_guard.validate_restoration_item("x" * 600)
        with self.assertRaises(ValueError):
            input_guard.validate_restoration_item(notes="n" * 6000)

    def test_ids_groupes(self):
        input_guard.validate_deal_ids(["a"] * 200)
        with self.assertRaises(ValueError):
            input_guard.validate_deal_ids(["a"] * 201)


class ChatBoundsTest(unittest.TestCase):
    def test_tool_use_et_reflexion_comptent_dans_la_borne(self):
        counters = {"text": 0, "images": 0, "b64": 0}
        chat_claude._clean_block({"type": "tool_use", "id": "t", "name": "n", "input": {"a": "x" * 1000}}, counters)
        self.assertGreater(counters["text"], 1000)
        counters = {"text": 0, "images": 0, "b64": 0}
        chat_claude._clean_block({"type": "thinking", "thinking": "y" * 1000, "signature": "s"}, counters)
        self.assertGreater(counters["text"], 1000)

    def test_schema_d_outil_trop_gros(self):
        tool = {"name": "t", "input_schema": {"type": "object", "properties": {"p": {"description": "d" * 30_000}}}}
        with self.assertRaises(chat_claude.ChatRequestError):
            chat_claude.validate_chat("s", [tool], [{"role": "user", "content": "q"}], chat_claude.SONNET)


class ChatConcurrencyTest(unittest.TestCase):
    def setUp(self):
        main._chat_inflight.clear()

    def test_troisieme_flux_simultane_refuse_puis_libere(self):
        main._chat_acquire("u")
        main._chat_acquire("u")
        with self.assertRaises(HTTPException) as ctx:
            main._chat_acquire("u")
        self.assertEqual(ctx.exception.status_code, 429)
        main._chat_acquire("autre")      # un autre compte n'est pas gêné

        async def drain():
            async def gen():
                yield "x"
            async for _ in main._release_after("u", gen()):
                pass
        asyncio.run(drain())
        main._chat_acquire("u")          # une place libérée


class ListenerCapTest(unittest.TestCase):
    def tearDown(self):
        main._ws_open.clear()

    def test_plafond_par_compte_ferme_le_socket(self):
        for i in range(main._WS_MAX_PER_USER):
            main._ws_open[object()] = ("u", None)
        ws = MagicMock()
        ws.close = AsyncMock()
        self.assertIsNone(asyncio.run(main._connect_listener(ws, "u")))
        ws.close.assert_awaited_once_with(code=1013)

    def test_plafond_global(self):
        for i in range(main._WS_MAX_TOTAL):
            main._ws_open[object()] = (f"u{i}", None)
        ws = MagicMock()
        ws.close = AsyncMock()
        self.assertIsNone(asyncio.run(main._connect_listener(ws, "nouveau")))


if __name__ == "__main__":
    unittest.main()
