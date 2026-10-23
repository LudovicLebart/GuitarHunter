"""Tests purs (sans Facebook ni base) de `backend/scraping/city_verification.py`.

Les cas reprennent des mesures RÉELLES du 2026-10-23 (serveur au Québec, session anonyme)."""
import unittest

from backend.scraping import city_verification as cv


class TestParseLabel(unittest.TestCase):
    def test_local_label_has_no_region(self):
        self.assertEqual(cv.parse_label("Bromont | Ville"), ("Bromont", None))
        self.assertEqual(cv.parse_label("Bromont\nVille"), ("Bromont", None))

    def test_foreign_label_keeps_region(self):
        self.assertEqual(cv.parse_label("Bromont-Lamothe, Auvergne, France | Ville"), ("Bromont-Lamothe", "Auvergne, France"))
        self.assertEqual(cv.parse_label("Sherbrooke, AB"), ("Sherbrooke", "AB"))
        self.assertEqual(cv.parse_label("Beloeil, Hainaut, Belgium | Ville"), ("Beloeil", "Hainaut, Belgium"))

    def test_empty(self):
        self.assertEqual(cv.parse_label(""), ("", None))
        self.assertEqual(cv.parse_label(None), ("", None))


class TestProvinceCode(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(cv.province_code("Québec"), "QC")
        self.assertEqual(cv.province_code("Quebec, Canada"), "QC")
        self.assertEqual(cv.province_code("ON"), "ON")
        self.assertIsNone(cv.province_code("Auvergne"))
        self.assertIsNone(cv.province_code(""))


class TestRegionCompatible(unittest.TestCase):
    def test_absent_region_is_local_and_compatible(self):
        self.assertTrue(cv.region_compatible(None, "Québec"))

    def test_explicit_variants_match(self):
        self.assertTrue(cv.region_compatible("QC", "Québec"))
        self.assertTrue(cv.region_compatible("Quebec, Canada", "Québec"))

    def test_foreign_or_other_province_rejected(self):
        self.assertFalse(cv.region_compatible("Auvergne, France", "Québec"))
        self.assertFalse(cv.region_compatible("Hainaut, Belgium", "Québec"))
        self.assertFalse(cv.region_compatible("AB", "Québec"))

    def test_word_boundaries(self):
        self.assertFalse(cv.region_compatible("Aqcx", "Québec"))  # « qc » ne doit pas matcher dans un mot


class TestFilterCandidates(unittest.TestCase):
    def indexes(self, labels, city, hint="Québec"):
        return [c["index"] for c in cv.filter_candidates(labels, city, hint)]

    def test_bromont_drops_the_french_homonym(self):
        labels = ["Bromont | Ville", "Bromont | Ville", "Bromont-Lamothe, Auvergne, France | Ville"]
        self.assertEqual(self.indexes(labels, "Bromont"), [0, 1])

    def test_beloeil_belgium_excluded(self):
        self.assertEqual(self.indexes(["Beloeil, Hainaut, Belgium | Ville", "Beloeil | Ville"], "Beloeil"), [1])

    def test_woluwe_saint_lambert_is_not_saint_lambert(self):
        self.assertEqual(self.indexes(["Woluwe-Saint-Lambert | Ville", "Saint-Lambert | Ville"], "Saint-lambert"), [1])

    def test_abbreviation_st_matches_saint(self):
        self.assertEqual(self.indexes(["St-Hubert, QC | Ville"], "Saint-Hubert"), [0])

    def test_sherbrooke_alberta_excluded_quebec_kept(self):
        self.assertEqual(self.indexes(["Sherbrooke, AB | Ville", "Sherbrooke, QC | Ville"], "Sherbrooke"), [1])

    def test_local_labels_come_first(self):
        labels = ["Longueuil, QC | Ville", "Longueuil | Ville"]
        self.assertEqual(self.indexes(labels, "Longueuil"), [1, 0])

    def test_nothing_matches(self):
        self.assertEqual(self.indexes(["Réunion | Ville"], "La saline"), [])


class TestParseCardLocation(unittest.TestCase):
    def test_cards(self):
        self.assertEqual(cv.parse_card_location("Montréal, QC"), ("Montréal", "QC"))
        self.assertEqual(cv.parse_card_location("Riom, ARA"), ("Riom", "ARA"))
        self.assertEqual(cv.parse_card_location("Montréal"), ("Montréal", None))


QUEBEC_CARDS = ["Montréal, QC"] * 14 + ["Longueuil, QC"] * 2 + ["St-Jean-sur-Richelieu, QC"] * 2 + ["McMasterville, QC", "St-Lambert, QC", "Boucherville, QC"] + ["Laval, QC", "Valcourt, QC", "St-Rémi, QC"]
FRANCE_CARDS = ["Riom, ARA"] * 6 + ["Clermont-Ferrand, ARA"] * 6 + ["Issoire, ARA"] * 4 + ["Chénérailles, NAQ"] * 4 + ["Nevers, BFC"] * 2


class TestScoreProbe(unittest.TestCase):
    def test_real_quebec_bromont_feed(self):
        s = cv.score_probe(QUEBEC_CARDS, "QC")
        self.assertEqual(s["n"], len(QUEBEC_CARDS))
        self.assertEqual(s["part_province"], 1.0)
        self.assertIsNone(s["part_near"])

    def test_real_french_bromont_feed(self):
        self.assertEqual(cv.score_probe(FRANCE_CARDS, "QC")["part_province"], 0.0)

    def test_empty_feed(self):
        self.assertEqual(cv.score_probe([], "QC"), {"n": 0, "part_province": 0.0, "part_near": None})

    def test_proximity_separates_homonyms_of_the_same_province(self):
        gazetteer = {"montreal": (45.5, -73.57), "levis": (46.8, -71.18), "quebec": (46.81, -71.21), "longueuil": (45.54, -73.51)}
        saint_lambert = (45.50, -73.50)
        near = cv.score_probe(["Montréal, QC", "Longueuil, QC"], "QC", saint_lambert, gazetteer)
        far = cv.score_probe(["Lévis, QC", "Québec, QC", "Lévis, QC"], "QC", saint_lambert, gazetteer)
        self.assertEqual(near["part_near"], 1.0)
        self.assertEqual(far["part_near"], 0.0)
        self.assertEqual(far["part_province"], 1.0)  # « QC » seul ne suffit pas à les distinguer

    def test_unknown_cities_do_not_count_for_proximity(self):
        s = cv.score_probe(["Laval, QC", "Valcourt, QC"], "QC", (45.3, -72.6), {"montreal": (45.5, -73.57)})
        self.assertIsNone(s["part_near"])


def cand(cid, cards, **kw):
    return {"id": cid, **cv.score_probe(cards, "QC", **kw)}


class TestDecide(unittest.TestCase):
    def test_bromont_quebec_verified_against_france(self):
        d = cv.decide([cand("110035235685771", FRANCE_CARDS), cand("103111009728836", QUEBEC_CARDS)])
        self.assertEqual((d.status, d.city_id), (cv.VERIFIED, "103111009728836"))

    def test_duplicate_id_in_candidates_is_one_candidate(self):
        d = cv.decide([cand("1", QUEBEC_CARDS), cand("1", QUEBEC_CARDS)])
        self.assertEqual((d.status, d.city_id), (cv.VERIFIED, "1"))

    def test_two_distinct_valid_ids_are_ambiguous(self):
        d = cv.decide([cand("1", QUEBEC_CARDS), cand("2", QUEBEC_CARDS)])
        self.assertEqual((d.status, d.city_id), (cv.AMBIGUOUS, None))

    def test_tiny_town_with_three_cards_is_decided_no_large_minimum(self):
        d = cv.decide([cand("9", ["Bromont, QC", "Granby, QC", "Bromont, QC"])])
        self.assertEqual(d.status, cv.VERIFIED)

    def test_fewer_than_three_cards_is_indeterminate_not_a_failure(self):
        d = cv.decide([cand("9", ["Bromont, QC"]), cand("8", [])])
        self.assertEqual((d.status, d.city_id), (cv.INDETERMINATE, None))

    def test_probed_but_none_valid_is_not_found(self):
        d = cv.decide([cand("1", FRANCE_CARDS)])
        self.assertEqual((d.status, d.city_id), (cv.NOT_FOUND, None))
        self.assertIn("1", d.detail)

    def test_quebec_homonym_rejected_by_proximity(self):
        gazetteer = {"lévis": (46.8, -71.18), "levis": (46.8, -71.18), "quebec": (46.81, -71.21)}
        far = cand("5", ["Lévis, QC", "Québec, QC", "Lévis, QC"], expected_coords=(45.5, -73.5), gazetteer=gazetteer)
        self.assertEqual(cv.decide([far]).status, cv.NOT_FOUND)

    def test_unprobed_candidate_does_not_block_a_verified_one(self):
        d = cv.decide([cand("1", QUEBEC_CARDS), cand("2", [])])
        self.assertEqual((d.status, d.city_id), (cv.VERIFIED, "1"))

    def test_empty_input(self):
        self.assertEqual(cv.decide([]).status, cv.INDETERMINATE)


if __name__ == "__main__":
    unittest.main()
