"""Tests de la mesure d'effet de la base sur le Portier (backend/scripts/compare_knowledge_effect.py) et de l'aide
d'injection du rejeu (compare_qwen_local_vs_prod.knowledge_for) — sans base, réseau ni IA."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("APP_ID_TARGET", "test")
os.environ.setdefault("USER_IDS_TARGET", "test_user")

from backend.scripts import compare_knowledge_effect as cke


def entry(i, local, cloud="FAIR", kb=()):
    return {"id": i, "title": f"annonce {i}", "link": f"https://x/{i}", "cloud_verdict": cloud, "local_verdict": local,
            "local_reasoning": "raison", "kb_ids": [f"k{n}" for n in kb], "kb_names": [f"Marque{n}" for n in kb]}


def by_id(*entries):
    return {e["id"]: e for e in entries}


class TestAnalyze(unittest.TestCase):
    def test_new_rejection_where_kb_was_injected_fails_the_criterion(self):
        baseline = by_id(entry("a", "FAIR"), entry("b", "FAIR"), entry("c", "REJECTED_ITEM"))
        with_kb = by_id(entry("a", "REJECTED_ITEM", kb=[1]), entry("b", "FAIR"), entry("c", "FAIR", kb=[2]))
        report = cke.analyze(baseline, with_kb)
        self.assertEqual(report["new_rejections"], ["a"])
        self.assertEqual(report["new_rejections_injected"], ["a"])
        self.assertEqual(report["lifted_rejections"], ["c"])
        self.assertFalse(report["passes"])

    def test_new_rejection_without_injection_is_noise_not_a_failure(self):
        baseline = by_id(entry("a", "FAIR"), entry("b", "FAIR"))
        with_kb = by_id(entry("a", "REJECTED_ITEM"), entry("b", "FAIR", kb=[1]))     # a : aucune fiche injectée
        report = cke.analyze(baseline, with_kb)
        self.assertEqual((report["new_rejections"], report["new_rejections_injected"]), (["a"], []))
        self.assertTrue(report["passes"])

    def test_noise_floor_from_a_second_baseline(self):
        base1 = by_id(entry("a", "FAIR"), entry("b", "FAIR"), entry("c", "REJECTED_ITEM"))
        base2 = by_id(entry("a", "REJECTED_ITEM"), entry("b", "FAIR"), entry("c", "REJECTED_ITEM"))
        report = cke.analyze(base1, base1, base2)
        self.assertEqual(report["noise_flips"], ["a"])
        self.assertEqual(report["n_noise_common"], 3)

    def test_agreement_with_cloud_on_injected_listings(self):
        baseline = by_id(entry("a", "REJECTED_ITEM", cloud="FAIR"), entry("b", "FAIR", cloud="FAIR"))
        with_kb = by_id(entry("a", "FAIR", cloud="FAIR", kb=[1]), entry("b", "FAIR", cloud="FAIR", kb=[2]))
        report = cke.analyze(baseline, with_kb)
        self.assertEqual(report["agreement_baseline_injected"], 0.5)     # a en désaccord, b d'accord
        self.assertEqual(report["agreement_with_kb_injected"], 1.0)

    def test_only_common_listings_are_compared(self):
        report = cke.analyze(by_id(entry("a", "FAIR"), entry("z", "FAIR")), by_id(entry("a", "FAIR", kb=[1]), entry("y", "FAIR")))
        self.assertEqual((report["n_common"], report["n_injected"]), (1, 1))

    def test_report_prints_validation_command_only_when_it_passes(self):
        def render(passes):
            baseline = by_id(entry("a", "FAIR"))
            with_kb = by_id(entry("a", "REJECTED_ITEM" if not passes else "FAIR", kb=[1]))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cke.print_report(cke.analyze(baseline, with_kb), baseline, with_kb, kb_version=7)
            return buf.getvalue()
        ok, ko = render(True), render(False)
        self.assertIn("UPDATE guitar_knowledge_versions SET validated = true WHERE version = 7", ok)
        self.assertNotIn("UPDATE guitar_knowledge_versions", ko)
        self.assertIn("NON tenu", ko)
        self.assertIn("NOUVEAUX REJETS À EXAMINER", ko)


class TestMainOnFiles(unittest.TestCase):
    def _write(self, tmp, name, listings, **meta):
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"model": "qwen3-vl:8b-instruct", "per_listing": listings, **meta}, fh)
        return path

    def _run(self, *argv):
        with patch("sys.argv", ["cke", *argv]), contextlib.redirect_stdout(io.StringIO()):
            return cke.main()

    def test_exit_code_reflects_the_criterion(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write(tmp, "b.json", [entry("a", "FAIR")], with_knowledge=False)
            good = self._write(tmp, "g.json", [entry("a", "FAIR", kb=[1])], with_knowledge=True, kb_version=3)
            bad = self._write(tmp, "x.json", [entry("a", "REJECTED_ITEM", kb=[1])], with_knowledge=True, kb_version=3)
            self.assertEqual(self._run("--baseline", base, "--with-kb", good), 0)
            self.assertEqual(self._run("--baseline", base, "--with-kb", bad), 1)

    def test_refuses_inconsistent_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = self._write(tmp, "p.json", [entry("a", "FAIR")], with_knowledge=False)
            kb = self._write(tmp, "k.json", [entry("a", "FAIR", kb=[1])], with_knowledge=True)
            with self.assertRaises(SystemExit):
                self._run("--baseline", kb, "--with-kb", kb)          # référence produite AVEC la base
            with self.assertRaises(SystemExit):
                self._run("--baseline", plain, "--with-kb", plain)    # rejeu « avec » produit sans --with-knowledge
            old = os.path.join(tmp, "old.json")
            with open(old, "w", encoding="utf-8") as fh:
                json.dump({"model": "m"}, fh)                          # ancien format, sans per_listing
            with self.assertRaises(SystemExit):
                self._run("--baseline", old, "--with-kb", kb)


class TestRunQualityGuards(unittest.TestCase):
    def _file(self, tmp, **data):
        path = os.path.join(tmp, "r.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"model": "qwen3-vl:8b-instruct", "per_listing": [entry("a", "FAIR")], **data}, fh)
        return path

    def test_thinking_variant_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                cke.load(self._file(tmp, model="qwen3-vl:8b"))
            self.assertIn("THINKING", str(ctx.exception))
            cke.load(self._file(tmp))                                     # l'instruct passe

    def test_high_failure_rate_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            failed = [{"id": f"f{i}"} for i in range(3)]                 # 3 échecs pour 1 réussite
            with self.assertRaises(SystemExit) as ctx:
                cke.load(self._file(tmp, failed_calls=failed))
            self.assertIn("inexploitables", str(ctx.exception))
            cke.load(self._file(tmp, per_listing=[entry(str(i), "FAIR") for i in range(20)], failed_calls=failed[:1]))

    def test_replay_default_model_is_the_production_model(self):
        """Constaté le 2026-10-01 : un rejeu lancé sans --model utilisait le tag Thinking (réponses vides)."""
        from backend.scripts import compare_qwen_local_vs_prod as replay
        import config
        self.assertEqual(replay.QWEN_LOCAL_MODEL, config.T1_LOCAL_MODEL)
        self.assertNotEqual(replay.QWEN_LOCAL_MODEL, cke.THINKING_TAG)


class TestReplayKnowledgeHelper(unittest.TestCase):
    def test_knowledge_for_returns_the_prompt_block_and_the_fiches(self):
        from backend.scripts import compare_qwen_local_vs_prod as replay
        fiche = {"id": "manual:vantage", "name": "Vantage", "kind": "brand", "description": "Marque.", "curated": True,
                 "source": "manual", "matched_on": "vantage"}
        with patch.object(replay.guitar_knowledge, "lookup", return_value=[fiche]) as lookup:
            block, fiches = replay.knowledge_for(object(), {"title": "Guitare Vantage", "description": "1979"}, limit=3)
        self.assertEqual(lookup.call_args.kwargs["limit"], 3)
        self.assertIn("Vantage (brand)", block)
        self.assertEqual(fiches, [fiche])
        with patch.object(replay.guitar_knowledge, "lookup", return_value=[]):
            self.assertEqual(replay.knowledge_for(object(), {"title": "x"}), ("", []))


if __name__ == "__main__":
    unittest.main()
