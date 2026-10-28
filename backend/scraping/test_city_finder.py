"""Tests de l'orchestration `CityFinder.lookup` avec un FAUX pilote (aucun Facebook, aucun Playwright en jeu).

Les scénarios reprennent des mesures réelles du 2026-10-23 (serveur au Québec, session anonyme) :
- « Bromont » : suggestions `Bromont | Ville` (×2) et `Bromont-Lamothe, Auvergne, France | Ville` ; l'ID
  110035235685771 (cartes : Riom, Clermont-Ferrand…) a été obtenu par DEUX clics différents, et le bouton de
  lieu de cette page affichait quand même « Bromont » — seule la géographie des cartes le démasque ;
  l'ID 103111009728836 a des cartes « Montréal, QC », « Longueuil, QC »…
"""
import unittest
from unittest.mock import MagicMock, patch

from backend.scraping import city_verification as cv
from backend.scraping.city_finder import (
    CityFinder, CityLookupResult, FacebookBlocked, LEGACY, ProbeResult, SelectResult,
)

FRANCE = "110035235685771"
QUEBEC = "103111009728836"
QUEBEC_CARDS = ["Montréal, QC"] * 10 + ["Longueuil, QC"] * 4 + ["Laval, QC"]
FRANCE_CARDS = ["Riom, ARA"] * 6 + ["Clermont-Ferrand, ARA"] * 6 + ["Issoire, ARA"] * 4
BROMONT_LABELS = ["Bromont | Ville", "Bromont | Ville", "Bromont-Lamothe, Auvergne, France | Ville"]


class FakeDriver:
    """`selects` : {(label, occurrence): SelectResult | Exception} ; `probes` : {id: ProbeResult}."""

    def __init__(self, labels, selects=None, probes=None):
        self.labels, self.selects, self.probes = labels, selects or {}, probes or {}
        self.select_calls, self.probe_calls = [], []

    def list_suggestions(self, city_name):
        return self.labels

    def select(self, city_name, label, occurrence=0):
        self.select_calls.append((label, occurrence))
        result = self.selects[(label, occurrence)]
        if isinstance(result, Exception):
            raise result
        return result

    def probe(self, city_id):
        self.probe_calls.append(city_id)
        return self.probes[city_id]


def sel(city_id, changed=True, segment=None):
    return SelectResult(city_id, segment or city_id, changed, None)


def landed(name):
    return f"{name} · Dans un rayon de 65 km"


class TestLookupBromont(unittest.TestCase):
    def test_quebec_id_is_verified_even_when_the_first_click_lands_on_the_french_id(self):
        driver = FakeDriver(
            BROMONT_LABELS,
            selects={("Bromont | Ville", 0): sel(FRANCE), ("Bromont | Ville", 1): sel(QUEBEC)},
            probes={FRANCE: ProbeResult(FRANCE_CARDS, landed("Bromont")), QUEBEC: ProbeResult(QUEBEC_CARDS, landed("Bromont"))},
        )
        result = CityFinder.lookup(driver, "Bromont", region_hint="Québec")
        self.assertEqual((result.status, result.city_id), (cv.VERIFIED, QUEBEC))
        self.assertEqual(driver.probe_calls, [FRANCE, QUEBEC])
        french = next(e for e in result.evidence if e["id"] == FRANCE)
        self.assertEqual(french["part_province"], 0.0)

    def test_the_french_suggestion_is_never_even_clicked(self):
        driver = FakeDriver(
            BROMONT_LABELS,
            selects={("Bromont | Ville", 0): sel(QUEBEC), ("Bromont | Ville", 1): sel(QUEBEC)},
            probes={QUEBEC: ProbeResult(QUEBEC_CARDS, landed("Bromont"))},
        )
        CityFinder.lookup(driver, "Bromont", region_hint="Québec")
        self.assertNotIn(("Bromont-Lamothe, Auvergne, France | Ville", 0), driver.select_calls)

    def test_same_id_from_two_clicks_is_probed_once(self):
        driver = FakeDriver(
            BROMONT_LABELS,
            selects={("Bromont | Ville", 0): sel(QUEBEC), ("Bromont | Ville", 1): sel(QUEBEC)},
            probes={QUEBEC: ProbeResult(QUEBEC_CARDS, landed("Bromont"))},
        )
        result = CityFinder.lookup(driver, "Bromont", region_hint="Québec")
        self.assertEqual(driver.probe_calls, [QUEBEC])
        self.assertEqual(result.status, cv.VERIFIED)

    def test_only_the_french_id_reachable_is_not_found_never_accepted(self):
        """Cas exact de la production : tous les clics donnent l'ID français."""
        driver = FakeDriver(
            BROMONT_LABELS,
            selects={("Bromont | Ville", 0): sel(FRANCE), ("Bromont | Ville", 1): sel(FRANCE)},
            probes={FRANCE: ProbeResult(FRANCE_CARDS, landed("Bromont"))},
        )
        result = CityFinder.lookup(driver, "Bromont", region_hint="Québec")
        self.assertEqual((result.status, result.city_id), (cv.NOT_FOUND, None))


class TestLookupDecisions(unittest.TestCase):
    def test_two_valid_distinct_ids_are_ambiguous_and_nothing_is_returned(self):
        driver = FakeDriver(
            ["Granby | Ville", "Granby, QC | Ville"],
            selects={("Granby | Ville", 0): sel("1"), ("Granby, QC | Ville", 0): sel("2")},
            probes={"1": ProbeResult(QUEBEC_CARDS, landed("Granby")), "2": ProbeResult(QUEBEC_CARDS, landed("Granby"))},
        )
        result = CityFinder.lookup(driver, "Granby", region_hint="Québec")
        self.assertEqual((result.status, result.city_id), (cv.AMBIGUOUS, None))

    def test_page_that_shows_another_city_cannot_validate(self):
        """Un clic « stale » renvoie l'ID de la ville précédente (Montréal) : québécois, mais pas Bromont."""
        driver = FakeDriver(
            ["Bromont | Ville"],
            selects={("Bromont | Ville", 0): sel("109294869089471")},
            probes={"109294869089471": ProbeResult(QUEBEC_CARDS, landed("Montreal"))},
        )
        result = CityFinder.lookup(driver, "Bromont", region_hint="Québec")
        self.assertEqual((result.status, result.city_id), (cv.NOT_FOUND, None))
        self.assertIn("n'affiche pas la ville demandée", result.detail)

    def test_feed_with_fewer_than_three_cards_is_indeterminate_not_accepted(self):
        driver = FakeDriver(
            ["Sutton | Ville"],
            selects={("Sutton | Ville", 0): sel("7")},
            probes={"7": ProbeResult(["Sutton, QC", "Sutton, QC"], landed("Sutton"))},
        )
        result = CityFinder.lookup(driver, "Sutton", region_hint="Québec")
        self.assertEqual((result.status, result.city_id), (cv.INDETERMINATE, None))

    def test_tiny_town_with_three_local_cards_is_verified(self):
        driver = FakeDriver(
            ["Bromont | Ville"],
            selects={("Bromont | Ville", 0): sel(QUEBEC)},
            probes={QUEBEC: ProbeResult(["Bromont, QC", "Granby, QC", "Bromont, QC"], landed("Bromont"))},
        )
        self.assertEqual(CityFinder.lookup(driver, "Bromont", region_hint="Québec").status, cv.VERIFIED)

    def test_proximity_rejects_a_quebec_homonym(self):
        gazetteer = {"montreal": (45.5, -73.57), "levis": (46.8, -71.18)}
        driver = FakeDriver(
            ["Saint-Lambert | Ville"],
            selects={("Saint-Lambert | Ville", 0): sel("5")},
            probes={"5": ProbeResult(["Lévis, QC"] * 4, landed("Saint-Lambert"))},
        )
        result = CityFinder.lookup(driver, "Saint-Lambert", region_hint="Québec",
                                   expected_coords=(45.50, -73.50), gazetteer=gazetteer)
        self.assertEqual((result.status, result.city_id), (cv.NOT_FOUND, None))

    def test_no_suggestion_matches_the_name_and_region(self):
        driver = FakeDriver(["Sherbrooke, AB | Ville"])
        result = CityFinder.lookup(driver, "Sherbrooke", region_hint="Québec")
        self.assertEqual((result.status, result.city_id), (cv.NOT_FOUND, None))
        self.assertEqual(driver.select_calls, [])  # l'Alberta n'est jamais cliquée

    def test_no_suggestions_at_all(self):
        self.assertEqual(CityFinder.lookup(FakeDriver([]), "X", region_hint="Québec").status, cv.NOT_FOUND)

    def test_text_alias_is_not_an_id(self):
        driver = FakeDriver(["Sherbrooke, QC | Ville"], selects={("Sherbrooke, QC | Ville", 0): sel(None, segment="edmonton")})
        result = CityFinder.lookup(driver, "Sherbrooke", region_hint="Québec")
        self.assertEqual((result.status, result.city_id), (cv.NOT_FOUND, None))
        self.assertIn("edmonton", str(result.evidence))

    def test_one_failing_click_does_not_prevent_trying_the_others(self):
        driver = FakeDriver(
            ["Granby | Ville", "Granby | Ville"],
            selects={("Granby | Ville", 0): LookupError("absente"), ("Granby | Ville", 1): sel("2")},
            probes={"2": ProbeResult(QUEBEC_CARDS, landed("Granby"))},
        )
        result = CityFinder.lookup(driver, "Granby", region_hint="Québec")
        self.assertEqual((result.status, result.city_id), (cv.VERIFIED, "2"))

    def test_blocked_by_facebook_propagates(self):
        driver = FakeDriver(["Granby | Ville"], selects={("Granby | Ville", 0): FacebookBlocked("login")})
        with self.assertRaises(FacebookBlocked):
            CityFinder.lookup(driver, "Granby", region_hint="Québec")


class TestLegacyWithoutProvince(unittest.TestCase):
    def test_no_hint_keeps_old_behavior_but_is_flagged_unverified(self):
        driver = FakeDriver(["Bromont | Ville"], selects={("Bromont | Ville", 0): sel(QUEBEC)})
        result = CityFinder.lookup(driver, "Bromont", region_hint=None)
        self.assertEqual((result.status, result.city_id), (LEGACY, QUEBEC))
        self.assertEqual(driver.probe_calls, [])

    def test_unknown_province_is_legacy(self):
        driver = FakeDriver(["Paris, Île-de-France, France | Ville"], selects={("Paris, Île-de-France, France | Ville", 0): sel("8")})
        self.assertEqual(CityFinder.lookup(driver, "Paris", region_hint="France").status, LEGACY)


class TestBackwardCompatibleTuple(unittest.TestCase):
    def _find(self, result):
        scraper = MagicMock()
        with patch.object(CityFinder, "lookup_with_scraper", return_value=result):
            return CityFinder.find_city_id_and_coords(scraper, "Bromont", "Québec")

    def test_verified(self):
        r = CityLookupResult(QUEBEC, {"lat": 1, "lon": 2}, "Bromont | Ville", cv.VERIFIED, "", [])
        self.assertEqual(self._find(r), (QUEBEC, {"lat": 1, "lon": 2}, "Bromont | Ville", True))

    def test_legacy_returns_id_but_not_confident(self):
        r = CityLookupResult(QUEBEC, None, "Bromont | Ville", LEGACY, "", [])
        self.assertEqual(self._find(r), (QUEBEC, None, "Bromont | Ville", False))

    def test_unverified_statuses_return_no_id(self):
        for status in (cv.AMBIGUOUS, cv.INDETERMINATE, cv.NOT_FOUND):
            r = CityLookupResult(None, None, None, status, "x", [])
            self.assertEqual(self._find(r), (None, None, None, False))

    def test_blocked_returns_no_id_instead_of_raising(self):
        scraper = MagicMock()
        with patch.object(CityFinder, "lookup_with_scraper", side_effect=FacebookBlocked("login")):
            self.assertEqual(CityFinder.find_city_id_and_coords(scraper, "X", "Québec"), (None, None, None, False))


if __name__ == "__main__":
    unittest.main()
