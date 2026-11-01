"""Tests des alertes « modèle injoignable » (`model_alerts.py`) : causes à traiter, pannes répétées, limitation, branchements."""
import unittest
from unittest.mock import patch

from backend.api import model_alerts


class TestModelAlerts(unittest.TestCase):
    def setUp(self):
        model_alerts.reset()
        self.sent = []
        self.patches = [
            patch.object(model_alerts, "send_ntfy", lambda topic, title, message: self.sent.append((title, message))),
            patch.object(model_alerts, "_spawn", lambda target, args: target(*args)),
            patch.dict("os.environ", {"NTFY_TOPIC": "topic-test", "MODEL_ALERTS_TEST": "1"}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        model_alerts.reset()

    def test_classify(self):
        c = model_alerts.classify
        self.assertEqual(c("no_key"), ("action", "no_key"))
        self.assertEqual(c("no_credit"), ("action", "no_credit"))
        self.assertEqual(c("http_401"), ("action", "auth"))
        self.assertEqual(c("http_403"), ("action", "auth"))
        self.assertEqual(c("http_404"), ("action", "model_unavailable"))
        self.assertEqual(c("model_unavailable"), ("action", "model_unavailable"))
        self.assertEqual(c("timeout"), ("transient", "timeout"))
        self.assertEqual(c("http_529"), ("transient", "http_529"))
        self.assertEqual(c("connection"), ("transient", "connection"))
        self.assertIsNone(c("connection", source="browser"))  # coupure du navigateur de l'utilisateur, pas du modèle
        for ignored in ("json", "other", "cancelled", "http_400", None, ""):
            self.assertIsNone(c(ignored), ignored)

    def test_each_action_cause_alerts_immediately_with_the_advice(self):
        for cause, word in (("no_key", "Clé API absente"), ("no_credit", "recharger"), ("http_403", "Clé refusée"),
                            ("http_404", "Modèle retiré")):
            title = model_alerts.report_failure("anthropic", "claude-sonnet-5-5", cause, now=1000.0)
            self.assertIsNotNone(title, cause)
            self.assertIn("claude-sonnet-5-5", title)
        messages = " | ".join(m for _t, m in self.sent)
        for word in ("Clé API absente", "recharger", "Clé refusée", "Modèle retiré"):
            self.assertIn(word, messages)

    def test_action_alert_is_limited_to_once_a_day_per_model_and_cause(self):
        self.assertIsNotNone(model_alerts.report_failure("anthropic", "m", "no_key", now=0.0))
        self.assertIsNone(model_alerts.report_failure("anthropic", "m", "no_key", now=3600.0))
        self.assertIsNotNone(model_alerts.report_failure("anthropic", "m", "no_credit", now=3600.0))  # autre cause
        self.assertIsNotNone(model_alerts.report_failure("gemini", "m", "no_key", now=3600.0))  # autre fournisseur
        self.assertIsNotNone(model_alerts.report_failure("anthropic", "m", "no_key", now=86400.0 + 1))

    def test_transient_failures_alert_only_when_they_repeat_and_then_hourly(self):
        for i in range(model_alerts.BURST_COUNT - 1):
            self.assertIsNone(model_alerts.report_failure("local", "qwen", "connection", now=i * 10.0))
        self.assertIsNotNone(model_alerts.report_failure("local", "qwen", "connection", now=60.0))  # 5e échec en 15 min
        self.assertIsNone(model_alerts.report_failure("local", "qwen", "timeout", now=70.0))  # limitation d'une heure
        self.assertIn("instable", self.sent[0][0])

    def test_spread_out_failures_do_not_alert(self):
        for i in range(10):
            self.assertIsNone(model_alerts.report_failure("gemini", "m", "http_503", now=i * 600.0))  # 1 toutes les 10 min

    def test_no_topic_sends_nothing_and_never_raises(self):
        with patch.dict("os.environ", {"NTFY_TOPIC": ""}):
            model_alerts.report_failure("anthropic", "m", "no_key", now=0.0)
        self.assertEqual(self.sent, [])

    def test_robot_failures_are_reported_even_when_the_database_is_down(self):
        from backend import llm_usage
        with patch.object(llm_usage, "_disabled", True):
            llm_usage.record(provider="anthropic", model="claude-sonnet-5-5", action="t3_expert", ok=False, error_type="no_key")
        self.assertEqual(len(self.sent), 1)

    def test_pytest_guard_blocks_alerts_of_unrelated_tests(self):
        with patch.dict("os.environ", {"PYTEST_CURRENT_TEST": "x"}), patch.dict("os.environ", {"MODEL_ALERTS_TEST": ""}):
            self.assertIsNone(model_alerts.report_failure("anthropic", "m", "no_key", now=0.0))


if __name__ == "__main__":
    unittest.main()
