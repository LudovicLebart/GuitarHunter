"""Tests du chat sur Claude (`chat_claude.py`) : validation, points de cache, flux SSE et enregistrement de l'usage. Aucun appel
réseau ni base de données : le client Anthropic et le pool sont simulés."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.api import chat_claude


def _run(coro):
    return asyncio.run(coro)


def _msg(text="Bonjour"):
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def _image(size=100):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "A" * size}}


class FakePool:
    def __init__(self):
        self.executed = []

    async def execute(self, sql, *args):
        self.executed.append(args)

    async def fetchval(self, *_a):
        return "2026-11-01"

    async def fetch(self, *_a):
        return []


class FakeStream:
    def __init__(self, deltas, final, error=None):
        self.deltas, self.final, self.error = deltas, final, error

    async def __aenter__(self):
        if self.error:
            raise self.error
        return self

    async def __aexit__(self, *_a):
        return False

    @property
    def text_stream(self):
        async def gen():
            for d in self.deltas:
                yield d
        return gen()

    async def get_final_message(self):
        return self.final


def _final(blocks=None):
    blocks = blocks or [{"type": "text", "text": "Bonjour"}]
    return SimpleNamespace(
        content=[SimpleNamespace(model_dump=lambda b=b, **_k: b) for b in blocks], stop_reason="end_turn",
        model="claude-sonnet-5-5",
        usage=SimpleNamespace(input_tokens=10, cache_read_input_tokens=100, cache_creation_input_tokens=50, output_tokens=7))


def _events(chunks):
    return [json.loads(c[6:]) for c in chunks if c.startswith("data: ")]


class TestValidation(unittest.TestCase):
    def test_accepts_a_normal_conversation_with_tools_and_thinking_blocks(self):
        tool = {"name": "propose_restoration_step", "description": "d", "input_schema": {"type": "object", "properties": {}}}
        messages = [_msg(), {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "tool_use", "id": "t1", "name": "propose_restoration_step", "input": {"label": "x"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}, _image()]}]
        req = chat_claude.validate_chat("système", [tool], messages, chat_claude.SONNET)
        self.assertEqual(req["images"], 1)
        self.assertEqual(req["messages"][1]["content"][0]["signature"], "sig")  # renvoyé tel quel

    def test_rejects_unknown_model_empty_conversation_and_foreign_blocks(self):
        for args in (("s", [], [_msg()], "gpt-5"), ("s", [], [], chat_claude.SONNET), ("", [], [_msg()], chat_claude.SONNET),
                     ("s", [], [{"role": "user", "content": [{"type": "document", "source": {}}]}], chat_claude.SONNET),
                     ("s", [], [{"role": "assistant", "content": "x"}], chat_claude.SONNET)):
            with self.assertRaises(chat_claude.ChatRequestError):
                chat_claude.validate_chat(*args)

    def test_rejects_too_many_tools_and_oversized_images(self):
        tools = [{"name": f"t{i}", "input_schema": {"type": "object"}} for i in range(chat_claude.MAX_TOOLS + 1)]
        with self.assertRaises(chat_claude.ChatRequestError):
            chat_claude.validate_chat("s", tools, [_msg()], chat_claude.SONNET)
        big = {"role": "user", "content": [_image(chat_claude.MAX_IMAGE_B64_CHARS + 1)]}
        with self.assertRaises(chat_claude.ChatRequestError):
            chat_claude.validate_chat("s", [], [big], chat_claude.SONNET)

    def test_consult_is_opus_without_tools_and_bounded(self):
        req = chat_claude.validate_consult("Dossier", [_image()])
        self.assertEqual(req["model"], chat_claude.OPUS)
        self.assertEqual(req["tools"], [])
        self.assertEqual(req["system"], chat_claude.CONSULT_SYSTEM)
        with self.assertRaises(chat_claude.ChatRequestError):
            chat_claude.validate_consult("x" * (chat_claude.MAX_BRIEF_CHARS + 1), [])
        with self.assertRaises(chat_claude.ChatRequestError):
            chat_claude.validate_consult("ok", [_image(), _image(), _image()])


class TestCacheBreakpoints(unittest.TestCase):
    def test_marks_system_and_last_block_without_mutating_the_input(self):
        messages = [_msg("a"), {"role": "assistant", "content": [{"type": "text", "text": "b"}]}, _msg("c")]
        system, out = chat_claude.with_cache_breakpoints("consigne", messages)
        self.assertEqual(system[0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(out[-1]["content"][-1]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("cache_control", messages[-1]["content"][-1])
        self.assertNotIn("cache_control", out[0]["content"][-1])


class TestEventStream(unittest.TestCase):
    def _stream(self, client, consult=False, pool=None):
        pool = pool or FakePool()
        req = chat_claude.validate_consult("Dossier", []) if consult else chat_claude.validate_chat("s", [], [_msg()], chat_claude.SONNET)

        async def collect():
            return [c async for c in chat_claude.event_stream(pool, "uid1", "deal1", "chat_turn", req, consult=consult)]
        with patch.object(chat_claude, "_client", lambda: client):
            return _events(_run(collect())), pool

    def test_streams_text_then_final_and_records_usage_with_cache_write(self):
        seen = {}

        def stream(**kw):
            seen.update(kw)
            return FakeStream(["Bon", "jour"], _final())
        events, pool = self._stream(SimpleNamespace(messages=SimpleNamespace(stream=stream)))
        self.assertEqual([e["type"] for e in events], ["text", "text", "final"])
        self.assertEqual(events[-1]["usage"], {"input": 10, "cache_read": 100, "cache_write": 50, "output": 7})
        self.assertEqual(seen["system"][0]["cache_control"], {"type": "ephemeral"})  # cache actif en conversation
        (args,) = pool.executed
        self.assertEqual(args[0], "claude-sonnet-5-5")
        self.assertEqual(args[5:8], (160, 100, 7))  # entrée (frais + lus + écrits), lus, sortie
        self.assertTrue(args[10])  # ok
        self.assertEqual(args[12], "anthropic")
        self.assertEqual(args[13], 50)  # tokens écrits dans le cache

    def test_consult_has_no_cache_no_tools_and_a_capped_answer(self):
        seen = {}

        def stream(**kw):
            seen.update(kw)
            return FakeStream([], _final())
        self._stream(SimpleNamespace(messages=SimpleNamespace(stream=stream)), consult=True)
        self.assertNotIn("tools", seen)
        self.assertEqual(seen["max_tokens"], chat_claude.CONSULT_MAX_TOKENS)
        self.assertEqual(seen["model"], chat_claude.OPUS)
        self.assertNotIn("cache_control", seen["system"][0])

    def test_failure_emits_error_event_and_records_a_failed_row(self):
        error = RuntimeError("surcharge")
        error.status_code = 529
        events, pool = self._stream(SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: FakeStream([], None, error))))
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(events[-1]["status"], 529)
        (args,) = pool.executed
        self.assertFalse(args[10])
        self.assertEqual(args[11], "http_529")

class TestRoutes(unittest.TestCase):
    """Routes HTTP : accès, validation et format SSE (sans lifespan, donc sans base : pool et visibilité simulés)."""

    def setUp(self):
        from fastapi.testclient import TestClient
        from backend.api import main
        self.main = main
        main.app.dependency_overrides[main.get_current_uid] = lambda: "uid1"
        self.pool = FakePool()

        async def visible(_pool, _deal_id, _uid):
            return None
        self.patches = [patch.object(main, "get_pool", lambda: self.pool), patch.object(main, "_require_deal_visible", visible),
                        patch.object(chat_claude, "_client", lambda: SimpleNamespace(
                            messages=SimpleNamespace(stream=lambda **kw: FakeStream(["Salut"], _final()))))]
        for p in self.patches:
            p.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.main.app.dependency_overrides.clear()

    def test_turn_streams_sse_events(self):
        body = {"model": chat_claude.SONNET, "system": "s", "tools": [], "messages": [_msg()], "action": "chat_turn"}
        resp = self.client.post("/deals/d1/chat/claude", json=body)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.headers["content-type"].startswith("text/event-stream"))
        sep = chr(10) * 2  # séparateur d'événements SSE
        chunks = [c + sep for c in resp.text.split(sep) if c]
        self.assertEqual(_events(chunks)[-1]["type"], "final")

    def test_turn_rejects_a_forbidden_model_with_422(self):
        body = {"model": "claude-fable-5-1", "system": "s", "tools": [], "messages": [_msg()]}
        self.assertEqual(self.client.post("/deals/d1/chat/claude", json=body).status_code, 422)

    def test_consult_streams_and_rejects_oversized_brief(self):
        ok = self.client.post("/deals/d1/chat/consult-opus", json={"brief": "Dossier", "images": []})
        self.assertEqual(ok.status_code, 200, ok.text)
        too_long = self.client.post("/deals/d1/chat/consult-opus", json={"brief": "x" * (chat_claude.MAX_BRIEF_CHARS + 1)})
        self.assertEqual(too_long.status_code, 422)


if __name__ == "__main__":
    unittest.main()
