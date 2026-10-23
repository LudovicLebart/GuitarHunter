"""Tests purs (sans base ni réseau) de `backend/scrape_health.py`."""
import unittest

from backend import scrape_health as sh


def fb(cards=0, out_of_list=0, blocked=False, error=None, deals=None):
    return {"total_cards_seen": cards, "rejected_out_of_list": out_of_list,
            "anti_bot_blocked": blocked, "error": error, "deals": deals or []}


class TestClassifyFacebook(unittest.TestCase):
    def test_bromont_france_case_is_geo_mismatch(self):
        # Mesure réelle du 2026-10-23 : 82 cartes, 82 hors liste, 0 gardée.
        self.assertEqual(sh.classify_facebook(fb(82, 82))[0], sh.GEO_MISMATCH)

    def test_quebec_bromont_case_is_ok(self):
        # 24 cartes, 3 hors liste, 21 gardées.
        deals = [{"imageUrls": ["u"]}] * 21
        self.assertEqual(sh.classify_facebook(fb(24, 3, deals=deals))[0], sh.OK)

    def test_small_town_without_new_guitar_is_ok_not_a_failure(self):
        # Cartes vues, aucune gardée (déjà connues / filtrées) : pas un échec du scraper.
        self.assertEqual(sh.classify_facebook(fb(12, 1))[0], sh.OK)

    def test_few_cards_all_out_of_list_is_not_geo_mismatch(self):
        # Sous le plancher de 5 cartes, on ne conclut pas (une toute petite ville).
        self.assertEqual(sh.classify_facebook(fb(3, 3))[0], sh.OK)

    def test_zero_cards(self):
        self.assertEqual(sh.classify_facebook(fb(0))[0], sh.NO_CARDS)

    def test_blocked_wins_over_everything(self):
        self.assertEqual(sh.classify_facebook(fb(0, blocked=True))[0], sh.BLOCKED)

    def test_error_field_and_exception(self):
        self.assertEqual(sh.classify_facebook(fb(10, error="boom"))[0], sh.ERROR)
        self.assertEqual(sh.classify_facebook(fb(), exception=RuntimeError("x"))[0], sh.ERROR)

    def test_detail_degraded_when_most_details_have_no_photo(self):
        deals = [{"imageUrls": []}, {"imageUrls": []}, {"imageUrls": ["u"]}]
        self.assertEqual(sh.classify_facebook(fb(20, 2, deals=deals))[0], sh.DETAIL_DEGRADED)

    def test_few_deals_never_degraded(self):
        self.assertEqual(sh.classify_facebook(fb(20, 2, deals=[{"imageUrls": []}]))[0], sh.OK)


class TestClassifyKijiji(unittest.TestCase):
    def test_outcomes(self):
        self.assertEqual(sh.classify_kijiji({"cards_seen": 12})[0], sh.OK)
        self.assertEqual(sh.classify_kijiji({"cards_seen": 0})[0], sh.NO_CARDS)
        self.assertEqual(sh.classify_kijiji({"blocked": True})[0], sh.BLOCKED)
        self.assertEqual(sh.classify_kijiji({"error": "no_anchor"})[0], sh.ERROR)
        self.assertEqual(sh.classify_kijiji(None)[0], sh.NO_CARDS)
        self.assertEqual(sh.classify_kijiji({"cards_seen": 3}, exception=ValueError("x"))[0], sh.ERROR)


class TestShouldAlert(unittest.TestCase):
    def test_no_history_no_alert(self):
        self.assertEqual(sh.should_alert([]), (False, None, 0))

    def test_three_consecutive_failures_alert(self):
        alert, code, n = sh.should_alert([sh.GEO_MISMATCH] * 3 + [sh.OK])
        self.assertTrue(alert)
        self.assertEqual((code, n), (sh.GEO_MISMATCH, 3))

    def test_two_failures_then_ok_do_not_alert(self):
        self.assertFalse(sh.should_alert([sh.ERROR, sh.ERROR, sh.OK, sh.OK])[0])

    def test_consecutive_failures_of_mixed_codes_use_dominant(self):
        alert, code, _ = sh.should_alert([sh.NO_CARDS, sh.BLOCKED, sh.BLOCKED, sh.OK])
        self.assertTrue(alert)
        self.assertEqual(code, sh.BLOCKED)

    def test_ratio_window_alerts_even_when_interleaved(self):
        # F, OK, F, OK, F, OK : 50 % d'échecs sur 6 scans, jamais 3 de suite.
        history = [sh.ERROR, sh.OK, sh.ERROR, sh.OK, sh.ERROR, sh.OK]
        alert, code, n = sh.should_alert(history)
        self.assertTrue(alert)
        self.assertEqual((code, n), (sh.ERROR, 3))

    def test_ratio_needs_enough_runs(self):
        self.assertFalse(sh.should_alert([sh.ERROR, sh.OK, sh.ERROR, sh.OK])[0])

    def test_healthy_history_no_alert(self):
        self.assertFalse(sh.should_alert([sh.OK] * 10)[0])


class TestRepairHint(unittest.TestCase):
    def test_geo_mismatch_names_the_city(self):
        self.assertIn("Bromont", sh.repair_hint(sh.GEO_MISMATCH, "Bromont"))

    def test_unknown_code_has_fallback(self):
        self.assertTrue(sh.repair_hint("inconnu", "X"))


if __name__ == "__main__":
    unittest.main()
