"""Expert Leaf (niveau 3) : garde-fous de l'avis, prompt, appel simulé. Textes INVENTÉS (dépôt public), modèle SIMULÉ : aucun appel réseau."""
import unittest

from backend.leaf import ai, expert as ex

DESC = "Batterie remplacée en 2024 sous garantie, facture disponible. Pompe à chaleur. Pneus d'hiver inclus."


def listing(**kw):
    base = {"id": "leaf_test_1", "title": "Nissan Leaf 2016 S", "description": DESC, "price": 5000.0, "year": 2016, "km": 110000, "trim": "S",
            "soh_announced": None, "battery_kwh_low": 30, "battery_kwh_high": 30, "mentions": {}, "flags": ["soh_unknown"],
            "price_fit": None, "verdict": "A_VERIFIER", "verdict_reasons": ["SOH inconnu"], "ai": None, "equipment_list": []}
    base.update(kw)
    return base


def raw(**kw):
    base = {"opinion": "Annonce sérieuse, batterie récente.", "worth_visiting": "oui", "seller_questions": ["Quel est le kilométrage exact ?"],
            "inspection_points": ["Port CHAdeMO"], "price_ceiling": {"amount": 4800, "reasoning": "Légèrement sous le prix demandé."},
            "risks": [{"text": "Facture à vérifier", "evidence": "facture disponible"}]}
    base.update(kw)
    return base


class TestGuardrails(unittest.TestCase):
    def test_unusable_responses_are_none(self):
        for bad in (None, [], "x", {}, {"opinion": ""}, {"opinion": 3}):
            self.assertIsNone(ex.apply_guardrails(bad, listing()))

    def test_valid_opinion_is_accepted(self):
        out = ex.apply_guardrails(raw(), listing())
        self.assertEqual((out["worth_visiting"], out["price_ceiling"]["amount"], out["price_ceiling"]["basis"]),
                         ("oui", 4800, "indicatif (marché insuffisant)"))
        self.assertEqual((out["risks"][0]["evidence"], out["dropped"]), ("facture disponible", 0))

    def test_risks_without_a_quote_found_in_the_ad_are_dropped(self):
        out = ex.apply_guardrails(raw(risks=[{"text": "Rouille", "evidence": "rouille sous le châssis"}, {"text": "Sans preuve"},
                                             {"text": "OK", "evidence": "Pompe à chaleur"}]), listing())
        self.assertEqual([r["text"] for r in out["risks"]], ["OK"])
        self.assertEqual(out["dropped"], 2)

    def test_leafspy_question_is_added_by_the_code_when_soh_is_unknown(self):
        out = ex.apply_guardrails(raw(seller_questions=["Quel est le kilométrage ?"]), listing())
        self.assertIn(ex.LEAFSPY_QUESTION, out["seller_questions"])
        asked = ex.apply_guardrails(raw(seller_questions=["Pouvez-vous mesurer le SOH ?"]), listing())
        self.assertNotIn(ex.LEAFSPY_QUESTION, asked["seller_questions"])                 # déjà posée : pas de doublon
        known = ex.apply_guardrails(raw(), listing(soh_announced=90.0))
        self.assertNotIn(ex.LEAFSPY_QUESTION, known["seller_questions"])                 # SOH connu : rien à ajouter

    def test_question_list_is_capped_and_still_ends_with_the_leafspy_question(self):
        out = ex.apply_guardrails(raw(seller_questions=[f"Question {i} ?" for i in range(20)]), listing())
        self.assertEqual(len(out["seller_questions"]), ex.MAX_QUESTIONS)
        self.assertEqual(out["seller_questions"][-1], ex.LEAFSPY_QUESTION)

    def test_battery_proof_question_for_a_replaced_24_kwh(self):
        out = ex.apply_guardrails(raw(seller_questions=["Question ?"]),
                                  listing(battery_kwh_low=24, battery_kwh_high=24, mentions={"battery_replaced": True}, soh_announced=95.0))
        self.assertIn(ex.BATTERY_PROOF_QUESTION, out["seller_questions"])

    def test_price_ceiling_must_be_coherent_with_the_price_and_the_market(self):
        for amount in (100, 9000, True, "4800"):
            out = ex.apply_guardrails(raw(price_ceiling={"amount": amount, "reasoning": "x"}), listing())
            self.assertIsNone(out["price_ceiling"], amount)
        fit = {"expected": 4000, "delta_pct": 25.0, "n": 20}
        self.assertIsNone(ex.apply_guardrails(raw(price_ceiling={"amount": 4800}), listing(price_fit=fit))["price_ceiling"])   # > marché × 1,1
        ok = ex.apply_guardrails(raw(price_ceiling={"amount": 4300}), listing(price_fit=fit))
        self.assertEqual((ok["price_ceiling"]["amount"], ok["price_ceiling"]["basis"]), (4300, "marché estimé"))
        self.assertIsNone(ex.apply_guardrails(raw(price_ceiling={"amount": None}), listing())["price_ceiling"])

    def test_unknown_worth_becomes_maybe_and_lists_are_cleaned(self):
        out = ex.apply_guardrails(raw(worth_visiting="absolument", seller_questions=["A ?", "A ?", "", 3, "B ?"],
                                      inspection_points="pas une liste"), listing())
        self.assertEqual((out["worth_visiting"], out["inspection_points"]), ("peut-etre", []))
        self.assertEqual(out["seller_questions"][:2], ["A ?", "B ?"])


class TestPrompt(unittest.TestCase):
    def test_prompt_carries_the_established_facts_and_the_text(self):
        p = ex.build_prompt(listing(soh_announced=88.0, verdict="CANDIDAT_FORT", ai={"facts": {"heat_pump": {"value": True}}}))
        for needle in ("FAITS ÉTABLIS PAR LE CODE", "CANDIDAT_FORT", "88.0", "heat_pump", "TEXTE DE L'ANNONCE", "facture disponible", "MOT POUR MOT"):
            self.assertIn(needle, p)

    def test_unknown_battery_is_never_sent_as_a_fact_like_none_ou_24(self):
        facts = lambda lo, hi: ex.known_facts(listing(battery_kwh_low=lo, battery_kwh_high=hi))["batterie_kwh"]
        self.assertEqual((facts(24, None), facts(None, 30), facts(None, None)), ("inconnue", "inconnue", "inconnue"))
        self.assertEqual((facts(30, 30), facts(24, 30)), ("30", "24 ou 30"))
        self.assertNotIn("None", ex.build_prompt(listing(battery_kwh_low=24, battery_kwh_high=None)).split("TEXTE DE L'ANNONCE")[0].replace("null", ""))

    def test_row_to_listing_rebuilds_what_the_scores_need(self):
        row = {"id": "leaf_x_1", "title": "t", "description": "d", "price": 5000, "year": 2017, "km": 1, "trim": "SV", "location": "V",
               "seller_type": "delr", "battery_kwh_low": 30, "battery_kwh_high": 30, "battery_source": "inferred", "soh_announced": None,
               "soh_evidence": None, "flags": ["soh_unknown", "accident:reconstruit"], "verdict": "A_VERIFIER",
               "analysis": {"mentions": {"heat_pump": True}, "winter_fit": {"verdict": "ok"}, "price_fit": {"expected": 5000},
                            "verdict_reasons": ["r"], "ai": {"summary": "s"}}}
        out = ex.row_to_listing(row)
        self.assertEqual((out["price"], out["accident_flags"], out["mentions"], out["price_fit"], out["ai"]["summary"]),
                         (5000.0, ["reconstruit"], {"heat_pump": True}, {"expected": 5000}, "s"))
        self.assertEqual(ex.row_to_listing({**row, "analysis": None})["mentions"], {})


class TestPhotoObservations(unittest.TestCase):
    def test_observations_must_target_a_photo_really_sent(self):
        out = ex.apply_guardrails(raw(photo_observations=[{"photo": 1, "text": "Capture LeafSpy lisible"}, {"photo": 5, "text": "invalide"},
                                                          {"photo": 0, "text": "zéro"}, {"photo": "1", "text": "chaîne"}, {"photo": 2, "text": ""}]),
                                  listing(), photo_count=2)
        self.assertEqual(out["photo_observations"], [{"photo": 1, "text": "Capture LeafSpy lisible"}])
        self.assertEqual(out["dropped"], 4)

    def test_no_photo_sent_means_no_observation_accepted(self):
        out = ex.apply_guardrails(raw(photo_observations=[{"photo": 1, "text": "x"}]), listing())
        self.assertEqual((out["photo_observations"], out["dropped"]), ([], 1))

    def test_prompt_asks_for_observations_not_facts(self):
        self.assertIn("photo_observations", ex.PROMPT)
        self.assertIn("pas des faits", ex.PROMPT)


class FakeClaude:
    def __init__(self, result=None, error=None, boom=False):
        self.result, self.error, self.boom, self.calls = result, error, boom, []

    def _call_openai_compatible_json(self, *a, **kw):          # le passage tente aussi l'IA niveau 2 : ici, sans réponse
        return None, "hors ligne"

    def _call_gemini_json(self, *a, **kw):
        return None, "hors ligne"

    def _call_claude_json(self, model, parts, **kw):
        self.calls.append((model, kw.get("action"), parts))
        if self.boom:
            raise RuntimeError("API indisponible")
        return self.result, self.error


class TestLeafAiExpert(unittest.TestCase):
    def test_expert_call_uses_claude_and_the_leaf_t3_action(self):
        analyzer = FakeClaude(raw())
        opinion, err = ai.LeafAI(analyzer).expert(listing())
        self.assertIsNone(err)
        self.assertEqual((analyzer.calls[0][1], opinion["model"], opinion["version"]), ("leaf_t3", analyzer.calls[0][0], ex.EXPERT_VERSION))
        self.assertIn("claude", opinion["model"])
        self.assertIn("TEXTE DE L'ANNONCE", analyzer.calls[0][2][0])

    def test_photos_are_attached_and_observations_are_renumbered_to_the_listing_photos(self):
        analyzer = FakeClaude(raw(photo_observations=[{"photo": 2, "text": "Capture de batterie"}]))
        imgs = [object(), object()]
        opinion, err = ai.LeafAI(analyzer).expert(listing(), imgs, [4, 1])
        self.assertIsNone(err)
        self.assertEqual(analyzer.calls[0][2][1:], imgs)                                 # images jointes après le prompt
        self.assertEqual((opinion["photo_observations"], opinion["photos_sent"]), ([{"photo": 1, "text": "Capture de batterie"}], [4, 1]))

    def test_failures_are_reported_never_raised(self):
        self.assertEqual(ai.LeafAI(FakeClaude(None, "ANTHROPIC_API_KEY n'est pas configurée.")).expert(listing()),
                         (None, "ANTHROPIC_API_KEY n'est pas configurée."))
        opinion, err = ai.LeafAI(FakeClaude(boom=True)).expert(listing())
        self.assertEqual((opinion, err), (None, "API indisponible"))
        self.assertEqual(ai.LeafAI(None).expert(listing())[1], "Analyseur indisponible (bot hors ligne).")
        self.assertIsNone(ai.LeafAI(FakeClaude({"pas": "d'avis"})).expert(listing())[0])


if __name__ == "__main__":
    unittest.main()
