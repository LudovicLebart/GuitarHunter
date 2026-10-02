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


if __name__ == "__main__":
    unittest.main()
