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


def entry(i, local, cloud="FAIR", kb=(), final=None, reclassified=False):
    e = {"id": i, "title": f"annonce {i}", "link": f"https://x/{i}", "cloud_verdict": cloud, "local_verdict": local,
         "local_reasoning": "raison", "kb_ids": [f"k{n}" for n in kb], "kb_names": [f"Marque{n}" for n in kb]}
    if final is not None:
        e["final_verdict"] = final
    if reclassified:
        e["reclassified"] = True
    return e


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

    def test_new_rejection_confirmed_by_cloud_is_not_harmful(self):
        """Cas Art & Lutherie (2026-10-01) : accepté sans base, rejeté avec, et le cloud rejette aussi."""
        baseline = by_id(entry("a", "FAIR", cloud="REJECTED_SERVICE"))
        with_kb = by_id(entry("a", "REJECTED_ITEM", cloud="REJECTED_SERVICE", kb=[1]))
        report = cke.analyze(baseline, with_kb)
        self.assertEqual((report["neutral_new_injected"], report["harmful_new_injected"]), (["a"], []))
        self.assertTrue(report["passes"])

    def test_harmful_rejections_are_tolerated_up_to_the_noise_on_the_same_listings(self):
        base1 = by_id(entry("a", "FAIR"), entry("b", "FAIR"), entry("c", "FAIR"))
        base2 = by_id(entry("a", "REJECTED_ITEM"), entry("b", "FAIR"), entry("c", "FAIR"))   # bruit : a bascule seul
        one = by_id(entry("a", "FAIR", kb=[1]), entry("b", "REJECTED_ITEM", kb=[2]), entry("c", "FAIR", kb=[3]))
        two = by_id(entry("a", "FAIR", kb=[1]), entry("b", "REJECTED_ITEM", kb=[2]), entry("c", "REJECTED_ITEM", kb=[3]))
        r1 = cke.analyze(base1, one, base2)
        self.assertEqual((r1["noise_harmful_injected"], r1["harmful_new_injected"]), (["a"], ["b"]))
        self.assertTrue(r1["passes"])                       # 1 rejet nuisible avec base <= 1 de bruit
        r2 = cke.analyze(base1, two, base2)
        self.assertEqual(len(r2["harmful_new_injected"]), 2)
        self.assertFalse(r2["passes"])                      # 2 > 1
        self.assertFalse(cke.analyze(base1, one)["passes"])  # sans 2e rejeu : seuil 0

    def test_noise_outside_injected_listings_does_not_raise_the_threshold(self):
        base1 = by_id(entry("a", "FAIR"), entry("z", "FAIR"))
        base2 = by_id(entry("a", "FAIR"), entry("z", "REJECTED_ITEM"))                      # bruit sur z, où rien n'est injecté
        with_kb = by_id(entry("a", "REJECTED_ITEM", kb=[1]), entry("z", "FAIR"))
        report = cke.analyze(base1, with_kb, base2)
        self.assertEqual(report["noise_harmful_injected"], [])
        self.assertFalse(report["passes"])

    def test_real_gains_count_only_where_cloud_did_not_reject(self):
        baseline = by_id(entry("a", "REJECTED_ITEM", cloud="FAIR"), entry("b", "REJECTED_ITEM", cloud="REJECTED_ITEM"))
        with_kb = by_id(entry("a", "FAIR", cloud="FAIR", kb=[1]), entry("b", "FAIR", cloud="REJECTED_ITEM", kb=[2]))
        self.assertEqual(cke.analyze(baseline, with_kb)["gains_injected"], ["a"])

    def test_final_verdict_is_the_reference_when_it_judges_the_listing(self):
        """T1 avait accepté, T2/T3 ont jugé « BAD_DEAL » : rejeter avec la base n'est pas une erreur."""
        baseline = by_id(entry("a", "FAIR", cloud="FAIR", final="BAD_DEAL"))
        with_kb = by_id(entry("a", "REJECTED_ITEM", cloud="FAIR", final="BAD_DEAL", kb=[1]))
        self.assertEqual(cke.analyze(baseline, with_kb)["harmful_new_injected"], [])
        # et inversement : T1 avait « rejeté » mais le verdict final est bon → le rejeter est une erreur
        baseline = by_id(entry("b", "FAIR", cloud="BAD_DEAL", final="FAIR"))
        with_kb = by_id(entry("b", "BAD_DEAL", cloud="BAD_DEAL", final="FAIR", kb=[1]))
        self.assertEqual(cke.analyze(baseline, with_kb)["harmful_new_injected"], ["b"])

    def test_non_judging_final_verdicts_fall_back_to_t1(self):
        for final in ("NOT_PROMOTED", "MANUAL_RETRY", "ERROR_GATEKEEPER", "", None):
            self.assertTrue(cke.reference_rejected(entry("a", "FAIR", cloud="REJECTED_ITEM", final=final)))
            self.assertFalse(cke.reference_rejected(entry("a", "FAIR", cloud="FAIR", final=final)))
        self.assertTrue(cke.is_rejected("REJECTED"))        # ancien verdict

    def test_reclassified_section_counts_rescued_false_rejections(self):
        base1 = by_id(entry("a", "BAD_DEAL", cloud="BAD_DEAL", final="FAIR", reclassified=True),
                      entry("b", "BAD_DEAL", cloud="BAD_DEAL", final="FAIR", reclassified=True),
                      entry("c", "FAIR", cloud="BAD_DEAL", final="FAIR", reclassified=True))
        base2 = by_id(entry("a", "BAD_DEAL", cloud="BAD_DEAL", final="FAIR", reclassified=True),
                      entry("b", "FAIR", cloud="BAD_DEAL", final="FAIR", reclassified=True),
                      entry("c", "FAIR", cloud="BAD_DEAL", final="FAIR", reclassified=True))
        with_kb = by_id(entry("a", "FAIR", cloud="BAD_DEAL", final="FAIR", reclassified=True, kb=[1]),
                        entry("b", "BAD_DEAL", cloud="BAD_DEAL", final="FAIR", reclassified=True),
                        entry("c", "FAIR", cloud="BAD_DEAL", final="FAIR", reclassified=True))
        rc = cke.analyze(base1, with_kb, base2)["reclassified"]
        self.assertEqual(rc["ids"], ["a", "b", "c"])
        self.assertEqual(rc["rejected_without"], ["a", "b"])
        self.assertEqual(rc["rejected_with"], ["b"])
        self.assertEqual(rc["saved"], ["a"])
        self.assertEqual(rc["n_injected"], 1)
        self.assertEqual(rc["rejected_without_2"], ["a"])

    def test_reclassified_report_warns_when_nothing_is_rejected_without_the_base(self):
        baseline = by_id(entry("a", "FAIR", cloud="BAD_DEAL", final="FAIR", reclassified=True))
        with_kb = by_id(entry("a", "FAIR", cloud="BAD_DEAL", final="FAIR", reclassified=True, kb=[1]))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cke.print_report(cke.analyze(baseline, with_kb), baseline, with_kb)
        out = buf.getvalue()
        self.assertIn("FAUX REJETS PRÉSUMÉS", out)
        self.assertIn("PAS mesurable", out)
        self.assertIn("pré-filtre de prix", out)

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
        self.assertIn("REJETS NUISIBLES AVEC FICHES", ko)


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


class TestSamplingConsistency(unittest.TestCase):
    def test_runs_with_different_sampling_cannot_be_compared(self):
        cke.check_same_sampling([("a", {"temperature": 0, "seed": 42}), ("b", {"temperature": 0, "seed": 42})])
        cke.check_same_sampling([("a", {}), ("b", {})])                                  # anciens JSON entre eux : ok
        for other in ({"temperature": 0.8, "seed": 42}, {"temperature": 0, "seed": 7}, {}):
            with self.assertRaises(SystemExit) as ctx:
                cke.check_same_sampling([("a", {"temperature": 0, "seed": 42}), ("b", other)])
            self.assertIn("échantillonnage", str(ctx.exception))

    def test_replay_sampling_options(self):
        from backend.scripts import compare_qwen_local_vs_prod as replay
        self.assertEqual(replay._sampling_options(None, None), {})
        self.assertEqual(replay._sampling_options(0.0, 42), {"temperature": 0.0, "seed": 42})
        self.assertEqual(replay._sampling_options(0.0, None), {"temperature": 0.0})


class TestReplayCallsCarrySampling(unittest.TestCase):
    """La température et la graine demandées doivent réellement partir vers Ollama, dans les deux chemins d'appel."""

    def test_openai_compat_path_sends_temperature_and_seed(self):
        from backend.scripts import compare_qwen_local_vs_prod as replay
        seen = {}

        class FakeCompletions:
            def create(self, **kw):
                seen.update(kw)
                raise RuntimeError("stop")            # la fonction ne lève jamais : renvoie une erreur

        class FakeClient:
            def __init__(self, *a, **k):
                self.chat = type("C", (), {"completions": FakeCompletions()})()

        with patch.object(replay, "OpenAI", FakeClient):
            replay._call_qwen_local_json("p", [], "m", temperature=0.0, seed=42)
            self.assertEqual(seen["extra_body"]["options"]["temperature"], 0.0)
            self.assertEqual(seen["extra_body"]["options"]["seed"], 42)
            seen.clear()
            replay._call_qwen_local_json("p", [], "m")                       # défaut : aucun réglage ajouté
            self.assertNotIn("temperature", seen["extra_body"]["options"])
            self.assertNotIn("seed", seen["extra_body"]["options"])

    def test_native_path_sends_temperature_and_seed(self):
        from backend.scripts import compare_qwen_local_vs_prod as replay
        seen = {}

        def fake_post(url, json=None, timeout=None):
            seen.update(json)
            raise RuntimeError("stop")

        with patch.object(replay.requests, "post", fake_post):
            replay._call_qwen_local_json_native("p", [], "m", temperature=0.0, seed=7)
        self.assertEqual((seen["options"]["temperature"], seen["options"]["seed"]), (0.0, 7))


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
