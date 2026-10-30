"""Tests purs de `backend/scraping/zone.py`."""
import unittest

from backend.scraping import zone

POINTS = [("granby", 45.399, -72.722), ("bromont", 45.319, -72.646), ("la saline", -21.0875, 55.2347)]
PARIS = [("paris", 48.8566, 2.3522)]


class TestIsOutsideCanada(unittest.TestCase):
    def test_reunion_and_paris_are_outside(self):
        self.assertTrue(zone.is_outside_canada(-21.0875, 55.2347))
        self.assertTrue(zone.is_outside_canada(48.8566, 2.3522))

    def test_quebec_cities_are_inside(self):
        self.assertFalse(zone.is_outside_canada(45.399, -72.722))
        self.assertFalse(zone.is_outside_canada(45.4042, -71.8929))

    def test_western_us_is_outside(self):
        self.assertTrue(zone.is_outside_canada(47.6, -122.3))   # Seattle

    def test_western_canada_is_inside(self):
        self.assertFalse(zone.is_outside_canada(49.28, -123.12))  # Vancouver
        self.assertFalse(zone.is_outside_canada(53.55, -113.49))  # Edmonton

    def test_missing_coordinates_are_never_excluded(self):
        self.assertFalse(zone.is_outside_canada(None, None))
        self.assertFalse(zone.is_outside_canada(None, -72.0))


class TestNearestListedCity(unittest.TestCase):
    def test_island_level_card_is_placed_by_gps(self):
        self.assertEqual(zone.nearest_listed_city(-21.09, 55.24, POINTS, 5), "la saline")

    def test_just_outside_the_bound_is_rejected(self):
        # Environ 11 km de Granby : hors des 5 km.
        self.assertIsNone(zone.nearest_listed_city(45.30, -72.72, POINTS, 5))

    def test_nearest_wins_when_two_in_bound(self):
        pts = [("a", 45.00, -72.00), ("b", 45.01, -72.00)]
        self.assertEqual(zone.nearest_listed_city(45.009, -72.00, pts, 5), "b")

    def test_french_homonym_never_matches_quebec(self):
        self.assertIsNone(zone.nearest_listed_city(45.97, 2.97, POINTS, 15))

    def test_per_city_extra_km_widens_only_that_city(self):
        pts = [("a", 45.00, -72.00, 30), ("b", 46.00, -72.00)]
        self.assertEqual(zone.nearest_listed_city(45.20, -72.00, pts, 5), "a")   # ~22 km, borne élargie de a
        self.assertIsNone(zone.nearest_listed_city(45.80, -72.00, pts, 5))       # ~22 km de b, borne 5


class TestCardVerdict(unittest.TestCase):
    def test_unknown_label_rescued_by_gps(self):
        # « Réunion, Reunion » : seul le GPS rattache la carte à La Saline.
        self.assertEqual(zone.card_verdict(False, {"lat": -21.09, "lng": 55.24}, POINTS, 5, 15), ("keep", "la saline"))

    def test_unknown_label_far_away_is_rejected_and_cacheable(self):
        self.assertEqual(zone.card_verdict(False, {"lat": 45.0, "lng": -73.9}, POINTS, 5, 15), ("reject", True))

    def test_unknown_label_without_gps_is_rejected_not_cacheable(self):
        # Fiche non chargée : on retentera au cycle suivant.
        self.assertEqual(zone.card_verdict(False, None, POINTS, 5, 15), ("reject", False))

    def test_name_match_without_gps_is_kept_on_the_name(self):
        self.assertEqual(zone.card_verdict(True, None, POINTS, 5, 15), ("keep", None))

    def test_name_match_within_wide_tolerance_is_kept(self):
        # ~6 km de Bromont : trop loin pour un lieu inconnu (5 km), accepté si le nom est reconnu (15 km).
        c = {"lat": 45.30, "lng": -72.72}
        self.assertEqual(zone.card_verdict(False, c, POINTS, 5, 15), ("reject", True))
        self.assertEqual(zone.card_verdict(True, c, POINTS, 5, 15), ("keep", "bromont"))

    def test_homonym_with_listed_name_but_far_gps_is_rejected(self):
        # « Paris, ON » reconnu par son nom pour une liste « Paris » (France) : le GPS (Ontario) le rejette.
        self.assertEqual(zone.card_verdict(True, {"lat": 43.19, "lng": -80.38}, PARIS, 5, 15), ("reject", True))


class TestMayTryGpsFallback(unittest.TestCase):
    def test_cap_per_scan(self):
        self.assertTrue(zone.may_try_gps_fallback(7, 2, cap=8))
        self.assertFalse(zone.may_try_gps_fallback(8, 2, cap=8))

    def test_gives_up_when_first_pages_rescue_nothing(self):
        # ID de ville probablement faux : 3 fiches sans aucune carte rattachée, on s'arrête.
        self.assertTrue(zone.may_try_gps_fallback(2, 0, cap=8))
        self.assertFalse(zone.may_try_gps_fallback(3, 0, cap=8))

    def test_keeps_going_once_something_was_rescued(self):
        self.assertTrue(zone.may_try_gps_fallback(5, 1, cap=8))



class TestBucketCity(unittest.TestCase):
    """Ville de rangement en mode strict : le GPS ne supplante le lieu affiché que pour une carte rattachée par GPS."""

    def test_a_name_matched_card_keeps_its_displayed_location_even_if_gps_is_nearer_another_listed_city(self):
        deal = {"location": "Laval", "zone_city": "montreal"}               # nom reconnu : zone_rescued absent
        self.assertEqual(zone.bucket_city(deal), "Laval")

    def test_a_gps_rescued_card_is_bucketed_by_its_gps_city(self):
        deal = {"location": "Réunion, Reunion", "zone_city": "granby", "zone_rescued": True}
        self.assertEqual(zone.bucket_city(deal), "granby")

    def test_missing_fields_never_raise(self):
        self.assertEqual(zone.bucket_city({}), "")
        self.assertEqual(zone.bucket_city({"zone_rescued": True}), "")      # rattachée sans ville : retombe sur le lieu affiché
        self.assertEqual(zone.bucket_city({"location": None}), "")

if __name__ == "__main__":
    unittest.main()
