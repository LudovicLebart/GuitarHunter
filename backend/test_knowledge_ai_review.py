"""Revue des fiches par Claude : règle d'approbation automatique, URL vérifiées, reprise, plafond de coût, application."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import types
import unittest
from collections import Counter

from backend.scripts import knowledge_ai_review as air
from backend.scripts import knowledge_review_html as rh

NS = types.SimpleNamespace


def text_block(text, cites=()):
    return NS(type="text", text=text, citations=[NS(url=u) for u in cites])


def search_blocks(*urls):
    return [NS(type="server_tool_use", name="web_search"),
            NS(type="web_search_tool_result", content=[NS(url=u, title="t") for u in urls])]


def response(blocks, stop="end_turn", tin=1000, tout=300):
    return NS(content=blocks, stop_reason=stop, usage=NS(input_tokens=tin, output_tokens=tout))


class FakeClient:
    """Rejoue des réponses scriptées ; `calls` garde les requêtes."""
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def verdict_json(**kw):
    base = {"verdict": "ok", "confidence": "haute", "problems": [], "corrections": {},
            "sourced_facts": [{"fact": "Fondée en 1946 aux États-Unis", "url": "https://en.wikipedia.org/wiki/X"}],
            "homonym_risk": "aucun", "risky_aliases": [], "about_guitars": True, "notes": ""}
    base.update(kw)
    return json.dumps(base)


def ok_client(**kw):
    return FakeClient(response(search_blocks("https://en.wikipedia.org/wiki/X") + [text_block(verdict_json(**kw))]))


def fiche(fid="wd:a", name="Marquea", **kw):
    f = {"id": fid, "name": name, "kind": "brand", "description": "Fabricant de guitares.", "countries": ["US"],
         "active_from": 1946, "active_to": None, "relevance": "guitars", "aliases": [name], "parent_name": None,
         "hard": [], "flags": [], "trusted": False, "state": None}
    f.update(kw)
    return f


class TestAsk(unittest.TestCase):
    def test_collects_search_urls_citations_searches_and_last_turn_text(self):
        c = FakeClient(response(search_blocks("https://a.org/1", "https://b.org/2") +
                                [text_block('{"x": 1}', cites=["https://c.org/3"])], tin=500, tout=100))
        text, urls, usage = air.ask(c, "m", "sys", "user", 3)
        self.assertEqual(json.loads(text), {"x": 1})
        self.assertEqual(urls, {"https://a.org/1", "https://b.org/2", "https://c.org/3"})
        self.assertEqual(usage, {"in": 500, "out": 100, "searches": 1})
        tool = c.calls[0]["tools"][0]
        self.assertEqual((tool["name"], tool["max_uses"]), ("web_search", 3))

    def test_pause_turn_is_continued_with_the_paused_content_unchanged(self):
        paused = search_blocks("https://a.org/1")
        c = FakeClient(response(paused, stop="pause_turn"), response([text_block("{}")]))
        text, urls, usage = air.ask(c, "m", "sys", "user", 3)
        self.assertEqual((text, urls, usage["searches"]), ("{}", {"https://a.org/1"}, 1))
        self.assertEqual(c.calls[1]["messages"][-1], {"role": "assistant", "content": paused})

    def test_search_errors_do_not_break_url_collection(self):
        c = FakeClient(response([NS(type="web_search_tool_result", content=NS(type="web_search_tool_result_error")),
                                 text_block("{}")]))
        self.assertEqual(air.ask(c, "m", "s", "u", 1)[1], set())

    def test_cost_estimate(self):
        self.assertAlmostEqual(air.estimate_cost({"in": 1_000_000, "out": 100_000, "searches": 3}, 3, 15), 3 + 1.5 + 0.03)

    def test_parse_json_is_tolerant_of_surrounding_text(self):
        self.assertEqual(air.parse_json('Voici :\n```json\n{"a": 1}\n```'), {"a": 1})
        with self.assertRaises(ValueError):
            air.parse_json("pas de json")


class TestRule(unittest.TestCase):
    def _r(self, **kw):
        return air.normalize_review(json.loads(verdict_json(**kw)), {"https://en.wikipedia.org/wiki/X"})

    def test_clean_verified_ok_is_auto_approved(self):
        self.assertTrue(air.auto_approvable(self._r()))

    def test_every_single_condition_is_needed(self):
        for kw in ({"verdict": "douteuse"}, {"verdict": "fausse"}, {"confidence": "moyenne"}, {"problems": ["année fausse"]},
                   {"homonym_risk": "élevé"}, {"risky_aliases": ["Strat"]}, {"about_guitars": False},
                   {"sourced_facts": []}):
            self.assertFalse(air.auto_approvable(self._r(**kw)), kw)

    def test_a_url_the_search_never_returned_does_not_count(self):
        r = air.normalize_review(json.loads(verdict_json()), {"https://autre.org/"})
        self.assertEqual((r["sourced_facts"], r["unverified_urls"]), ([], ["https://en.wikipedia.org/wiki/X"]))
        self.assertFalse(air.auto_approvable(r))

    def test_unknown_verdict_or_confidence_falls_back_to_cautious_values(self):
        r = air.normalize_review({"verdict": "super", "confidence": "énorme"}, set())
        self.assertEqual((r["verdict"], r["confidence"]), ("douteuse", "basse"))

    def test_error_results_are_never_approved(self):
        self.assertFalse(air.auto_approvable({**self._r(), "error": "x"}))


class TestReviewOne(unittest.TestCase):
    def test_success_carries_verified_facts_and_cost(self):
        r = air.review_one(ok_client(), "m", fiche())
        self.assertEqual((r["verdict"], r["searches"]), ("ok", 1))
        self.assertGreater(r["cost_usd"], 0.01)
        self.assertTrue(air.auto_approvable(r))

    def test_api_failure_gives_no_verdict(self):
        r = air.review_one(FakeClient(RuntimeError("web search is not enabled")), "m", fiche())
        self.assertIn("not enabled", r["error"])
        self.assertNotIn("verdict", r)

    def test_unreadable_answer_becomes_a_doubtful_fiche_for_the_user(self):
        r = air.review_one(FakeClient(response([text_block("désolé")])), "m", fiche())
        self.assertEqual(r["verdict"], "douteuse")
        self.assertFalse(air.auto_approvable(r))

    def test_the_prompt_carries_the_fiche_facts_and_nothing_about_listings(self):
        c = ok_client()
        air.review_one(c, "m", fiche(description="Fabricant canadien de guitares."))
        sent = c.calls[0]["messages"][0]["content"]
        self.assertIn("Marquea", sent)
        self.assertIn("Fabricant canadien", sent)
        self.assertIn("1946", sent)


class TestRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.path = os.path.join(self.tmp, "r.jsonl")
        self.pool = [fiche(f"wd:{i}", f"Marque{i}") for i in range(5)]

    def test_resumes_without_redoing_finished_fiches_and_retries_errors(self):
        c = ok_client()
        air.run_review(c, self.pool, self.path, "m", limit=2, workers=1, log=lambda *_: None)
        self.assertEqual(len(c.calls), 2)
        air.run_review(c, self.pool, self.path, "m", workers=1, log=lambda *_: None)
        self.assertEqual(len(c.calls), 5)                       # seules les 3 restantes
        with open(self.path, "a", encoding="utf-8") as fh:      # une erreur n'est pas « faite »
            fh.write(json.dumps({"id": "wd:9", "name": "X", "error": "boom"}) + "\n")
        self.assertNotIn("wd:9", air.latest_by_id(air.load_results(self.path)))

    def test_cost_cap_stops_the_run_early(self):
        c = ok_client()
        air.run_review(c, self.pool, self.path, "m", max_usd=0.02, workers=1, log=lambda *_: None)
        self.assertLess(len(c.calls), 5)
        self.assertGreaterEqual(len(c.calls), 1)

    def test_selection_orders_by_hits_and_can_shuffle(self):
        fs = [fiche("wd:a", "A"), fiche("wd:b", "B"), fiche("wd:c", "C", state="approved")]
        hits = Counter({"wd:a": 1, "wd:b": 5, "wd:c": 9})
        self.assertEqual([f["id"] for f in air.select_fiches(fs, hits)], ["wd:b", "wd:a"])
        self.assertEqual([f["id"] for f in air.select_fiches(fs, hits, min_hits=2)], ["wd:b"])
        self.assertEqual(sorted(f["id"] for f in air.select_fiches(fs, hits, shuffle_seed=1)), ["wd:a", "wd:b"])


class TestRemaining(unittest.TestCase):
    def test_user_list_has_false_first_then_doubtful_and_skips_auto_and_decided(self):
        res = [dict(air.review_one(ok_client(), "m", fiche(f"wd:{n}", n)), id=f"wd:{n}") for n in "abcd"]
        res[1].update(verdict="douteuse")
        res[2].update(verdict="fausse")
        rows = air.remaining_for_user(res, decided_ids=["wd:d"])
        self.assertEqual([r["id"] for r in rows], ["wd:c", "wd:b"])      # a = auto, d = déjà décidée


@unittest.skipUnless(os.getenv("KB_TEST_DATABASE_URL"), "définir KB_TEST_DATABASE_URL (base Postgres JETABLE)")
class TestApplyPostgres(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        from backend import guitar_knowledge as gk
        from backend.test_guitar_knowledge import use_latest_kb
        self.gk = gk
        self.conn = psycopg.connect(os.environ["KB_TEST_DATABASE_URL"], autocommit=True, row_factory=dict_row)
        self.addCleanup(self.conn.close)
        with open(os.path.join(os.path.dirname(__file__), "api", "schema.sql"), encoding="utf-8") as fh:
            self.conn.execute(fh.read())
        self.conn.execute("TRUNCATE guitar_knowledge, guitar_knowledge_alias, guitar_knowledge_versions CASCADE")
        use_latest_kb(self)
        for fid, name in (("wd:a", "Marquea"), ("wd:b", "Marqueb"), ("wd:c", "Marquec")):
            self.conn.execute(
                """INSERT INTO guitar_knowledge (id, kind, name, description, relevance, source, kb_version, raw)
                   VALUES (%s,'brand',%s,'Fabricant américain de guitares électriques, actif depuis 1950.',
                           'guitars','wikidata',1,'{"origin":["category:en"]}')""", (fid, name))
            self.conn.execute("INSERT INTO guitar_knowledge_alias VALUES (%s,%s,%s,'wikidata')", (name.lower(), fid, name))
        gk.invalidate_cache()

    def _result(self, fid, **kw):
        r = air.review_one(ok_client(**kw), "claude-test", fiche(fid, fid))
        r["id"] = fid
        return r

    def _state(self, fid):
        return self.conn.execute("SELECT review_status, review_note, reviewed_digest FROM guitar_knowledge WHERE id=%s",
                                 (fid,)).fetchone()

    def test_only_rule_passing_fiches_are_approved_and_gate_then_serves_them(self):
        results = [self._result("wd:a"), self._result("wd:b", verdict="douteuse")]
        approved, _ = air.apply_auto(self.conn, results, log=lambda *_: None)
        self.assertEqual(approved, ["wd:a"])
        st = self._state("wd:a")
        self.assertEqual(st["review_status"], "approved")
        self.assertIn("Claude (auto, claude-test", st["review_note"])
        self.assertIn("wikipedia.org", st["review_note"])
        self.assertTrue(st["reviewed_digest"])
        self.assertIsNone(self._state("wd:b")["review_status"])
        self.gk.invalidate_cache()
        self.gk.configure_review_gate(True)
        self.assertEqual([f["id"] for f in self.gk.lookup(self.conn, "marquea marqueb")], ["wd:a"])

    def test_a_decision_by_the_user_is_never_overwritten(self):
        self.conn.execute("UPDATE guitar_knowledge SET review_status='rejected', review_note='faux, 1957' WHERE id='wd:a'")
        approved, skipped = air.apply_auto(self.conn, [self._result("wd:a")], log=lambda *_: None)
        self.assertEqual((approved, skipped), ([], ["wd:a"]))
        self.assertEqual(self._state("wd:a")["review_status"], "rejected")
        self.assertEqual(self._state("wd:a")["review_note"], "faux, 1957")

    def test_dry_run_writes_nothing(self):
        approved, _ = air.apply_auto(self.conn, [self._result("wd:c")], dry_run=True, log=lambda *_: None)
        self.assertEqual(approved, ["wd:c"])
        self.assertIsNone(self._state("wd:c")["review_status"])


class TestEnrich(unittest.TestCase):
    def _client(self, obj, urls=("https://en.wikipedia.org/wiki/X", "https://collector.example/x")):
        return FakeClient(response(search_blocks(*urls) + [text_block(json.dumps(obj))]))

    def _obj(self, **kw):
        base = {"hunt_notes": "Marque canadienne de guitares sur mesure (depuis 2006), séries M-SR6/7/8.",
                "tier": "boutique", "aliases": [], "reason": None, "sources": [
                    {"url": "https://en.wikipedia.org/wiki/X", "publisher": "Wikipedia", "kind": "wikipedia",
                     "title": "X", "lang": "en", "license": "CC BY-SA 4.0", "excerpt": "Canadian custom guitars"},
                    {"url": "https://collector.example/x", "publisher": "Collector", "kind": "collector",
                     "title": "X", "lang": "en", "license": "copyright", "excerpt": "[résumé] depuis 2006"}]}
        base.update(kw)
        return base

    def test_a_valid_patch_targets_the_fiche_id_and_passes_the_seed_validation(self):
        entry, why, cost = air.enrich_one(self._client(self._obj()), "m", fiche("wd:Q1", "Marquea"))
        self.assertIsNone(why)
        self.assertEqual((entry["patch"], entry["tier"], len(entry["sources"])), ("wd:Q1", "boutique", 2))
        self.assertGreater(cost, 0)

    def test_a_source_the_search_never_returned_is_dropped_and_two_sites_are_then_missing(self):
        obj = self._obj()
        obj["sources"][1]["url"] = "https://inventee.example/y"
        entry, why, _ = air.enrich_one(self._client(obj), "m", fiche())
        self.assertIsNone(entry)
        self.assertIn("2 sources", why)

    def test_two_pages_of_the_same_site_are_not_two_sources(self):
        obj = self._obj()
        obj["sources"][1]["url"] = "https://fr.wikipedia.org/wiki/X"
        entry, why, _ = air.enrich_one(self._client(obj, urls=("https://en.wikipedia.org/wiki/X", "https://fr.wikipedia.org/wiki/X")),
                                       "m", fiche())
        self.assertIsNone(entry)

    def test_no_note_means_no_patch(self):
        entry, why, _ = air.enrich_one(self._client({"hunt_notes": None, "sources": [], "reason": "introuvable"}), "m", fiche())
        self.assertEqual((entry, why), (None, "introuvable"))

    def test_an_unusable_alias_is_dropped_not_the_whole_note(self):
        entry, why, _ = air.enrich_one(self._client(self._obj(aliases=["x"])), "m", fiche())
        self.assertIsNone(why)
        self.assertNotIn("aliases", entry)

    def test_run_enrich_writes_a_seed_file_only_for_successes(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "seed.json")
            entries, failed, spent = air.run_enrich(self._client(self._obj()), "m", [fiche("wd:a", "A")], out, log=lambda *_: None)
            self.assertEqual(len(entries), 1)
            self.assertEqual(json.load(open(out, encoding="utf-8"))["entries"][0]["patch"], "wd:a")
            out2 = os.path.join(d, "none.json")
            air.run_enrich(self._client({"hunt_notes": None, "sources": [], "reason": "x"}), "m", [fiche()], out2, log=lambda *_: None)
            self.assertFalse(os.path.exists(out2))


class TestReportPage(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node absent")
    def test_page_with_claude_block_is_valid_javascript_and_shows_the_findings(self):
        cards = rh.build_cards([fiche()], Counter({"wd:a": 2}), {}, {})
        cards[0]["ai"] = {"verdict": "fausse", "confidence": "haute", "problems": ["années fausses"],
                          "corrections": {"active_from": 1887}, "sourced_facts": [{"fact": "Fondée en 1887", "url": "https://x.org/"}],
                          "notes": ""}
        html = rh.render_html(cards, generated="t")
        self.assertIn("Vérification Claude", html)
        script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.js")
            open(path, "w", encoding="utf-8").write(script)
            self.assertEqual(subprocess.run(["node", "--check", path]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
