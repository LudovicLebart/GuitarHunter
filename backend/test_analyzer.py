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

from backend import t1_circuit_breaker
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


class TestT1UsageProviderLabel(unittest.TestCase):
    def test_failure_labels_match_success_labels(self):
        self.assertEqual(DealAnalyzer._t1_usage_provider_for("local"), "local")
        self.assertEqual(DealAnalyzer._t1_usage_provider_for("qwen"), "tokenrouter")
        self.assertEqual(DealAnalyzer._t1_usage_provider_for("gemini"), "gemini")

    @patch("backend.analyzer.llm_usage.record")
    @patch("backend.analyzer.OpenAI")
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
    @patch("backend.analyzer.OpenAI")
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


if __name__ == "__main__":
    unittest.main()
