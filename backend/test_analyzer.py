"""Tests pour le pipeline de décision de `DealAnalyzer` (backend/analyzer.py).

Périmètre volontairement restreint au changement du 2026-09-24 : un échec du Portier T1
réel (appel raté OU réponse malformée) ne doit plus fail-open vers l'Analyste (T2) — voir
`_run_analysis_cascade_body`/`T1_ERROR_STATUSES`. Le reste de la cascade (rejet T1, routage
Chantier G, Tier 2/3) n'est pas couvert ici.
"""
import os
import threading
import unittest
from unittest.mock import MagicMock, patch

# config.py fait sys.exit(1) à l'import sans APP_ID_TARGET : valeurs neutres par défaut pour que
# ces tests tournent sans .env (n'écrase jamais une vraie valeur déjà présente).
os.environ.setdefault("APP_ID_TARGET", "test")
os.environ.setdefault("USER_IDS_TARGET", "test_user")

from backend import llm_usage, t1_circuit_breaker
from backend.analyzer import DealAnalyzer
from backend.t1_prompt import build_t1_gatekeeper_prompt


def _make_analyzer():
    """Instance minimale, sans passer par __init__ (qui appelle genai.configure()/
    list_models(), un vrai réseau) — seuls les attributs lus par _run_analysis_cascade_body
    sont posés à la main, comme _make_bot() dans test_bot.py."""
    analyzer = DealAnalyzer.__new__(DealAnalyzer)
    analyzer.logger = MagicMock()
    analyzer.models = {}
    analyzer._model_error_last_notified = {}
    analyzer._taxonomy_index = None
    analyzer._taxonomy_index_source = None
    analyzer._cache_lock = threading.Lock()
    return analyzer


def _listing():
    return {"id": "deal_1", "title": "Guitare Fender Stratocaster", "description": "Bon état", "price": 300}


class TestGatekeeperFailureSkip(unittest.TestCase):
    def setUp(self):
        self.analyzer = _make_analyzer()
        # Portier miroir (Chantier H) : best-effort, jamais utilisé pour la décision — neutralisé
        # pour isoler le comportement du décideur T1 réel testé ici.
        self.analyzer._run_t1_shadow_observation = MagicMock(return_value={})
        # t1_circuit_breaker._state est un global process-wide : sans reset, l'historique d'échecs
        # d'un test fuit vers le suivant (ex: 2 échecs "local"/"qwen" par test, seuil par défaut 3).
        t1_circuit_breaker.reset()
        self.addCleanup(t1_circuit_breaker.reset)
        # llm_usage.record() est appelé directement par le nouveau bloc T1_PROVIDER_CHAIN sur
        # chaque échec — mocké pour ne jamais tenter une vraie connexion Postgres dans les tests.
        self._llm_usage_record_patcher = patch("backend.analyzer.llm_usage.record")
        self._llm_usage_record_patcher.start()
        self.addCleanup(self._llm_usage_record_patcher.stop)
        # `_run_analysis_cascade` sort en "ERROR" dès le départ sans GEMINI_API_KEY (garde-fou de
        # prod) : sans ce patch, ces tests dépendaient de la variable d'environnement réelle.
        gemini_key_patcher = patch("backend.analyzer.GEMINI_API_KEY", "dummy")
        gemini_key_patcher.start()
        self.addCleanup(gemini_key_patcher.stop)

    def test_t1_call_failure_returns_skip_verdict_not_fail_open(self):
        """err_t1 renseigné (appel raté, ex: panne réseau/TokenRouter) : doit sauter
        l'annonce plutôt que de continuer vers le Tier 2."""
        self.analyzer._call_t1_provider = MagicMock(return_value=(None, "Panne réseau TokenRouter."))

        result = self.analyzer.analyze_deal(_listing(), firestore_config={"analysisConfig": {}})

        self.assertEqual(result["verdict"], "GATEKEEPER_FAILED_SKIP")
        self.assertEqual(result["gatekeeperVerdict"], "ERROR_GATEKEEPER")

    def test_t1_malformed_response_returns_skip_verdict_not_fail_open(self):
        """Le Portier répond, mais sans status/verdict exploitable (JSON invalide) : doit
        aussi sauter l'annonce, pas seulement le cas d'exception explicite (err_t1)."""
        self.analyzer._call_t1_provider = MagicMock(return_value=({"unexpected": "shape"}, None))

        result = self.analyzer.analyze_deal(_listing(), firestore_config={"analysisConfig": {}})

        self.assertEqual(result["verdict"], "GATEKEEPER_FAILED_SKIP")
        self.assertEqual(result["gatekeeperVerdict"], "ERROR")

    @patch("backend.analyzer.T1_PROVIDER_CHAIN", ["local", "qwen"])
    def test_t1_chain_falls_through_to_next_candidate_on_failure(self):
        """Chantier I — coeur du fallback chaîné : un échec du PREMIER fournisseur de
        T1_PROVIDER_CHAIN (ex: local/Dell injoignable) ne doit pas sauter l'annonce si un
        fournisseur suivant répond correctement, verdict inclus. Chaîne figée par le décorateur
        (indépendante de la config d'environnement réelle) pour un test déterministe."""
        def _side_effect(provider, *args, **kwargs):
            if provider == "local":
                return None, "Connection refused (Dell injoignable)."
            return {"status": "REJECTED", "reason": "Pas une guitare."}, None

        self.analyzer._call_t1_provider = MagicMock(side_effect=_side_effect)

        result = self.analyzer.analyze_deal(_listing(), firestore_config={"analysisConfig": {}})

        self.assertEqual(self.analyzer._call_t1_provider.call_count, 2)
        self.assertEqual(result["verdict"], "REJECTED")

    def test_t1_normal_rejection_is_unaffected(self):
        """Garde-fou anti-régression : un verdict normal (Portier opérationnel) suit
        toujours son chemin existant (ici : rejet), pas le nouveau skip."""
        self.analyzer._call_t1_provider = MagicMock(return_value=({"status": "REJECTED", "reason": "Pas une guitare."}, None))

        result = self.analyzer.analyze_deal(_listing(), firestore_config={"analysisConfig": {}})

        self.assertEqual(result["verdict"], "REJECTED")


class TestT1PromptBuilder(unittest.TestCase):
    def test_annonce_block_is_always_last_even_with_user_correction(self):
        prompt = build_t1_gatekeeper_prompt(_listing(), {"guitare": {}}, "INSTRUCTION", user_comment="C'est une vraie Strat")
        self.assertTrue(prompt.rstrip().endswith("</annonce>"))
        self.assertLess(prompt.index("CORRECTION UTILISATEUR"), prompt.index("<annonce>"))

    def test_empty_string_is_preserved_but_missing_key_becomes_na(self):
        prompt = build_t1_gatekeeper_prompt({"title": "X", "description": ""}, {}, "INSTRUCTION")
        self.assertIn('"description": ""', prompt)
        self.assertIn('"localisation": "N/A"', prompt)

    def test_analyzer_delegates_to_shared_builder(self):
        analyzer = _make_analyzer()
        self.assertEqual(
            analyzer._construct_t1_gatekeeper_prompt(_listing(), {}, "INSTRUCTION", "note"),
            build_t1_gatekeeper_prompt(_listing(), {}, "INSTRUCTION", "note"),
        )


class TestLlmUsageRecording(unittest.TestCase):
    @patch("backend.analyzer.llm_usage.record")
    @patch("backend.llm_clients.OpenAI")
    def test_local_call_records_provider_local(self, mock_openai, mock_record):
        response = MagicMock()
        response.choices[0].message.content = '{"status": "FAIR"}'
        response.usage.completion_tokens = 5
        response.usage.completion_tokens_details = None
        response.usage.prompt_tokens_details = None
        response.usage.prompt_tokens = 10
        response.usage.total_tokens = 15
        mock_openai.return_value.chat.completions.create.return_value = response
        analyzer = _make_analyzer()

        result, err = analyzer._call_openai_compatible_json(
            "p", [], "qwen3-vl:8b-instruct", "ollama", "http://100.94.33.54:11434/v1", provider_label="local"
        )

        self.assertIsNone(err)
        self.assertEqual(result, {"status": "FAIR"})
        self.assertEqual(mock_record.call_args.kwargs["provider"], "local")

    @patch("backend.analyzer.llm_usage.record")
    @patch("backend.llm_clients.OpenAI")
    def test_without_label_provider_is_deduced_from_base_url(self, mock_openai, mock_record):
        response = MagicMock()
        response.choices[0].message.content = '{"status": "FAIR"}'
        response.usage.completion_tokens = 5
        response.usage.completion_tokens_details = None
        response.usage.prompt_tokens_details = None
        response.usage.prompt_tokens = 10
        response.usage.total_tokens = 15
        mock_openai.return_value.chat.completions.create.return_value = response
        _make_analyzer()._call_openai_compatible_json("p", [], "m", "k", "https://api.tokenrouter.io/v1")
        self.assertEqual(mock_record.call_args.kwargs["provider"], "tokenrouter")

    @patch("backend.analyzer.llm_usage.record")
    @patch("backend.llm_clients.OpenAI")
    def test_failed_call_records_ok_false_with_error_type_and_provider_local(self, mock_openai, mock_record):
        mock_openai.return_value.chat.completions.create.side_effect = TimeoutError("request timed out")

        result, err = _make_analyzer()._call_openai_compatible_json(
            "p", [], "qwen3-vl:8b-instruct", "ollama", "http://100.94.33.54:11434/v1", provider_label="local"
        )

        self.assertIsNone(result)
        self.assertIn("timed out", err)
        kwargs = mock_record.call_args.kwargs
        self.assertEqual((kwargs["provider"], kwargs["ok"], kwargs["error_type"]), ("local", False, "timeout"))
        mock_record.assert_called_once()

    @patch("backend.analyzer.llm_usage.record")
    @patch("backend.llm_clients.OpenAI")
    def test_invalid_json_records_a_single_failure_row_not_a_success(self, mock_openai, mock_record):
        response = MagicMock()
        response.choices[0].message.content = "pas du json {"
        response.usage.completion_tokens = 5
        response.usage.completion_tokens_details = None
        response.usage.prompt_tokens_details = None
        response.usage.prompt_tokens = 10
        response.usage.total_tokens = 15
        mock_openai.return_value.chat.completions.create.return_value = response

        result, err = _make_analyzer()._call_openai_compatible_json("p", [], "m", "k", "https://api.tokenrouter.io/v1")

        self.assertIsNone(result)
        mock_record.assert_called_once()
        kwargs = mock_record.call_args.kwargs
        self.assertEqual((kwargs["ok"], kwargs["error_type"]), (False, "json"))
        self.assertEqual(kwargs["input_tokens"], 10)  # tokens facturés conservés

    @patch("backend.llm_clients.TOKENROUTER_API_KEY", "")
    @patch("backend.analyzer.llm_usage.record")
    def test_qwen_provider_without_tokenrouter_key_still_records_the_failure(self, mock_record):
        _, err = _make_analyzer()._call_t1_provider("qwen", "prompt", [], "gemini-x")
        self.assertIn("manquante", err)
        self.assertEqual(mock_record.call_args.kwargs["error_type"], "no_key")

    @patch("backend.analyzer.llm_usage.record")
    def test_missing_api_key_records_no_key(self, mock_record):
        _, err = _make_analyzer()._call_openai_compatible_json("p", [], "m", "", "https://api.tokenrouter.io/v1")
        self.assertIn("manquante", err)
        self.assertEqual(mock_record.call_args.kwargs["error_type"], "no_key")


class TestClassifyError(unittest.TestCase):
    def test_categories(self):
        import json
        self.assertEqual(llm_usage.classify_error(json.JSONDecodeError("x", "y", 0)), "json")
        self.assertEqual(llm_usage.classify_error(TimeoutError("boom")), "timeout")
        self.assertEqual(llm_usage.classify_error(Exception("Connection refused")), "connection")
        self.assertEqual(llm_usage.classify_error(type("APIStatusError", (Exception,), {})("x")), "http")


class TestT1Knowledge(unittest.TestCase):
    """Branchement de la base de connaissances au Portier : interrupteur, ordre du prompt, traçabilité, échec ouvert."""
    FICHE = {"id": "manual:vantage", "name": "Vantage", "kind": "brand", "description": "Marque construite par Matsumoku.",
             "matched_on": "vantage", "curated": True, "source": "manual"}

    def setUp(self):
        self.analyzer = _make_analyzer()
        t1_circuit_breaker.reset()
        self.addCleanup(t1_circuit_breaker.reset)
        for target, value in (("backend.analyzer.llm_usage.record", None), ("backend.analyzer.GEMINI_API_KEY", "dummy")):
            patcher = patch(target, value) if value else patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.analyzer._run_t1_shadow_observation = MagicMock(return_value={})

    def _enabled(self, fiches=None, version=5):
        stack = [
            patch("backend.analyzer.T1_KNOWLEDGE_ENABLED", True),
            patch("backend.pg_db.get_pool", return_value=MagicMock()),
            patch("backend.analyzer.guitar_knowledge.lookup", return_value=[self.FICHE] if fiches is None else fiches),
            patch("backend.analyzer.guitar_knowledge.effective_version", return_value=version),
            patch("backend.analyzer.guitar_knowledge.configure_version"),
        ]
        for p in stack:
            p.start()
            self.addCleanup(p.stop)

    def test_disabled_by_default_touches_no_database_and_leaves_the_prompt_unchanged(self):
        with patch("backend.pg_db.get_pool", side_effect=AssertionError("aucun accès base attendu")):
            self.assertEqual(self.analyzer._t1_knowledge(_listing()), ("", {}))
        self.assertEqual(
            self.analyzer._construct_t1_gatekeeper_prompt(_listing(), {}, "INSTRUCTION"),
            build_t1_gatekeeper_prompt(_listing(), {}, "INSTRUCTION"))

    def test_enabled_returns_block_and_trace_without_sources(self):
        self._enabled()
        block, trace = self.analyzer._t1_knowledge(_listing())
        self.assertIn("Vantage (brand)", block)
        self.assertNotIn("http", block)
        self.assertEqual(trace, {"gatekeeperKnowledge": {"version": 5, "fiches": ["manual:vantage"], "matched": ["vantage"]}})

    def test_no_match_means_no_block_and_no_trace(self):
        self._enabled(fiches=[])
        self.assertEqual(self.analyzer._t1_knowledge(_listing()), ("", {}))

    def test_fail_open_when_the_database_is_unavailable(self):
        with patch("backend.analyzer.T1_KNOWLEDGE_ENABLED", True), \
                patch("backend.pg_db.get_pool", side_effect=RuntimeError("pool non initialisé")):
            self.assertEqual(self.analyzer._t1_knowledge(_listing()), ("", {}))
        self.analyzer.logger.warning.assert_called()

    def test_prompt_order_knowledge_before_correction_and_annonce_stays_last(self):
        block = "CONNAISSANCES SUR LES MARQUES DÉTECTÉES : - Vantage"
        prompt = build_t1_gatekeeper_prompt(_listing(), {}, "INSTRUCTION", user_comment="CORR", knowledge_block=block)
        self.assertLess(prompt.index("INSTRUCTION"), prompt.index("CONNAISSANCES"))
        self.assertLess(prompt.index("CONNAISSANCES"), prompt.index("CORRECTION UTILISATEUR"))
        self.assertLess(prompt.index("CORRECTION UTILISATEUR"), prompt.index("<annonce>"))
        self.assertTrue(prompt.rstrip().endswith("</annonce>"))
        self.assertEqual(build_t1_gatekeeper_prompt(_listing(), {}, "I", knowledge_block="   "),
                         build_t1_gatekeeper_prompt(_listing(), {}, "I"))       # bloc vide = prompt inchangé

    def test_full_analysis_injects_into_the_real_prompt_and_stores_the_trace(self):
        self._enabled()
        self.analyzer._call_t1_provider = MagicMock(return_value=({"status": "REJECTED", "reason": "Pas une guitare."}, None))
        result = self.analyzer.analyze_deal(_listing(), firestore_config={"analysisConfig": {}})
        sent_prompt = self.analyzer._call_t1_provider.call_args[0][1]
        self.assertIn("Vantage (brand)", sent_prompt)
        self.assertTrue(sent_prompt.rstrip().endswith("</annonce>"))
        self.assertEqual(result["gatekeeperKnowledge"]["fiches"], ["manual:vantage"])
        self.assertEqual(result["gatekeeperKnowledge"]["version"], 5)

    def test_full_analysis_without_the_switch_stores_no_trace(self):
        self.analyzer._call_t1_provider = MagicMock(return_value=({"status": "REJECTED", "reason": "x"}, None))
        result = self.analyzer.analyze_deal(_listing(), firestore_config={"analysisConfig": {}})
        self.assertNotIn("gatekeeperKnowledge", result)
        self.assertNotIn("CONNAISSANCES", self.analyzer._call_t1_provider.call_args[0][1])


class TestCascadeCharacterization(unittest.TestCase):
    """Tests de CARACTÉRISATION de la cascade complète T1 -> T2 -> T3 via l'API publique `analyze_deal`
    (2026-10-02) : figent le comportement AVANT le découpage de `_run_analysis_cascade_body` en phases,
    pour qu'un refactoring sans changement de comportement reste vérifiable. Appels réseau mockés."""

    T1_ACCEPT = {"status": "FAIR", "reasoning": "Prix correct.", "brand": "Fender", "classification": "guitare.electrique"}

    def setUp(self):
        self.a = _make_analyzer()
        self.a._run_t1_shadow_observation = MagicMock(return_value={})
        self.a._download_and_optimize_image = MagicMock(return_value=None)
        self.a._call_t1_provider = MagicMock(return_value=(dict(self.T1_ACCEPT), None))
        self.t2 = {"verdict": "FAIR", "deal_score": 3, "authenticity_score": 9, "restoration_interest_score": 0,
                   "confidence": 0.9, "summary": "RAS"}
        self.t3 = {"verdict": "PEPITE", "deal_score": 9, "authenticity_score": 9, "confidence": 0.95, "summary": "Top"}
        self.gemini_calls = []

        def _gemini(model, parts, user_email=None, **kw):
            self.gemini_calls.append((model, kw.get("action"), parts))
            if kw.get("action") == "t2_analyst":
                return (dict(self.t2) if self.t2 is not None else None), self.t2_err
            return (dict(self.t3) if self.t3 is not None else None), self.t3_err
        self.t2_err = None
        self.t3_err = None
        self.a._call_gemini_json = _gemini
        t1_circuit_breaker.reset()
        self.addCleanup(t1_circuit_breaker.reset)
        for target, value in (("backend.analyzer.llm_usage.record", None), ):
            p = patch(target)
            p.start()
            self.addCleanup(p.stop)
        for p in (patch("backend.analyzer.GEMINI_API_KEY", "dummy"), patch("backend.analyzer.T1_PROVIDER_CHAIN", ["local"])):
            p.start()
            self.addCleanup(p.stop)

    def _run(self, config=None, **kw):
        return self.a.analyze_deal(_listing(), firestore_config={"analysisConfig": config or {}}, **kw)

    def _actions(self):
        return [c[1] for c in self.gemini_calls]

    def test_t1_rejection_stops_before_t2(self):
        self.a._call_t1_provider = MagicMock(return_value=({"status": "REJECTED_ITEM", "reasoning": "Étui seul", "brand": "X",
                                                            "classification": None}, None))
        r = self._run()
        self.assertEqual(r["verdict"], "REJECTED_ITEM")
        self.assertEqual(r["gatekeeperVerdict"], "REJECTED_ITEM")
        self.assertEqual(r["gatekeeperBrand"], "X")
        self.assertEqual(self.gemini_calls, [])

    def test_t2_only_when_expert_not_triggered(self):
        r = self._run()
        self.assertEqual(self._actions(), ["t2_analyst"])
        self.assertEqual(r["verdict"], "FAIR")
        self.assertEqual(r["gatekeeperVerdict"], "FAIR")
        self.assertEqual(r["gatekeeperBrand"], "Fender")
        self.assertEqual(r["gatekeeperClassification"], "guitare.electrique")
        self.assertNotIn("tier3_trigger", r)
        self.assertEqual(r["model_used"].count(" -> "), 1)  # portier -> analyste

    def test_expert_runs_and_overrides_t2_when_triggered(self):
        self.t2["deal_score"] = 9
        r = self._run()
        self.assertEqual(self._actions(), ["t2_analyst", "t3_expert"])
        self.assertEqual(r["verdict"], "PEPITE")
        self.assertIn("critique", r["tier3_trigger"])
        self.assertEqual(r["model_used"].count(" -> "), 2)  # portier -> analyste -> expert
        self.assertEqual(r["gatekeeperVerdict"], "FAIR")

    def test_t3_failure_raises(self):
        self.t2["deal_score"] = 9
        self.t3, self.t3_err = None, "boom"
        with self.assertRaises(RuntimeError):
            self._run()

    def test_t2_failure_returns_error_result_with_gatekeeper_status(self):
        self.t2, self.t2_err = None, "quota"
        r = self._run()
        self.assertEqual(r["verdict"], "FAIR")  # verdict du Portier conservé
        self.assertIn("Erreur Tier 2", r["reasoning"])
        self.assertIn("quota", r["reasoning"])
        self.assertTrue(r["model_used"].endswith("(Error)"))
        self.assertEqual(self._actions(), ["t2_analyst"])

    def test_force_expert_skips_t1_and_marks_manual_retry(self):
        r = self._run(force_expert=True)
        self.a._call_t1_provider.assert_not_called()
        self.assertEqual(self._actions(), ["t2_analyst", "t3_expert"])
        self.assertEqual(r["gatekeeperVerdict"], "MANUAL_RETRY")
        self.assertIn("forcée", r["tier3_trigger"])
        self.assertIsNone(r["gatekeeperBrand"])

    def test_active_search_not_matching_is_not_promoted(self):
        r = self._run(config={"activeSearchFamilies": ["amplificateur"]})
        self.assertEqual(r["verdict"], "NOT_PROMOTED")
        self.assertEqual(r["gatekeeperVerdict"], "FAIR")
        self.assertEqual(self.gemini_calls, [])

    def test_active_search_matching_continues_to_t2(self):
        r = self._run(config={"activeSearchFamilies": ["guitare.electrique"]})
        self.assertNotEqual(r["verdict"], "NOT_PROMOTED")
        self.assertEqual(self._actions(), ["t2_analyst"])

    def test_pepite_bypasses_active_search_filter(self):
        self.a._call_t1_provider = MagicMock(return_value=({**self.T1_ACCEPT, "status": "PEPITE"}, None))
        r = self._run(config={"activeSearchFamilies": ["amplificateur"]})
        self.assertNotEqual(r["verdict"], "NOT_PROMOTED")
        self.assertEqual(self._actions(), ["t2_analyst"])

    def test_gatekeeper_failure_skips_without_calling_gemini(self):
        self.a._call_t1_provider = MagicMock(return_value=(None, "panne"))
        r = self._run()
        self.assertEqual(r["verdict"], "GATEKEEPER_FAILED_SKIP")
        self.assertEqual(self.gemini_calls, [])

    def test_model_used_starts_with_the_t1_model_of_the_provider(self):
        from backend.llm_clients import T1_LOCAL_MODEL
        r = self._run()
        self.assertTrue(r["model_used"].startswith(T1_LOCAL_MODEL))

    def test_user_comment_reaches_t1_prompt_and_t2_prompt(self):
        self._run(user_comment="C'est une vraie Strat")
        t1_prompt = self.a._call_t1_provider.call_args[0][1]
        self.assertIn("C'est une vraie Strat", t1_prompt)
        self.assertLess(t1_prompt.index("CORRECTION UTILISATEUR"), t1_prompt.index("<annonce>"))
        t2_parts = self.gemini_calls[0][2]
        self.assertIn("C'est une vraie Strat", t2_parts[0])

    def test_custom_models_from_config_are_used(self):
        self.t2["deal_score"] = 9
        self._run(config={"mainModel": "m-analyst", "proModel": "m-expert"})
        self.assertEqual([c[0] for c in self.gemini_calls], ["m-analyst", "m-expert"])


class TestExpertTriggerReason(unittest.TestCase):
    """`expert_trigger_reason` : décision pure (extraite de la cascade le 2026-10-02) de déclencher
    l'Expert Pro après l'Analyste. Seuils par défaut : prix 1000, deal 8, combo 6+resto 7, auth 7,
    confiance 0.75 (config.py `DEFAULT_PRO_*`). Un résultat T2 « neutre » ne déclenche rien."""

    NEUTRAL = {"deal_score": 3, "authenticity_score": 9, "restoration_interest_score": 0,
               "confidence": 0.9, "verdict": "FAIR"}

    def _reason(self, price=100, config=None, force=False, **t2):
        from backend.analyzer import expert_trigger_reason
        return expert_trigger_reason(config or {}, {**self.NEUTRAL, **t2}, price, force)

    def test_neutral_result_does_not_trigger(self):
        self.assertIsNone(self._reason())

    def test_missing_scores_use_safe_defaults_and_do_not_trigger(self):
        from backend.analyzer import expert_trigger_reason
        self.assertIsNone(expert_trigger_reason({}, {}, 100, False))

    def test_force_always_triggers(self):
        self.assertIn("forcée", self._reason(force=True))

    def test_high_price_needs_a_decent_deal_score(self):
        self.assertIn("Prix élevé", self._reason(price=1500, deal_score=4))
        self.assertIsNone(self._reason(price=1500, deal_score=3))

    def test_price_equal_to_threshold_does_not_trigger(self):
        self.assertIsNone(self._reason(price=1000, deal_score=5))

    def test_critical_deal_score(self):
        self.assertIn("attractivité critique", self._reason(deal_score=8))
        self.assertIsNone(self._reason(deal_score=7))

    def test_jackpot_combo(self):
        self.assertIn("Combo Jackpot", self._reason(deal_score=6, restoration_interest_score=7))
        self.assertIsNone(self._reason(deal_score=6, restoration_interest_score=6))
        self.assertIsNone(self._reason(deal_score=5, restoration_interest_score=9))

    def test_low_authenticity(self):
        self.assertIn("authenticité", self._reason(authenticity_score=7))
        self.assertIsNone(self._reason(authenticity_score=8))

    def test_low_confidence(self):
        self.assertIn("Faible confiance", self._reason(confidence=0.7))
        self.assertIsNone(self._reason(confidence=0.75))

    def test_collection_verdict(self):
        self.assertIn("COLLECTION", self._reason(verdict="COLLECTION"))

    def test_first_matching_rule_wins(self):
        # prix élevé ET score critique ET authenticité douteuse : la règle du prix passe en premier
        self.assertIn("Prix élevé", self._reason(price=2000, deal_score=9, authenticity_score=1))
        # score critique avant authenticité douteuse
        self.assertIn("attractivité critique", self._reason(deal_score=9, authenticity_score=1))

    def test_thresholds_come_from_config(self):
        self.assertIn("attractivité critique", self._reason(deal_score=5, config={"proTriggerDealScoreThreshold": 5}))
        self.assertIsNone(self._reason(deal_score=8, config={"proTriggerDealScoreThreshold": 9}))


def _claude_response(text, stop_reason="end_turn", usage=(100, 0, 0, 200)):
    """Réponse Anthropic factice : un bloc de raisonnement (ignoré) puis un bloc texte."""
    response = MagicMock()
    response.content = [MagicMock(type="thinking", text="(ne doit pas être lu)"), MagicMock(type="text", text=text)]
    response.stop_reason = stop_reason
    inp, read, write, out = usage
    response.usage = MagicMock(input_tokens=inp, cache_read_input_tokens=read,
                               cache_creation_input_tokens=write, output_tokens=out)
    return response


class TestClaudeExpertProvider(unittest.TestCase):
    """Expert T3 via l'API Anthropic (`T3_PROVIDER=claude`, 2026-10-13) : appels réseau mockés."""

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

    def test_content_blocks_label_images_first_and_leave_originals_untouched(self):
        from PIL import Image
        big, small = Image.new("RGB", (3000, 2000)), Image.new("RGBA", (400, 300))
        with patch("backend.llm_clients.T3_CLAUDE_MAX_IMAGE_EDGE", 1568):
            blocks, count = self.a._claude_content_blocks(["PROMPT", big, small])
        self.assertEqual(count, 2)
        self.assertEqual([b["type"] for b in blocks], ["text", "image", "text", "image", "text"])
        self.assertEqual(blocks[0]["text"], "Image 1 :")
        self.assertEqual(blocks[1]["source"]["media_type"], "image/jpeg")
        self.assertIn("PROMPT", blocks[-1]["text"])
        self.assertIn("JSON", blocks[-1]["text"])
        # Les objets PIL partagés avec les autres tiers ne sont jamais modifiés en place.
        self.assertEqual(big.size, (3000, 2000))
        self.assertEqual(small.mode, "RGBA")
        import base64, io
        sent = Image.open(io.BytesIO(base64.b64decode(blocks[1]["source"]["data"])))
        self.assertEqual(max(sent.size), 1568)

    def test_success_parses_json_ignores_thinking_and_records_usage(self):
        self.client.messages.create.return_value = _claude_response('```json\n{"verdict": "PEPITE"}\n```',
                                                                   usage=(100, 50, 10, 200))
        result, err = self.a._call_claude_json("claude-sonnet-5-5", ["p"], action="t3_expert")
        self.assertIsNone(err)
        self.assertEqual(result, {"verdict": "PEPITE"})
        kwargs = self.client.messages.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-sonnet-5-5")
        self.assertEqual(kwargs["extra_body"], {"output_config": {"effort": "high"}})
        self.assertNotIn("temperature", kwargs)
        self.assertNotIn("thinking", kwargs)
        row = self.record.call_args.kwargs
        self.assertEqual(row["provider"], "anthropic")
        self.assertEqual(row["action"], "t3_expert")
        # Entrée = neuve + lecture cache + écriture cache (convention de la table), raisonnement déjà dans la sortie.
        self.assertEqual((row["input_tokens"], row["cached_tokens"], row["output_tokens"], row["thoughts_tokens"]),
                         (160, 50, 200, 0))
        self.assertNotIn("ok", row)

    def test_truncated_response_is_an_error_and_is_not_retried(self):
        self.client.messages.create.return_value = _claude_response('{"verdict": "PEP', stop_reason="max_tokens")
        result, err = self.a._call_claude_json("claude-sonnet-5-5", ["p"], max_retries=2)
        self.assertIsNone(result)
        self.assertIn("T3_CLAUDE_MAX_TOKENS", err)
        self.assertEqual(self.client.messages.create.call_count, 1)
        self.assertFalse(self.record.call_args.kwargs["ok"])
        self.assertEqual(self.record.call_args.kwargs["error_type"], "json")

    def test_invalid_json_retries_once_with_a_warning(self):
        self.client.messages.create.side_effect = [_claude_response("pas du json"), _claude_response('{"a": 1}')]
        result, err = self.a._call_claude_json("claude-sonnet-5-5", ["p"], max_retries=1)
        self.assertEqual((result, err), ({"a": 1}, None))
        self.assertEqual(self.client.messages.create.call_count, 2)
        first, second = [c.kwargs["messages"][0]["content"] for c in self.client.messages.create.call_args_list]
        self.assertEqual(len(second), len(first) + 1)
        self.assertIn("CRITICAL", second[-1]["text"])
        self.assertEqual([c.kwargs.get("ok", True) for c in self.record.call_args_list], [False, True])

    def test_object_is_extracted_from_surrounding_prose(self):
        self.client.messages.create.return_value = _claude_response('Voici le résultat : {"a": 1} Bonne journée.')
        self.assertEqual(self.a._call_claude_json("claude-sonnet-5-5", ["p"]), ({"a": 1}, None))

    def test_missing_api_key_fails_without_touching_the_network(self):
        with patch("backend.llm_clients.ANTHROPIC_API_KEY", None):
            result, err = self.a._call_claude_json("claude-sonnet-5-5", ["p"])
        self.assertIsNone(result)
        self.assertIn("ANTHROPIC_API_KEY", err)
        self.client.messages.create.assert_not_called()

    def test_api_error_is_returned_and_classified(self):
        class APITimeoutError(Exception):
            pass
        self.client.messages.create.side_effect = APITimeoutError("Request timed out.")
        result, err = self.a._call_claude_json("claude-sonnet-5-5", ["p"])
        self.assertIsNone(result)
        self.assertIn("timed out", err)
        self.assertEqual(self.record.call_args.kwargs["error_type"], "timeout")

    def _t3(self, provider, claude=None, gemini=None, base="base", cache=True):
        self.a._call_claude_json = claude or MagicMock(return_value=({"verdict": "PEPITE"}, None))
        self.a._call_gemini_json = gemini or MagicMock(return_value=({"verdict": "FAIR"}, None))
        chain = ["gemini-3.7-flash"]
        with patch("backend.analyzer.T3_PROVIDER", provider), patch("backend.analyzer.T3_CLAUDE_MODEL", "claude-sonnet-5-5"), \
                patch("backend.analyzer.T3_CLAUDE_CACHE", cache):
            result = self.a._run_t3_phase(base, [], {}, "gemini-3.1-pro-preview", None, chain,
                                          {"verdict": "FAIR", "summary": "RAS"}, "motif")
        return result

    # --- Cache de prompt : le préfixe statique va dans `system`, jamais le texte propre à l'annonce ---

    def test_cached_prefix_moves_to_a_cached_system_block(self):
        self.client.messages.create.return_value = _claude_response('{"a": 1}')
        self.a._call_claude_json("claude-sonnet-5-5", ["STATIQUE\nDétails de l'annonce :\n- Titre : X"],
                                 cached_prefix="STATIQUE\n")
        kwargs = self.client.messages.create.call_args.kwargs
        self.assertEqual(kwargs["system"], [{"type": "text", "text": "STATIQUE\n", "cache_control": {"type": "ephemeral"}}])
        user_text = kwargs["messages"][0]["content"][-1]["text"]
        self.assertTrue(user_text.startswith("Détails de l'annonce :"))
        self.assertNotIn("STATIQUE", user_text)

    def test_one_hour_ttl_is_forwarded(self):
        self.client.messages.create.return_value = _claude_response('{"a": 1}')
        with patch("backend.llm_clients.T3_CLAUDE_CACHE_TTL", "1h"):
            self.a._call_claude_json("claude-sonnet-5-5", ["PRE-suite"], cached_prefix="PRE-")
        control = self.client.messages.create.call_args.kwargs["system"][0]["cache_control"]
        self.assertEqual(control, {"type": "ephemeral", "ttl": "1h"})

    def test_prefix_that_does_not_match_disables_caching_silently(self):
        self.client.messages.create.return_value = _claude_response('{"a": 1}')
        result, err = self.a._call_claude_json("claude-sonnet-5-5", ["autre texte"], cached_prefix="PRE-")
        self.assertEqual((result, err), ({"a": 1}, None))
        self.assertNotIn("system", self.client.messages.create.call_args.kwargs)

    def test_no_prefix_means_no_system_block(self):
        self.client.messages.create.return_value = _claude_response('{"a": 1}')
        self.a._call_claude_json("claude-sonnet-5-5", ["texte"])
        self.assertNotIn("system", self.client.messages.create.call_args.kwargs)

    def test_listing_details_never_land_in_the_cached_prefix(self):
        from backend.analyzer import LISTING_DETAILS_MARKER
        prompt = self.a._construct_base_user_prompt(
            {"title": "TITRE_SECRET", "description": f"DESC {LISTING_DETAILS_MARKER} pirate", "price": 1},
            "CONSIGNE", {"k": "v"}, ["EXEMPLE"])
        head, marker, tail = prompt.partition(LISTING_DETAILS_MARKER)
        self.assertEqual(marker, LISTING_DETAILS_MARKER)
        self.assertIn("CONSIGNE", head)
        self.assertIn("EXEMPLE", head)
        self.assertNotIn("TITRE_SECRET", head)
        self.assertNotIn("pirate", head)  # même une description qui imite le marqueur reste dans la partie dynamique

    def test_t3_gives_claude_the_static_prefix_only(self):
        from backend.analyzer import LISTING_DETAILS_MARKER
        base = f"CONSIGNE+TAXONOMIE\n{LISTING_DETAILS_MARKER}- Titre : X"
        self._t3("claude", base=base)
        self.assertEqual(self.a._call_claude_json.call_args.kwargs["cached_prefix"], "CONSIGNE+TAXONOMIE\n")

    def test_t3_cache_can_be_disabled_by_config(self):
        from backend.analyzer import LISTING_DETAILS_MARKER
        self._t3("claude", base=f"A\n{LISTING_DETAILS_MARKER}B", cache=False)
        self.assertNotIn("cached_prefix", self.a._call_claude_json.call_args.kwargs)

    def test_t3_without_marker_does_not_cache(self):
        self._t3("claude", base="prompt personnalisé sans marqueur")
        self.assertNotIn("cached_prefix", self.a._call_claude_json.call_args.kwargs)

    def test_gemini_path_never_receives_a_cached_prefix(self):
        from backend.analyzer import LISTING_DETAILS_MARKER
        self._t3("gemini", base=f"A\n{LISTING_DETAILS_MARKER}B")
        self.assertNotIn("cached_prefix", self.a._call_gemini_json.call_args.kwargs)

    def test_t3_uses_claude_when_provider_is_claude(self):
        result = self._t3("claude")
        self.a._call_claude_json.assert_called_once()
        self.assertEqual(self.a._call_claude_json.call_args.args[0], "claude-sonnet-5-5")
        self.assertEqual(self.a._call_claude_json.call_args.kwargs["action"], "t3_expert")
        self.a._call_gemini_json.assert_not_called()
        self.assertEqual(result["model_used"], "gemini-3.7-flash -> claude-sonnet-5-5")

    def test_t3_stays_on_gemini_by_default(self):
        result = self._t3("gemini")
        self.a._call_gemini_json.assert_called_once()
        self.assertEqual(self.a._call_gemini_json.call_args.args[0], "gemini-3.1-pro-preview")
        self.a._call_claude_json.assert_not_called()
        self.assertEqual(result["model_used"], "gemini-3.7-flash -> gemini-3.1-pro-preview")

    def test_t3_claude_failure_raises_without_falling_back_to_gemini(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._t3("claude", claude=MagicMock(return_value=(None, "boom")))
        self.assertIn("claude-sonnet-5-5", str(ctx.exception))
        self.a._call_gemini_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
