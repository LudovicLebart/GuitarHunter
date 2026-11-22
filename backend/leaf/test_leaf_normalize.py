"""Tests purs de `backend/leaf/normalize.py` — données INVENTÉES (dépôt public : aucune vraie annonce)."""
import unittest

from backend.leaf import normalize as n


class TestParsers(unittest.TestCase):
    def test_year(self):
        self.assertEqual(n.parse_year("Nissan Leaf 2017 SV"), 2017)
        self.assertIsNone(n.parse_year("Nissan Leaf SV"))
        self.assertIsNone(n.parse_year("ref 1999"))

    def test_km_variants(self):
        self.assertEqual(n.parse_km("Leaf 111 439 km en bon état"), 111439)
        self.assertEqual(n.parse_km("115000km"), 115000)
        self.assertEqual(n.parse_km("98.500 km"), 98500)
        self.assertEqual(n.parse_km("111 439 km"), 111439)

    def test_km_out_of_range_or_missing(self):
        self.assertIsNone(n.parse_km("pas de kilométrage"))
        self.assertIsNone(n.parse_km("500 km"))            # trop petit : probablement autre chose
        self.assertIsNone(n.parse_km("999 999 km"))

    def test_trim(self):
        self.assertEqual(n.parse_trim("2016 Nissan Leaf SV"), "SV")
        self.assertEqual(n.parse_trim("Nissan LEAF SL cuir"), "SL")
        self.assertEqual(n.parse_trim("2017 Nissan LEAF  S"), "S")
        self.assertEqual(n.parse_trim("Nissan Leaf Voiture à hayon modèle S à 4 portes"), "S")
        self.assertIsNone(n.parse_trim("2017 Nissan Leaf"))


class TestBattery(unittest.TestCase):
    def test_inferred_by_year(self):
        self.assertEqual(n.battery_info(2018, "SV"), (40, 40, "inferred"))
        self.assertEqual(n.battery_info(2017, "S"), (30, 30, "inferred"))
        self.assertEqual(n.battery_info(2016, "SV"), (30, 30, "inferred"))

    def test_2016_s_or_unknown_trim_may_be_24(self):
        self.assertEqual(n.battery_info(2016, "S"), (24, 30, "inferred"))
        self.assertEqual(n.battery_info(2016, None), (24, 30, "inferred"))

    def test_stated_wins(self):
        self.assertEqual(n.battery_info(2016, "SV", "batterie 24 kWh"), (24, 24, "stated"))

    def test_unknown_year(self):
        self.assertEqual(n.battery_info(None, None), (None, None, "unknown"))


class TestSoh(unittest.TestCase):
    def test_soh_variants(self):
        self.assertEqual(n.extract_soh("LeafSpy : SOH 87,5 %")[0], 87.5)
        self.assertEqual(n.extract_soh("État de santé de la batterie : 91%")[0], 91.0)
        self.assertEqual(n.extract_soh("85% SOH")[0], 85.0)

    def test_evidence_is_substring_of_normalised_text(self):
        text = "Très propre. LeafSpy: SOH 88 % vérifié"
        value, evidence = n.extract_soh(text)
        self.assertEqual(value, 88.0)
        self.assertIn(evidence, n.normalize_text(text))

    def test_no_soh_when_percentage_is_not_battery(self):
        self.assertIsNone(n.extract_soh("Taxes incluses 15 % de rabais"))
        self.assertIsNone(n.extract_soh("SOH 12 %"))        # hors bornes plausibles

    def test_bars(self):
        self.assertEqual(n.extract_capacity_bars("11/12 barres de batterie")[0], 11)
        self.assertEqual(n.extract_capacity_bars("10 sur 12 barres")[0], 10)
        self.assertIsNone(n.extract_capacity_bars("12 barres"))      # sans « x/12 » : pas une mesure


class TestFlagsAndMentions(unittest.TestCase):
    def test_accident_detected(self):
        self.assertIn("accident", n.accident_flags("Véhicule accidenté, à réparer"))
        self.assertIn("reconstruit", n.accident_flags("Titre reconstruit"))

    def test_negated_accident_not_flagged(self):
        self.assertEqual(n.accident_flags("Jamais accidentée, Carfax propre"), [])
        self.assertEqual(n.accident_flags("sans accident"), [])
        self.assertEqual(n.accident_flags("aucun accident déclaré"), [])

    def test_mentions(self):
        m = n.detect_mentions("Pompe à chaleur, sièges chauffants, volant chauffant, pneus d'hiver, câble de recharge")
        self.assertTrue(all(m[k] for k in ("heat_pump", "heated_seats", "heated_wheel", "winter_tires", "charging_cable")))
        self.assertFalse(m["carfax"])


class TestNormalizeListing(unittest.TestCase):
    def test_fills_missing_fields_and_derives(self):
        raw = {"title": "2016 Nissan Leaf SV 111 439 km", "description": "LeafSpy SOH 86 %, jamais accidentée"}
        out = n.normalize_listing(raw)
        self.assertEqual((out["year"], out["trim"], out["km"]), (2016, "SV", 111439))
        self.assertEqual(out["soh_announced"], 86.0)
        self.assertEqual(out["battery_kwh_low"], 30)
        self.assertEqual(out["accident_flags"], [])
        self.assertNotIn("soh_announced", raw)        # l'entrée n'est pas modifiée

    def test_source_values_take_precedence(self):
        out = n.normalize_listing({"title": "Leaf 2016", "year": 2018, "km": 50000, "trim": "SL"})
        self.assertEqual((out["year"], out["km"], out["trim"]), (2018, 50000, "SL"))


if __name__ == "__main__":
    unittest.main()


class TestReviewFixes(unittest.TestCase):
    def test_french_negations_are_not_accidents(self):
        for t in ("Carfax propre, pas d'accident", "aucun historique d'accident", "jamais eu d'accident",
                  "sans accident", "pas d’accident"):
            self.assertEqual(n.accident_flags(t), [], t)
        self.assertEqual(n.accident_flags("voiture accidentée"), ["accident"])
        self.assertEqual(n.accident_flags("compas accident"), ["accident"])

    def test_km_after_year(self):
        self.assertEqual(n.parse_km("Nissan Leaf 2017 120 000 km"), 120000)
        self.assertEqual(n.parse_km("2017 85 000 km"), 85000)

    def test_12v_battery_is_not_traction_battery(self):
        self.assertFalse(n.detect_mentions("batterie 12v neuve")["battery_replaced"])
        self.assertFalse(n.detect_mentions("nouvelle batterie 12 v")["battery_replaced"])
        self.assertTrue(n.detect_mentions("batterie remplacée en 2024")["battery_replaced"])

    def test_negated_kwh_is_not_stated(self):
        self.assertEqual(n.battery_info(2018, "SV", "batterie 40 kWh, pas la 24 kWh")[:3], (40, 40, "stated"))
        self.assertEqual(n.battery_info(2018, "SV", "pas de 24 kWh ici")[2], "inferred")
