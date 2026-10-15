"""Rejeu apparié du Portier : statistiques, critères fixés d'avance, reprise après coupure, fidélité à la prod."""
import json
import os
import random
import types
import unittest

from backend.scripts import t1_kb_paired_replay as rp


def _rows(stage, arm, stratum, ids, rates, reps):
    """Lignes de résultats : pour chaque annonce, `reps` répétitions dont une part `rate` rejetée."""
    out = []
    for i in ids:
        k = round(rates * reps)
        for rep in range(reps):
            rejected = rep < k
            out.append({"id": i, "stratum": stratum, "arm": arm, "rep": rep, "stage": stage,
                        "verdict": "REJECTED_ITEM" if rejected else "GOOD_DEAL", "rejected": rejected})
    return out


def _plan(a_ids, b_ids):
    return {"listings": [{"id": i, "stratum": "A", "kb_with": ["k1"], "kb_photo": ["k1"]} for i in a_ids] +
                        [{"id": i, "stratum": "B", "kb_with": ["k1"], "kb_photo": ["k1"]} for i in b_ids]}


class TestStats(unittest.TestCase):
    def test_bootstrap_ci_brackets_a_constant_and_a_noisy_mean(self):
        lo, hi = rp.bootstrap_ci([0.2] * 30)
        self.assertAlmostEqual(lo, 0.2)
        self.assertAlmostEqual(hi, 0.2)
        rng = random.Random(3)
        noisy = [rng.choice([0.0, 0.4]) for _ in range(60)]
        lo, hi = rp.bootstrap_ci(noisy)
        self.assertLess(lo, rp.mean(noisy))
        self.assertGreater(hi, rp.mean(noisy))

    def test_sign_flip_is_small_for_a_consistent_gain_and_large_for_noise(self):
        self.assertLess(rp.sign_flip_p([0.3] * 25), 0.001)
        self.assertGreater(rp.sign_flip_p([0.3, -0.3] * 10), 0.5)
        self.assertEqual(rp.sign_flip_p([0.0] * 5), 1.0)

    def test_placebo_splits_repetitions_by_parity(self):
        rows = [{"id": "a", "arm": "without", "rep": r, "verdict": "x", "rejected": r % 2 == 0} for r in range(10)]
        self.assertEqual(rp.placebo(rows, {"a"}), [-1.0])      # paires rejetées, impaires non : écart -1


class TestCriteria(unittest.TestCase):
    A = [f"a{i}" for i in range(30)]
    B = [f"b{i}" for i in range(40)]

    def _results(self, a_with_rate, b_with_rate, a_without=0.6, b_without=0.0, screen=0.6):
        r = _rows("screen", "without", "A", self.A, screen, 5)
        r += _rows("eval", "without", "A", self.A, a_without, 10) + _rows("eval", "with", "A", self.A, a_with_rate, 10)
        r += _rows("eval", "without", "B", self.B, b_without, 5) + _rows("eval", "with", "B", self.B, b_with_rate, 5)
        return r

    def test_clear_gain_without_regression_is_demonstrated(self):
        rep = rp.analyze(_plan(self.A, self.B), self._results(0.2, 0.0))
        self.assertEqual(rep["verdict"], "GAIN DÉMONTRÉ ET SANS RÉGRESSION")
        self.assertAlmostEqual(rep["A_with"]["mean_pts"], 40.0)

    def test_no_effect_with_enough_data_excludes_a_15_point_gain(self):
        rep = rp.analyze(_plan(self.A, self.B), self._results(0.6, 0.0))
        self.assertEqual(rep["verdict"], "GAIN D'AU MOINS 15 POINTS EXCLU")

    def test_gain_with_regression_in_B_is_flagged(self):
        rep = rp.analyze(_plan(self.A, self.B), self._results(0.2, 0.2))
        self.assertEqual(rep["verdict"], "GAIN MAIS RÉGRESSION POSSIBLE EN B")

    def test_too_few_A_listings_is_inconclusive_whatever_the_numbers(self):
        a = self.A[:10]
        r = _rows("screen", "without", "A", a, 0.6, 5) + _rows("eval", "without", "A", a, 0.6, 10) + \
            _rows("eval", "with", "A", a, 0.0, 10)
        rep = rp.analyze(_plan(a, []), r)
        self.assertEqual(rep["verdict"], "NON CONCLUANT")
        self.assertTrue(any("puissance" in p for p in rep["problems"]))

    def test_listings_the_model_already_accepts_are_screened_out(self):
        r = _rows("screen", "without", "A", self.A, 0.0, 5)       # rien n'est rejeté sans base : rien à sauver
        self.assertEqual(rp.select_screened(r, self.A), [])
        self.assertEqual(len(rp.select_screened(_rows("screen", "without", "A", self.A, 0.4, 5), self.A)), 30)

    def test_effect_is_measured_on_eval_repetitions_not_the_screening_ones(self):
        # dépistage : 100 % rejeté ; évaluation : 50 % avec comme sans -> aucun gain malgré le dépistage extrême
        rep = rp.analyze(_plan(self.A, self.B), self._results(0.5, 0.0, a_without=0.5, screen=1.0))
        self.assertAlmostEqual(rep["A_with"]["mean_pts"], 0.0)

    def test_failed_calls_over_the_tolerance_make_the_result_inconclusive(self):
        r = self._results(0.2, 0.0)
        for x in r[:len(r) // 3]:
            if x["arm"] == "with":
                x["verdict"] = None
        for x in r:
            if x["arm"] == "with" and x["stratum"] == "A":
                x["verdict"] = None
        rep = rp.analyze(_plan(self.A, self.B), r)
        self.assertEqual(rep["verdict"], "NON CONCLUANT")


class TestResume(unittest.TestCase):
    def test_done_calls_are_skipped_and_failures_are_retried(self):
        plan = _plan(["a1"], ["b1"])
        screen = _rows("screen", "without", "A", ["a1"], 1.0, 5)
        jobs = rp.jobs_for(plan, screen, "eval", 5, 2, 2)
        self.assertEqual({(j[0], j[2]) for j in jobs}, {("a1", "without"), ("a1", "with"), ("b1", "without"), ("b1", "with")})
        done = [{"id": "b1", "arm": "with", "rep": 0, "stage": "eval", "verdict": "GOOD_DEAL", "rejected": False},
                {"id": "b1", "arm": "without", "rep": 0, "stage": "eval", "verdict": None, "rejected": False}]
        again = rp.jobs_for(plan, screen + done, "eval", 5, 2, 2)
        self.assertNotIn(("b1", "with", 0), {(j[0], j[2], j[3]) for j in again})
        self.assertIn(("b1", "without", 0), {(j[0], j[2], j[3]) for j in again})

    def test_photo_arm_only_runs_when_the_photo_text_changes_the_fiches(self):
        plan = {"listings": [{"id": "a1", "stratum": "A", "kb_with": ["k1"], "kb_photo": ["k1"]},
                             {"id": "a2", "stratum": "A", "kb_with": ["k1"], "kb_photo": ["k1", "k2"]}]}
        screen = _rows("screen", "without", "A", ["a1", "a2"], 1.0, 5)
        arms = {(j[0], j[2]) for j in rp.jobs_for(plan, screen, "eval", 5, 2, 2)}
        self.assertNotIn(("a1", "photo"), arms)
        self.assertIn(("a2", "photo"), arms)

    def test_arms_are_interleaved_per_repetition(self):
        plan = _plan(["a1"], [])
        screen = _rows("screen", "without", "A", ["a1"], 1.0, 5)
        jobs = rp.jobs_for(plan, screen, "eval", 5, 3, 3)
        self.assertEqual([j[3] for j in jobs], sorted(j[3] for j in jobs))      # répétition 0 complète avant la 1


class TestFidelity(unittest.TestCase):
    def _cq(self, **kw):
        base = dict(MAX_IMAGES=8, QWEN_LOCAL_FIT_BUDGET=True, QWEN_LOCAL_NUM_CTX=8192, QWEN_LOCAL_MODEL="qwen3-vl:8b-instruct")
        base.update(kw)
        return types.SimpleNamespace(**base)

    def test_prod_conditions_pass(self):
        self.assertEqual(rp.check_fidelity(self._cq(), False), [])

    def test_non_prod_conditions_are_refused_unless_explicitly_allowed(self):
        for bad in ({"MAX_IMAGES": 4}, {"QWEN_LOCAL_FIT_BUDGET": False}, {"QWEN_LOCAL_NUM_CTX": 4096},
                    {"QWEN_LOCAL_MODEL": "qwen3-vl:8b"}):
            with self.assertRaises(SystemExit):
                rp.check_fidelity(self._cq(**bad), False)
            self.assertTrue(rp.check_fidelity(self._cq(**bad), True))


@unittest.skipUnless(os.getenv("KB_TEST_DATABASE_URL"), "définir KB_TEST_DATABASE_URL (base Postgres JETABLE)")
class TestBuildPlanPostgres(unittest.TestCase):
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
        self.conn.execute("TRUNCATE guitar_knowledge, guitar_knowledge_alias, guitar_knowledge_versions, guitar_deals CASCADE")
        use_latest_kb(self)
        self.conn.execute(
            """INSERT INTO guitar_knowledge (id, kind, name, description, relevance, source, kb_version, raw, curated)
               VALUES ('wd:a','brand','Marquea','Fabricant américain de guitares électriques et de basses, actif depuis 1950.',
                       'guitars','wikidata',1,'{"origin":["category:en"]}',true)""")
        self.conn.execute("INSERT INTO guitar_knowledge_alias VALUES ('marquea','wd:a','Marquea','wikidata')")
        self.gk.invalidate_cache()

    def _deal(self, did, title, initial, final, gate_verdict, photo=None):
        raw = {"gatekeeperVerdict": gate_verdict}
        if photo:
            raw["visual_inspection"] = photo
        self.conn.execute(
            "INSERT INTO guitar_deals (id, title, description, initial_verdict, verdict, ai_analysis_raw) "
            "VALUES (%s,%s,'',%s,%s,%s)", (did, title, initial, final, json.dumps(raw)))

    def test_strata_follow_the_reference_label_and_need_a_fiche(self):
        self._deal("fa", "Marquea guitare", "REJECTED_ITEM", "GOOD_DEAL", "REJECTED_ITEM")      # A : rejetée puis reclassée
        self._deal("fb", "Marquea basse", "GOOD_DEAL", "GOOD_DEAL", "GOOD_DEAL")                # B
        self._deal("fc", "Marquea ampli", "REJECTED_ITEM", "REJECTED_ITEM", "REJECTED_ITEM")    # vraiment rejetée : hors étude
        self._deal("fd", "Guitare sans fiche", "REJECTED_ITEM", "GOOD_DEAL", "REJECTED_ITEM")   # aucune fiche : hors étude
        self._deal("fe", "Marquea manuelle", "REJECTED_ITEM", "MANUAL_RETRY", "REJECTED_ITEM")  # le verdict final ne juge pas
        plan = rp.build_plan(self.conn, "latest", True, n_b=150, max_a=80, seed=1)
        self.assertEqual({l["id"]: l["stratum"] for l in plan["listings"]}, {"fa": "A", "fb": "B"})
        self.assertTrue(plan["meta"]["review_gate"])

    def test_photo_text_can_bring_a_fiche_the_title_missed_in_A_only(self):
        self._deal("fa", "Guitare rouge", "REJECTED_ITEM", "GOOD_DEAL", "REJECTED_ITEM", photo="tête de manche : Marquea")
        self._deal("fb", "Basse noire", "GOOD_DEAL", "GOOD_DEAL", "GOOD_DEAL", photo="Marquea")
        plan = rp.build_plan(self.conn, "latest", True, 150, 80, 1)
        by = {l["id"]: l for l in plan["listings"]}
        self.assertEqual(by["fa"]["kb_with"], [])
        self.assertEqual(by["fa"]["kb_photo"], ["wd:a"])
        self.assertNotIn("fb", by)                      # B n'a pas de bras « photo » : sans fiche par le texte, rien à mesurer
        jobs = rp.jobs_for(plan, _rows("screen", "without", "A", ["fa"], 1.0, 5), "eval", 5, 2, 2)
        self.assertEqual({j[2] for j in jobs}, {"without", "photo"})       # pas de bras « avec » : prompt identique à « sans »

    def test_gate_hides_unreviewed_fiches_from_the_plan(self):
        self.conn.execute("UPDATE guitar_knowledge SET curated = false")
        self.gk.invalidate_cache()
        self._deal("fa", "Marquea guitare", "REJECTED_ITEM", "GOOD_DEAL", "REJECTED_ITEM")
        self.assertEqual(rp.build_plan(self.conn, "latest", True, 150, 80, 1)["listings"], [])
        self.assertEqual(len(rp.build_plan(self.conn, "latest", False, 150, 80, 1)["listings"]), 1)


if __name__ == "__main__":
    unittest.main()
