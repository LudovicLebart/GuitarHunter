"""Tests pour le pipeline de décision de `DealAnalyzer` (backend/analyzer.py).

Périmètre volontairement restreint au changement du 2026-09-24 : un échec du Portier T1
réel (appel raté OU réponse malformée) ne doit plus fail-open vers l'Analyste (T2) — voir
`_run_analysis_cascade_body`/`T1_ERROR_STATUSES`. Le reste de la cascade (rejet T1, routage
Chantier G, Tier 2/3) n'est pas couvert ici.
"""
import threading
import unittest
from unittest.mock import MagicMock

from backend.analyzer import DealAnalyzer


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

    def test_t1_normal_rejection_is_unaffected(self):
        """Garde-fou anti-régression : un verdict normal (Portier opérationnel) suit
        toujours son chemin existant (ici : rejet), pas le nouveau skip."""
        self.analyzer._call_t1_provider = MagicMock(return_value=({"status": "REJECTED", "reason": "Pas une guitare."}, None))

        result = self.analyzer.analyze_deal(_listing(), firestore_config={"analysisConfig": {}})

        self.assertEqual(result["verdict"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
