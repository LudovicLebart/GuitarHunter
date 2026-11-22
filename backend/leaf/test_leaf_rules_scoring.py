"""Tests purs : filtres, règles du Portier, scores, doublons, pipeline — données INVENTÉES."""
import unittest

from backend.leaf import dedup, filters, normalize, pipeline, rules, scoring


def L(**kw):
    """Annonce brute inventée, normalisée."""
    base = {"id": "leaf_test_1", "source": "test", "title": "2016 Nissan Leaf SV", "description": "",
            "price": 5000, "year": 2016, "km": 100000, "model": "leaf", "latitude": 45.5, "longitude": -73.6}
    base.update(kw)
    return normalize.normalize_listing(base)


class TestFilters(unittest.TestCase):
    def test_accepts_in_range(self):
        self.assertEqual(filters.passes_criteria(L()), (True, "ok"))

    def test_rejection_reasons(self):
        self.assertEqual(filters.passes_criteria(L(price=None))[1], "no_price")
        self.assertEqual(filters.passes_criteria(L(year=2014))[1], "year")
        self.assertEqual(filters.passes_criteria(L(price=900))[1], "price_low")
        self.assertEqual(filters.passes_criteria(L(price=9000))[1], "price_high")
        self.assertEqual(filters.passes_criteria(L(km=200000))[1], "km")
        self.assertEqual(filters.passes_criteria(L(model="spark", title="Chevrolet Spark EV"))[1], "not_leaf")

    def test_unknown_km_is_kept(self):
        listing = L(km=None, title="2016 Nissan Leaf SV")
        self.assertEqual(filters.passes_criteria(listing), (True, "ok"))

    def test_custom_criteria(self):
        self.assertEqual(filters.passes_criteria(L(price=6500), {"max_price": 6000})[1], "price_high")

    def test_distance(self):
        ok, d = filters.within_distance(L(), 45.5, -73.6, 150)
        self.assertTrue(ok)
        self.assertLess(d, 1)
        ok, d = filters.within_distance(L(latitude=46.8, longitude=-71.2), 45.5, -73.6, 150)   # Québec ~ 230 km
        self.assertFalse(ok)
        self.assertGreater(d, 150)
        self.assertEqual(filters.within_distance(L(latitude=None, longitude=None), 45.5, -73.6, 150), (True, None))


class TestRules(unittest.TestCase):
    def test_pass_with_flags(self):
        decision, reasons, flags = rules.gatekeeper_rules(L(km=None))
        self.assertEqual((decision, reasons), ("PASS", []))
        self.assertIn("soh_unknown", flags)
        self.assertIn("km_unknown", flags)

    def test_reject_stated_24kwh(self):
        decision, reasons, _ = rules.gatekeeper_rules(L(description="batterie 24 kWh"))
        self.assertEqual(decision, "REJECT")
        self.assertIn("battery_24kwh", reasons)

    def test_24kwh_replaced_is_flagged_not_rejected(self):
        for desc in ("batterie 24 kWh remplacée en janvier 2024", "24 kWh, nouvelle batterie installée",
                     "24 kWh battery replaced by Nissan"):
            decision, reasons, flags = rules.gatekeeper_rules(L(description=desc))
            self.assertEqual((decision, reasons), ("PASS", []), desc)
            self.assertIn("battery_24_replaced", flags)

    def test_24kwh_replaced_winter_fit_assumes_new_battery(self):
        wf = scoring.winter_fit(L(description="24 kWh, batterie remplacée en 2024"))
        self.assertEqual(wf["soh_assumed"], (95.0, 100.0))
        self.assertEqual((wf["low_km"], wf["high_km"], wf["verdict"]), (71, 101, "juste"))
        self.assertIn("battery_24_replaced", scoring.risk_flags(L(description="24 kWh, batterie remplacée")))

    def test_2016_s_is_only_flagged(self):
        decision, _, flags = rules.gatekeeper_rules(L(title="2016 Nissan Leaf S"))
        self.assertEqual(decision, "PASS")
        self.assertIn("battery_24_possible", flags)

    def test_reject_accident_but_not_negated(self):
        self.assertEqual(rules.gatekeeper_rules(L(description="véhicule reconstruit"))[0], "REJECT")
        self.assertEqual(rules.gatekeeper_rules(L(description="jamais accidentée"))[0], "PASS")

    def test_soh_threshold(self):
        self.assertEqual(rules.gatekeeper_rules(L(description="LeafSpy SOH 78 %"))[0], "REJECT")
        self.assertEqual(rules.gatekeeper_rules(L(description="LeafSpy SOH 82 %"))[0], "PASS")
        self.assertEqual(rules.gatekeeper_rules(L(description="LeafSpy SOH 82 %"), soh_min_reject=85)[0], "REJECT")


class TestScoring(unittest.TestCase):
    def test_battery_score(self):
        self.assertEqual([scoring.battery_score(v) for v in (95, 87, 82, 70)], [10, 8, 5, 2])
        self.assertIsNone(scoring.battery_score(None))

    def test_winter_fit_30kwh_85pct(self):
        wf = scoring.winter_fit(L(year=2017, description="LeafSpy SOH 85 %"))
        self.assertEqual((wf["low_km"], wf["high_km"]), (80, 110))     # cohérent avec « 80-110 km »
        self.assertEqual(wf["needed_km"], 75)
        self.assertEqual(wf["verdict"], "ok")

    def test_winter_fit_unknown_soh_gives_range(self):
        wf = scoring.winter_fit(L(year=2017))
        self.assertEqual(wf["soh_assumed"], (75.0, 90.0))
        self.assertLess(wf["low_km"], wf["high_km"])

    def test_winter_fit_24kwh(self):
        wf = scoring.winter_fit(L(description="24 kWh LeafSpy SOH 80 %"))
        self.assertEqual((wf["low_km"], wf["high_km"], wf["verdict"]), (59, 81, "juste"))
        wf = scoring.winter_fit(L(description="24 kWh LeafSpy SOH 70 %"))
        self.assertEqual(wf["verdict"], "insuffisant")

    def test_winter_fit_2018_40kwh_degraded_still_ok(self):
        wf = scoring.winter_fit(L(year=2018, title="2018 Nissan Leaf SV", description="LeafSpy SOH 75 %"))
        self.assertEqual(wf["verdict"], "ok")

    def test_winter_fit_unknown_battery(self):
        wf = scoring.winter_fit({"battery_kwh_low": None, "battery_kwh_high": None})
        self.assertEqual(wf["verdict"], "inconnu")

    def test_equipment(self):
        e = scoring.equipment_score(L(description="pompe à chaleur, pneus d'hiver, sièges chauffants, volant chauffant"))
        self.assertEqual((e["score"], e["heat_pump_inferred"]), (10, False))
        inferred = scoring.equipment_score(L(title="2016 Nissan Leaf SV"))
        self.assertEqual((inferred["score"], inferred["heat_pump_inferred"]), (4, True))
        self.assertEqual(scoring.equipment_score(L(title="2016 Nissan Leaf S"))["score"], 0)

    def test_price_fit_needs_enough_comparables(self):
        comps = [{"year": 2016, "km": 100000 + i * 1000, "price": 5000} for i in range(5)]
        self.assertIsNone(scoring.price_fit(L(), comps))

    def test_price_fit_regression(self):
        comps = []
        for i in range(20):                       # prix = 4000 + 800*(année-2016) - 20*(km/10000), exact
            year, km = 2016 + i % 3, 60000 + 5000 * i
            comps.append({"year": year, "km": km, "price": 4000 + 800 * (year - 2016) - 20 * (km / 10000)})
        fit = scoring.price_fit(L(year=2017, km=100000, price=4600), comps)
        self.assertEqual(fit["expected"], 4600)
        self.assertEqual(fit["delta"], 0)
        cheap = scoring.price_fit(L(year=2017, km=100000, price=4140), comps)
        self.assertEqual(cheap["delta_pct"], -10.0)


class TestDedup(unittest.TestCase):
    def test_same_vin(self):
        self.assertTrue(dedup.same_vehicle({"vin": "abc123"}, {"vin": "ABC123", "year": 1}))
        self.assertFalse(dedup.same_vehicle({"vin": "ABC123", "year": 2016, "km": 1}, {"vin": "XYZ999", "year": 2016, "km": 1}))

    def test_same_attributes(self):
        a = {"year": 2017, "trim": "SV", "km": 100000, "latitude": 45.5, "longitude": -73.6}
        b = {"year": 2017, "trim": "SV", "km": 100500, "latitude": 45.52, "longitude": -73.62}
        self.assertTrue(dedup.same_vehicle(a, b))

    def test_differences(self):
        a = {"year": 2017, "trim": "SV", "km": 100000}
        self.assertFalse(dedup.same_vehicle(a, {**a, "year": 2016}))
        self.assertFalse(dedup.same_vehicle(a, {**a, "trim": "SL"}))
        self.assertFalse(dedup.same_vehicle(a, {**a, "km": 110000}))
        self.assertFalse(dedup.same_vehicle(a, {**a, "km": None}))
        far = {**a, "latitude": 46.8, "longitude": -71.2}
        self.assertFalse(dedup.same_vehicle({**a, "latitude": 45.5, "longitude": -73.6}, far))

    def test_unknown_trim_is_compatible(self):
        a = {"year": 2017, "trim": "SV", "km": 100000}
        self.assertTrue(dedup.same_vehicle(a, {**a, "trim": None}))


class TestPipeline(unittest.TestCase):
    def test_buckets_and_sorting(self):
        raws = [
            {"id": "a", "title": "2016 Nissan Leaf SV", "price": 4500, "year": 2016, "km": 110000, "model": "leaf"},
            {"id": "b", "title": "2017 Nissan Leaf SV", "price": 3800, "year": 2017, "km": 90000, "model": "leaf"},
            {"id": "c", "title": "2016 Nissan Leaf SV", "price": 4000, "year": 2016, "km": 90000, "model": "leaf",
             "description": "titre reconstruit"},
            {"id": "d", "title": "2014 Nissan Leaf", "price": 3000, "year": 2014, "km": 90000, "model": "leaf"},
            {"id": "a", "title": "doublon d'id", "price": 1, "year": 2016, "km": 1, "model": "leaf"},
        ]
        out = pipeline.evaluate_listings(raws)
        self.assertEqual([a["id"] for a in out["kept"]], ["b", "a"])           # tri par prix
        self.assertEqual([a["id"] for a in out["rejected"]], ["c"])
        self.assertEqual([a["id"] for a in out["ignored"]], ["d"])
        self.assertEqual(out["ignored"][0]["ignored_reason"], "year")

    def test_duplicate_is_marked_not_dropped(self):
        base = {"title": "2017 Nissan Leaf SV", "year": 2017, "km": 100000, "model": "leaf",
                "latitude": 45.5, "longitude": -73.6}
        out = pipeline.evaluate_listings([{**base, "id": "x", "price": 5200}, {**base, "id": "y", "price": 5000}])
        self.assertEqual(len(out["kept"]), 2)
        by_id = {a["id"]: a for a in out["kept"]}
        self.assertIsNone(by_id["x"]["duplicate_of"])      # la première vue sert de référence
        self.assertEqual(by_id["y"]["duplicate_of"], "x")  # la suivante est MARQUÉE, pas supprimée

    def test_distance_filter(self):
        raws = [{"id": "near", "title": "2016 Nissan Leaf SV", "price": 4000, "year": 2016, "km": 1e5, "model": "leaf",
                 "latitude": 45.5, "longitude": -73.6},
                {"id": "far", "title": "2016 Nissan Leaf SV", "price": 4100, "year": 2016, "km": 1.1e5, "model": "leaf",
                 "latitude": 48.4, "longitude": -71.1}]
        out = pipeline.evaluate_listings(raws, home={"latitude": 45.5, "longitude": -73.6, "max_km": 150})
        self.assertEqual([a["id"] for a in out["kept"]], ["near"])
        self.assertEqual(out["ignored"][0]["ignored_reason"], "distance")


if __name__ == "__main__":
    unittest.main()
