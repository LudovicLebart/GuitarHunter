"""Outil `lookup_brand` de l'Expert Claude (2026-10-14) : recherche large dans la base de marques, boucle d'outil de
`_call_claude_json`, câblage derrière `T3_KNOWLEDGE_ENABLED`. Sans Postgres ni réseau."""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("APP_ID_TARGET", "test")
os.environ.setdefault("USER_IDS_TARGET", "test_user")

from backend import guitar_knowledge as gk
from backend import t3_claude_tools as tools
from backend.test_analyzer import _claude_response, _make_analyzer

ALIASES = {
    "carmelo catania": {"k1"}, "catania": {"k1"},
    "guerrilla guitars": {"k2"}, "guerrilla": {"k2"},
    "martin": {"k3"},
    "ibanez": {"k4"},
}


class TestMatchAliases(unittest.TestCase):
    def test_exact_match_on_what_the_model_read(self):
        found = gk.match_aliases("Carmelo Catania", ALIASES)
        self.assertEqual(found["k1"], ("carmelo catania", "exact", 1.0))

    def test_typo_is_a_fuzzy_match_with_a_score(self):
        found = gk.match_aliases("guerilla", ALIASES)       # une seule lettre manquante
        alias, mtype, score = found["k2"]
        self.assertEqual(mtype, "fuzzy")
        self.assertIn("guerrilla", alias)
        self.assertGreaterEqual(score, 0.8)

    def test_a_shared_generic_word_does_not_hide_unrelated_names(self):
        # Constaté sur données réelles : « guerilla guitars » → « Gurian Guitars » (0,87), « 7 string electric guitar »
        # → « Yamaha electric guitar models ». Les mots communs ne doivent pas faire le rapprochement.
        aliases = {"gurian guitars": {"k5"}, "gurian": {"k5"}, "yamaha electric guitar models": {"k6"}}
        self.assertEqual(gk.match_aliases("guerilla guitars", aliases), {})
        self.assertEqual(gk.match_aliases("7 string electric guitar", aliases), {})

    def test_typo_in_a_multiword_name_still_matches(self):
        found = gk.match_aliases("carmelo catenia", {"carmelo catania": {"k1"}})
        self.assertEqual(found["k1"][1], "fuzzy")

    def test_word_of_a_longer_alias_is_only_a_partial_match(self):
        found = gk.match_aliases("catania", {"carmelo catania": {"k1"}})
        self.assertEqual(found["k1"][1:], ("partiel", gk._TOOL_PARTIAL_SCORE))

    def test_best_type_is_kept_per_fiche(self):
        # « catania » est un alias exact de k1 : l'exact l'emporte sur le partiel de « carmelo catania ».
        self.assertEqual(gk.match_aliases("catania", ALIASES)["k1"][1], "exact")

    def test_a_prefix_or_extension_is_not_a_typo(self):
        self.assertNotIn("k3", gk.match_aliases("martine", ALIASES))   # autre mot, pas une faute
        self.assertNotIn("k4", gk.match_aliases("ibanezz", ALIASES))   # suffixe

    def test_generic_words_and_empty_query_find_nothing(self):
        self.assertEqual(gk.match_aliases("", ALIASES), {})
        self.assertEqual(gk.match_aliases("guitar vintage custom", ALIASES), {})


class TestVerificationLabels(unittest.TestCase):
    def test_unreviewed_import_is_only_a_hint(self):
        self.assertEqual(gk.unverified_reasons({"kind": "brand", "relevance": "guitars", "source": "wikidata",
                                                "description": "Fabricant de guitares électriques américaines, actif depuis les années 1950."}),
                         ["import Wikidata non relu"])

    def test_curated_or_manual_fiche_with_detail_has_no_reason(self):
        text = "Fabricant de guitares électriques et de basses installé au Québec depuis 2006."
        for extra in ({"curated": True}, {"source": "manual"}):
            self.assertEqual(gk.unverified_reasons({"kind": "brand", "relevance": "guitars", "description": text,
                                                    **extra}), [], extra)

    def test_approved_review_wins_over_flags_but_a_stale_one_does_not(self):
        base = {"kind": "luthier", "confidence": "single_source", "relevance": "unknown", "description": "x",
                "review_status": "approved", "reviewed_digest": "d1"}
        self.assertEqual(gk.unverified_reasons({**base, "content_digest": "d1"}), [])
        self.assertIn("fiche modifiée depuis sa relecture", gk.unverified_reasons({**base, "content_digest": "d2"}))

    def test_each_soft_flag_gives_its_reason(self):
        reasons = gk.unverified_reasons({"confidence": "single_source", "kind": "luthier", "curated": False,
                                         "relevance": "unknown", "source": "wikidata", "description": "x"})
        for expected in ("source unique", "luthier, fiche non curée", "import brut, nature de l'entité non confirmée",
                         "fiche creuse", "import Wikidata non relu"):
            self.assertIn(expected, reasons)

    def test_maker_category_import_is_not_flagged_as_raw(self):
        self.assertNotIn("import brut, nature de l'entité non confirmée",
                         gk.unverified_reasons({"kind": "brand", "relevance": "unknown", "from_maker_category": True,
                                                "description": "Fabricant de guitares électriques américaines, actif depuis les années 1950."}))

    def test_hard_failures(self):
        self.assertEqual(gk.hard_failures({"active_from": 1850, "active_to": 1900, "description": "Luthier."}), [])
        self.assertTrue(gk.hard_failures({"active_from": 1700}))
        self.assertTrue(gk.hard_failures({"active_from": 1990, "active_to": 1960}))
        self.assertTrue(gk.hard_failures({"active_to": 2999}))
        self.assertTrue(gk.hard_failures({"description": "Fabricant suisse de montres."}))
        self.assertEqual(gk.hard_failures({"description": "Fabricant de montres et de guitares."}), [])
        self.assertTrue(gk.hard_failures({"review_status": "rejected"}))


class TestFormatting(unittest.TestCase):
    def test_no_result_never_says_low_value(self):
        text = gk.format_brand_results("zzz", [])
        self.assertIn("Aucune fiche", text)
        self.assertIn("ne dit rien de sa valeur", text)
        self.assertIn("marque à vérifier", text)

    def test_unverified_fiche_is_labelled_and_sources_are_not_leaked(self):
        fiche = {"id": "manual:x", "kind": "brand", "name": "Marque X", "match_type": "fuzzy", "matched_on": "a→b",
                 "score": 0.84, "unverified_reasons": ["source unique"], "description": "Luthier québécois.",
                 "sources": [{"url": "https://secret.example"}], "parent_name": None, "countries": ["CA"]}
        text = gk.format_brand_results("marque x", [fiche])
        self.assertIn("NON VÉRIFIÉE", text)
        self.assertIn("source unique", text)
        self.assertIn("0.84", text)
        self.assertNotIn("secret.example", text)


class TestMatchAliasesMisuse(unittest.TestCase):
    def test_the_old_positional_call_fails_loudly(self):
        """`match_aliases(aliases, by_len, texts)` était la signature de la fonction par type, renommée `match_alias_index` :
        un appelant resté sur l'ancien nom doit échouer, pas renvoyer silencieusement un résultat vide."""
        with self.assertRaises(TypeError):
            gk.match_aliases({"fender": {"k1"}}, {}, ["Fender Stratocaster"])
        index_aliases, by_len = gk.build_alias_index([("fender", "k1", "brand")])
        self.assertEqual(set(gk.match_alias_index(index_aliases, by_len, ["Fender Stratocaster"])), {"k1"})   # la bonne fonction
        self.assertEqual(set(gk.match_aliases("Fender Stratocaster", {"fender": {"k1"}})), {"k1"})              # et la recherche libre


class TestBrandToolHandler(unittest.TestCase):
    def _handler(self):
        trace = []
        return tools.make_brand_tool(MagicMock(), trace), trace

    def test_unknown_tool_and_empty_query_are_answered_not_raised(self):
        handler, _ = self._handler()
        self.assertIn("inconnu", handler("autre", {}))
        self.assertIn("vide", handler("lookup_brand", {"query": "  "}))

    def test_query_is_searched_traced_and_capped(self):
        handler, trace = self._handler()
        fiche = {"id": "k1", "kind": "brand", "name": "Catania", "match_type": "exact", "matched_on": "catania",
                 "score": 1.0, "unverified_reasons": [], "relevance": "guitars"}
        conn_cm = MagicMock()
        pool = MagicMock()
        pool.connection.return_value = conn_cm
        with patch("backend.pg_db.get_pool", return_value=pool), \
             patch.object(tools.guitar_knowledge, "search_brand", return_value=[fiche]) as search:
            out = handler("lookup_brand", {"query": "Catania"})
            self.assertIn("Catania", out)
            search.assert_called_once()
            self.assertEqual(trace[0], {"query": "Catania", "fiches": [
                {"id": "k1", "match": "exact", "score": 1.0, "verified": True}]})
            for _ in range(tools.MAX_CALLS_PER_ANALYSIS):
                last = handler("lookup_brand", {"query": "x"})
        self.assertIn("Limite", last)


    def test_reset_restores_the_budget_and_clears_the_trace_in_place(self):
        handler, trace = self._handler()
        pool = MagicMock()
        with patch("backend.pg_db.get_pool", return_value=pool), \
             patch.object(tools.guitar_knowledge, "search_brand", return_value=[]):
            for _ in range(tools.MAX_CALLS_PER_ANALYSIS):
                handler("lookup_brand", {"query": "x"})
            self.assertIn("Limite", handler("lookup_brand", {"query": "x"}))
            same_list = trace
            handler.reset()
            self.assertIs(trace, same_list)                  # vidée EN PLACE : l'appelant garde sa référence
            self.assertEqual(trace, [])
            self.assertNotIn("Limite", handler("lookup_brand", {"query": "x"}))   # budget rendu à la reprise


class TestToolLoop(unittest.TestCase):
    """`_call_claude_json` avec outils : allers-retours, usage par appel, erreurs d'outil, budget."""

    def setUp(self):
        self.a = _make_analyzer()
        self.client = MagicMock()
        for p in (patch("backend.llm_clients._get_claude_client", return_value=self.client),
                  patch("backend.llm_clients.ANTHROPIC_API_KEY", "cle-test"),
                  patch("backend.llm_clients.llm_usage.record")):
            started = p.start()
            self.addCleanup(p.stop)
            if p.attribute == "record":
                self.record = started

    @staticmethod
    def _tool_use(query):
        r = _claude_response("", stop_reason="tool_use")
        r.content = [MagicMock(type="thinking"),
                     MagicMock(type="tool_use", id="tu_1", input={"query": query}, **{"name": "lookup_brand"})]
        r.content[1].name = "lookup_brand"
        return r

    def test_tool_round_trip_then_final_json(self):
        self.client.messages.create.side_effect = [self._tool_use("catania"),
                                                   _claude_response('{"verdict": "PEPITE"}')]
        seen = []
        result, err = self.a._call_claude_json(
            "claude-sonnet-5-5", ["p"], action="t3_expert", tools=[tools.LOOKUP_BRAND_TOOL],
            tool_handler=lambda name, args: seen.append((name, args)) or "FICHE")
        self.assertIsNone(err)
        self.assertEqual(result, {"verdict": "PEPITE"})
        self.assertEqual(seen, [("lookup_brand", {"query": "catania"})])
        self.assertEqual(self.record.call_count, 2)          # une ligne d'usage par appel API
        second = self.client.messages.create.call_args_list[1].kwargs["messages"]
        self.assertEqual([m["role"] for m in second], ["user", "assistant", "user"])
        result_block = second[2]["content"][0]
        self.assertEqual((result_block["type"], result_block["tool_use_id"], result_block["content"]),
                         ("tool_result", "tu_1", "FICHE"))
        self.assertNotIn("tool_choice", self.client.messages.create.call_args_list[0].kwargs)

    def test_handler_exception_is_returned_to_the_model_as_error(self):
        self.client.messages.create.side_effect = [self._tool_use("x"), _claude_response('{"verdict": "FAIR"}')]

        def boom(name, args):
            raise RuntimeError("base hors ligne")
        result, err = self.a._call_claude_json("claude-sonnet-5-5", ["p"], tools=[tools.LOOKUP_BRAND_TOOL],
                                               tool_handler=boom)
        self.assertEqual(result, {"verdict": "FAIR"})
        block = self.client.messages.create.call_args_list[1].kwargs["messages"][2]["content"][0]
        self.assertTrue(block["is_error"])
        self.assertIn("base hors ligne", block["content"])

    def test_a_json_retry_gets_a_fresh_tool_budget_and_a_clean_trace(self):
        """1re tentative : un appel d'outil puis un JSON invalide ; reprise : la boucle repart, le gestionnaire est remis à zéro."""
        self.client.messages.create.side_effect = [self._tool_use("a"), _claude_response("pas du json {{{"),
                                                   self._tool_use("b"), _claude_response('{"verdict": "FAIR"}')]
        resets, seen = [], []

        def handler(name, args):
            seen.append(args["query"])
            return "ok"
        handler.reset = lambda: resets.append(len(seen))
        result, err = self.a._call_claude_json("claude-sonnet-5-5", ["p"], tools=[tools.LOOKUP_BRAND_TOOL],
                                               tool_handler=handler, max_retries=1)
        self.assertEqual(result, {"verdict": "FAIR"})
        self.assertEqual(seen, ["a", "b"])
        self.assertEqual(resets, [1])                       # remis à zéro UNE fois, au début de la 2e tentative seulement

    def test_a_handler_without_reset_still_works_on_retry(self):
        self.client.messages.create.side_effect = [_claude_response("pas du json {{{"), _claude_response('{"verdict": "FAIR"}')]
        result, err = self.a._call_claude_json("claude-sonnet-5-5", ["p"], tools=[tools.LOOKUP_BRAND_TOOL],
                                               tool_handler=lambda n, a: "ok", max_retries=1)
        self.assertEqual(result, {"verdict": "FAIR"})

    def test_budget_exhausted_forces_the_final_answer(self):
        with patch("backend.llm_clients.T3_KNOWLEDGE_MAX_TOOL_ROUNDS", 1):
            self.client.messages.create.side_effect = [self._tool_use("a"), _claude_response('{"verdict": "FAIR"}')]
            result, err = self.a._call_claude_json("claude-sonnet-5-5", ["p"], tools=[tools.LOOKUP_BRAND_TOOL],
                                                   tool_handler=lambda n, a: "ok")
        self.assertEqual(result, {"verdict": "FAIR"})
        last = self.client.messages.create.call_args_list[-1].kwargs
        self.assertEqual(last["tool_choice"], {"type": "none"})
        self.assertIn("tools", last)                 # exigé par l'API tant que l'historique contient un tool_use

    def test_without_tools_nothing_changes(self):
        self.client.messages.create.return_value = _claude_response('{"verdict": "FAIR"}')
        self.a._call_claude_json("claude-sonnet-5-5", ["p"])
        kwargs = self.client.messages.create.call_args.kwargs
        self.assertNotIn("tools", kwargs)
        self.assertNotIn("tool_choice", kwargs)
        self.assertEqual(self.client.messages.create.call_count, 1)


class TestWiring(unittest.TestCase):
    """`_run_t3_phase` : l'outil et l'addendum n'apparaissent que si Claude ET T3_KNOWLEDGE_ENABLED."""

    def _run(self, provider, enabled):
        a = _make_analyzer()
        a._call_claude_json = MagicMock(return_value=({"verdict": "PEPITE"}, None))
        a._call_gemini_json = MagicMock(return_value=({"verdict": "FAIR"}, None))
        with patch("backend.analyzer.T3_PROVIDER", provider), patch("backend.analyzer.T3_KNOWLEDGE_ENABLED", enabled), \
                patch("backend.analyzer.T3_CLAUDE_MODEL", "claude-sonnet-5-5"):
            result = a._run_t3_phase("base", [], {}, "gemini-3.1-pro-preview", None, ["gemini-3.7-flash"],
                                     {"verdict": "FAIR", "summary": "RAS"}, "motif")
        return a, result

    def test_claude_with_switch_on_gets_tool_and_addendum(self):
        a, _ = self._run("claude", True)
        args, kwargs = a._call_claude_json.call_args
        self.assertEqual(kwargs["tools"], [tools.LOOKUP_BRAND_TOOL])
        self.assertTrue(callable(kwargs["tool_handler"]))
        self.assertTrue(args[1][0].endswith(tools.CLAUDE_T3_ADDENDUM))

    def test_switch_off_leaves_the_claude_call_unchanged(self):
        a, _ = self._run("claude", False)
        args, kwargs = a._call_claude_json.call_args
        self.assertNotIn("tools", kwargs)
        self.assertNotIn(tools.CLAUDE_T3_ADDENDUM, args[1][0])

    def test_gemini_never_gets_the_tool_even_with_switch_on(self):
        a, _ = self._run("gemini", True)
        a._call_claude_json.assert_not_called()
        self.assertNotIn("tools", a._call_gemini_json.call_args.kwargs)
        self.assertNotIn(tools.CLAUDE_T3_ADDENDUM, a._call_gemini_json.call_args.args[1][0])


class TestDiagnosticScript(unittest.TestCase):
    def test_report_shows_portier_and_tool_views_and_flags_unverified(self):
        from backend.scripts import knowledge_diag_t3 as diag
        fiche = {"name": "Catania", "match_type": "partiel", "score": 0.7, "unverified_reasons": ["source unique"]}
        with patch.object(diag.gk, "lookup", return_value=[]), patch.object(diag.gk, "configure_version"), \
                patch.object(diag.gk, "search_brand", return_value=[fiche]):
            text = diag.report_listing(None, {"id": "d1", "title": "Guitare 7 cordes", "description": "x"},
                                       ["catania"])
        self.assertIn("aucune fiche", text)                       # le Portier ne trouve rien par le titre
        self.assertIn("lu: catania", text)
        self.assertIn("NON VÉRIFIÉE: source unique", text)


class TestAddendum(unittest.TestCase):
    def test_addendum_states_the_rules_that_matter(self):
        text = tools.CLAUDE_T3_ADDENDUM
        for needle in ("visual_inspection", "lookup_brand", "NON VÉRIFIÉE", "≠ faible valeur", "marque à vérifier"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
