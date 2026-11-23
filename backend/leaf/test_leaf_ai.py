"""IA niveau 2 de Leaf : garde-fou des preuves, verdict, chaîne de fournisseurs. Textes INVENTÉS (dépôt public), modèles SIMULÉS :
aucun appel réseau. Sans Postgres."""
import unittest

from backend.leaf import ai, ai_extract as ax, normalize, verdict

TEXT = "Nissan Leaf 2017 SV. Batterie remplacée en 2024 sous garantie, facture disponible. Pompe à chaleur. Aucun accident."


def listing(**kw):
    base = {"title": "Nissan Leaf 2017 SV", "description": "Batterie remplacée en 2024 sous garantie, facture disponible. "
            "Pompe à chaleur. Aucun accident.", "price": 6000, "year": 2017, "km": 90000, "trim": "SV", "mentions": {},
            "accident_flags": [], "soh_announced": None, "flags": ["soh_unknown"], "battery_kwh_low": 30, "battery_kwh_high": 30}
    base.update(kw)
    return base


def response(**facts):
    base = {"summary": "Annonce détaillée.", "facts": {}, "attention": []}
    base["facts"].update(facts)
    return base


def fact(value, evidence, conf="high"):
    return {"value": value, "evidence": evidence, "confidence": conf}


class TestParse(unittest.TestCase):
    def test_unusable_responses_are_none(self):
        for bad in (None, [], "texte", {"facts": "x"}, {"summary": "s"}):
            self.assertIsNone(ax.parse_response(bad))

    def test_types_are_coerced_and_unknown_keys_ignored(self):
        parsed = ax.parse_response({"summary": " ok ", "facts": {
            "soh_pct": {"value": "87", "evidence": "SOH 87 %", "confidence": "high"},          # une chaîne n'est pas un nombre
            "heat_pump": {"value": "oui", "evidence": "x", "confidence": "??"},                # pas un booléen
            "chademo": {"value": True, "evidence": "CHAdeMO", "confidence": "banane"},
            "inconnu": {"value": True, "evidence": "x"}}, "attention": [{"text": "a", "evidence": 3}, "z"]})
        self.assertIsNone(parsed["facts"]["soh_pct"]["value"])
        self.assertIsNone(parsed["facts"]["heat_pump"]["value"])
        self.assertEqual((parsed["facts"]["chademo"]["value"], parsed["facts"]["chademo"]["confidence"]), (True, "low"))
        self.assertNotIn("inconnu", parsed["facts"])
        self.assertEqual((parsed["summary"], parsed["attention"]), ("ok", [{"text": "a", "evidence": None}]))


class TestGuardrails(unittest.TestCase):
    def guard(self, resp, **kw):
        return ax.apply_guardrails(ax.parse_response(resp), listing(**kw))

    def test_fact_with_exact_quote_is_accepted_even_with_accents_and_case(self):
        out = self.guard(response(battery_replaced=fact(True, "BATTERIE REMPLACÉE en 2024"), heat_pump=fact(True, "Pompe à chaleur")))
        self.assertEqual(set(out["facts"]), {"battery_replaced", "heat_pump"})
        self.assertEqual((out["flags"], out["rejected"]), ([], 0))

    def test_quote_not_found_in_the_text_is_refused_and_flagged(self):
        out = self.guard(response(chademo=fact(True, "charge rapide CHAdeMO incluse"), winter_tires=fact(True, "pneus d'hiver")))
        self.assertEqual(out["facts"], {})
        self.assertEqual((out["flags"], out["rejected"]), (["ai_unsupported_claim"], 2))

    def test_missing_or_too_short_quote_is_refused(self):
        out = self.guard(response(heat_pump=fact(True, None), chademo=fact(True, "ok"), winter_tires=fact(True, "")))
        self.assertEqual((out["facts"], out["rejected"]), ({}, 3))

    def test_null_value_is_unknown_not_a_rejection(self):
        out = self.guard(response(heat_pump=fact(None, None)))
        self.assertEqual((out["facts"], out["flags"], out["rejected"]), ({}, [], 0))

    def test_soh_number_must_appear_in_its_quote_and_be_plausible(self):
        text = {"description": "LeafSpy : SOH 87,5 % mesuré hier."}
        ok = self.guard(response(soh_pct=fact(87.5, "SOH 87,5 % mesuré")), **text)
        self.assertEqual(ok["facts"]["soh_pct"]["value"], 87.5)
        wrong = self.guard(response(soh_pct=fact(92.0, "SOH 87,5 % mesuré")), **text)           # 92 n'est pas dans la citation
        self.assertEqual((wrong["facts"], wrong["rejected"]), ({}, 1))
        absurd = self.guard(response(soh_pct=fact(30.0, "SOH 30")), description="SOH 30 %")
        self.assertEqual(absurd["facts"], {})

    def test_rules_win_when_the_model_contradicts_them(self):
        out = self.guard(response(heat_pump=fact(False, "Pompe à chaleur"), soh_pct=fact(95.0, "SOH 95 %")),
                         description="Pompe à chaleur. SOH 95 %.", mentions={"heat_pump": True}, soh_announced=86.0)
        self.assertEqual(out["facts"], {})
        self.assertEqual(out["flags"], ["ai_conflict"])

    def test_model_may_add_what_the_regex_missed(self):
        out = self.guard(response(battery_replaced=fact(True, "Batterie remplacée en 2024")), mentions={"battery_replaced": False})
        self.assertIn("battery_replaced", out["facts"])

    def test_attention_points_need_a_real_quote(self):
        resp = response()
        resp["attention"] = [{"text": "Facture à demander", "evidence": "facture disponible"},
                             {"text": "Inventé", "evidence": "vendu urgemment"}, {"text": "Sans preuve", "evidence": None}]
        out = self.guard(resp)
        self.assertEqual([a["text"] for a in out["attention"]], ["Facture à demander"])


class TestApply(unittest.TestCase):
    def test_accepted_facts_enrich_a_copy_and_clear_soh_unknown(self):
        base = listing()
        out_ai = ax.apply_guardrails(ax.parse_response(response(
            soh_pct=fact(91.0, "SOH 91 %"), battery_replaced=fact(True, "Batterie remplacée en 2024"),
            accident_mentioned=fact(True, "Aucun accident"))), {**base, "description": base["description"] + " SOH 91 %."})
        enriched = ax.apply_to_listing(base, out_ai)
        self.assertEqual((enriched["soh_announced"], enriched["soh_source"]), (91.0, "ai"))
        self.assertTrue(enriched["mentions"]["battery_replaced"])
        self.assertNotIn("soh_unknown", enriched["flags"])
        self.assertIn("ai_accident_mentioned", enriched["flags"])
        self.assertIsNone(base["soh_announced"])
        self.assertEqual(base["mentions"], {})                 # l'annonce d'origine n'est pas modifiée

    def test_ai_never_overrides_a_regex_soh(self):
        enriched = ax.apply_to_listing(listing(soh_announced=84.0), {"facts": {"soh_pct": {"value": 95.0, "evidence": "SOH 95", "confidence": "high"}}})
        self.assertEqual(enriched["soh_announced"], 84.0)


class TestFingerprint(unittest.TestCase):
    def test_changes_with_text_or_price_but_not_with_unrelated_fields(self):
        a = ax.fingerprint(listing())
        self.assertEqual(a, ax.fingerprint(listing(km=1)))
        self.assertEqual(a, ax.fingerprint(listing(price=6000.4)))
        self.assertNotEqual(a, ax.fingerprint(listing(price=5500)))
        self.assertNotEqual(a, ax.fingerprint(listing(description="Autre texte")))


class TestVerdict(unittest.TestCase):
    def v(self, **kw):
        return verdict.compute_verdict(listing(**kw))["verdict"]

    def test_verdicts(self):
        self.assertEqual(self.v(soh_announced=82.0), "BATTERIE_DOUTEUSE")
        self.assertEqual(self.v(price_fit={"delta_pct": 20.0}), "TROP_CHER")
        self.assertEqual(self.v(km=None), "INCOMPLET")
        self.assertEqual(self.v(year=None), "INCOMPLET")
        self.assertEqual(self.v(soh_announced=90.0, winter_fit={"verdict": "ok"}), "CANDIDAT_FORT")
        self.assertEqual(self.v(soh_announced=90.0, winter_fit={"verdict": "insuffisant"}), "A_VERIFIER")
        self.assertEqual(self.v(soh_announced=90.0, winter_fit={"verdict": "ok"}, flags=["ai_accident_mentioned"]), "A_VERIFIER")
        self.assertEqual(self.v(soh_announced=90.0, winter_fit={"verdict": "ok"}, price_fit={"delta_pct": 10.0}), "A_VERIFIER")
        self.assertEqual(self.v(), "A_VERIFIER")

    def test_few_dashboard_bars_make_the_battery_doubtful_but_a_stated_soh_wins(self):
        self.assertEqual(self.v(capacity_bars=6), "BATTERIE_DOUTEUSE")
        self.assertEqual(self.v(capacity_bars=9), "BATTERIE_DOUTEUSE")
        self.assertEqual(self.v(capacity_bars=10), "A_VERIFIER")
        self.assertEqual(self.v(capacity_bars=6, soh_announced=90.0, winter_fit={"verdict": "ok"}), "CANDIDAT_FORT")   # la mesure LeafSpy l'emporte sur la jauge

    def test_soh_unknown_is_explained_and_replaced_24_kwh_can_be_strong(self):
        self.assertIn("LeafSpy", " ".join(verdict.compute_verdict(listing())["reasons"]))
        strong = listing(battery_kwh_low=24, battery_kwh_high=24, mentions={"battery_replaced": True}, winter_fit={"verdict": "juste"})
        self.assertEqual(verdict.compute_verdict(strong)["verdict"], "CANDIDAT_FORT")

    def test_doubtful_battery_wins_over_a_good_price(self):
        self.assertEqual(self.v(soh_announced=80.0, price_fit={"delta_pct": -30.0}), "BATTERIE_DOUTEUSE")


class FakeAnalyzer:
    """Simule `DealAnalyzer` : réponses programmées par fournisseur."""
    def __init__(self, local=None, gemini=None):
        self.local, self.gemini, self.calls = local, gemini, []

    def _call_openai_compatible_json(self, prompt, images, model, key, url, **kw):
        self.calls.append(("local", kw.get("action")))
        return self.local if isinstance(self.local, tuple) else (self.local, None)

    def _call_gemini_json(self, model, parts, **kw):
        self.calls.append(("gemini", kw.get("action")))
        return self.gemini if isinstance(self.gemini, tuple) else (self.gemini, None)


class TestChain(unittest.TestCase):
    GOOD = response(heat_pump=fact(True, "Pompe à chaleur"))

    def setUp(self):
        from backend import t1_circuit_breaker
        t1_circuit_breaker.record_success("local")                          # état partagé du processus : repart à zéro
        self.addCleanup(t1_circuit_breaker.record_success, "local")

    def test_a_dead_dell_is_skipped_after_three_failures_like_for_the_gatekeeper(self):
        from backend import t1_circuit_breaker
        analyzer = FakeAnalyzer(local=(None, "timeout"), gemini=self.GOOD)
        for _ in range(3):
            ai.LeafAI(analyzer).extract(listing())
        self.assertTrue(t1_circuit_breaker.is_open("local"))
        analyzer.calls.clear()
        result, err = ai.LeafAI(analyzer).extract(listing())
        self.assertEqual((err, result["provider"], [c[0] for c in analyzer.calls]), (None, "gemini", ["gemini"]))   # Dell non rappelé

    def test_a_working_dell_keeps_the_circuit_closed_and_unusable_json_is_not_a_failure(self):
        from backend import t1_circuit_breaker
        analyzer = FakeAnalyzer(local=({"pas": "de faits"}, None), gemini=self.GOOD)       # a répondu, mais réponse inutilisable
        for _ in range(5):
            ai.LeafAI(analyzer).extract(listing())
        self.assertFalse(t1_circuit_breaker.is_open("local"))

    def run_chain(self, analyzer, providers=("local", "gemini")):
        return ai.LeafAI(analyzer).extract(listing(), providers)

    def test_local_answer_is_used_and_gemini_not_called(self):
        analyzer = FakeAnalyzer(local=self.GOOD, gemini=self.GOOD)
        result, err = self.run_chain(analyzer)
        self.assertEqual((err, result["provider"], analyzer.calls), (None, "local", [("local", "leaf_t2")]))
        self.assertEqual((result["facts"]["heat_pump"]["value"], result["version"]), (True, ax.AI_VERSION))
        self.assertEqual(result["fingerprint"], ax.fingerprint(listing()))

    def test_unusable_local_answer_falls_back_to_gemini(self):
        analyzer = FakeAnalyzer(local=(None, "JSON invalide"), gemini=self.GOOD)
        result, err = self.run_chain(analyzer)
        self.assertEqual((err, result["provider"], [c[0] for c in analyzer.calls]), (None, "gemini", ["local", "gemini"]))

    def test_all_providers_failing_returns_an_error_never_raises(self):
        class Boom(FakeAnalyzer):
            def _call_gemini_json(self, *a, **k):
                raise RuntimeError("quota")
        result, err = self.run_chain(Boom(local=(None, "hors ligne")))
        self.assertIsNone(result)
        self.assertIn("quota", err)

    def test_provider_order_is_the_configured_one_and_unknown_providers_are_skipped(self):
        analyzer = FakeAnalyzer(local=self.GOOD, gemini=self.GOOD)
        result, _ = self.run_chain(analyzer, ("nope", "gemini", "local"))
        self.assertEqual((result["provider"], [c[0] for c in analyzer.calls]), ("gemini", ["gemini"]))

    def test_no_analyzer_means_no_call(self):
        self.assertEqual(ai.LeafAI(None).extract(listing()), (None, "Analyseur indisponible (bot hors ligne)."))

    def test_hallucinated_fact_in_the_answer_is_dropped_by_the_guardrail(self):
        bad = response(chademo=fact(True, "CHAdeMO neuf"), heat_pump=fact(True, "Pompe à chaleur"))
        result, _ = self.run_chain(FakeAnalyzer(local=bad))
        self.assertEqual(set(result["facts"]), {"heat_pump"})
        self.assertEqual((result["flags"], result["rejected"]), (["ai_unsupported_claim"], 1))


if __name__ == "__main__":
    unittest.main()
