import json
import unittest

from scraping.parser import ListingParser
from scraping.kijiji.locations import (
    parse_locations_response,
    flatten_locations_tree,
    location_slug_from_seo_url,
    build_location_lookup,
    resolve_location,
    build_search_url,
    nearest_configured_city,
)

# Coordonnées réelles reprises de backend/resources/city_coordinates.json.
CITY_COORDINATES = {
    "montreal": {"lat": 45.5017, "lng": -73.5673},
    "quebec": {"lat": 46.8139, "lng": -71.2080},
    "longueuil": {"lat": 45.5369, "lng": -73.5105},
    "sherbrooke": {"lat": 45.4010, "lng": -71.8824},
}

# Extrait réel de https://www.kijiji.ca/j-locations.json?q=Quebec (test live du
# 2026-07-26) : 3 régions du Québec (Grand Montréal, Abitibi-Témiscamingue,
# Chaudière-Appalaches), chacune avec ses villes terminales (leaf: true).
SAMPLE_TREE = {
    "migratedLocation": True,
    "children": [
        {
            "migratedLocation": True,
            "children": [
                {"migratedLocation": True, "children": [], "nameFr": "Laval/Rive Nord", "regionLabel": None, "id": 1700278, "nameEn": "Laval / North Shore", "homePageSEOUrl": "/h-laval-rive-nord/1700278", "leaf": True},
                {"migratedLocation": True, "children": [], "nameFr": "Longueuil/Rive Sud", "regionLabel": None, "id": 1700279, "nameEn": "Longueuil / South Shore", "homePageSEOUrl": "/h-longueuil-rive-sud/1700279", "leaf": True},
                {"migratedLocation": True, "children": [], "nameFr": "Ouest de l'Île", "regionLabel": None, "id": 1700280, "nameEn": "West Island", "homePageSEOUrl": "/h-ouest-de-lile-qc/1700280", "leaf": True},
                {"migratedLocation": True, "children": [], "nameFr": "Ville de Montréal", "regionLabel": None, "id": 1700281, "nameEn": "City of Montréal", "homePageSEOUrl": "/h-ville-de-montreal/1700281", "leaf": True},
            ],
            "nameFr": "Grand Montréal", "regionLabel": "Québec", "id": 80002, "nameEn": "Greater Montréal", "homePageSEOUrl": "/h-grand-montreal/80002", "leaf": False,
        },
        {
            "migratedLocation": True,
            "children": [
                {"migratedLocation": True, "children": [], "nameFr": "Rouyn-Noranda", "regionLabel": None, "id": 1700060, "nameEn": "Rouyn-Noranda", "homePageSEOUrl": "/h-rouyn-noranda/1700060", "leaf": True},
                {"migratedLocation": True, "children": [], "nameFr": "Val-d'Or", "regionLabel": None, "id": 1700061, "nameEn": "Val-d'Or", "homePageSEOUrl": "/h-val-dor/1700061", "leaf": True},
            ],
            "nameFr": "Abitibi-Témiscamingue", "regionLabel": "Québec", "id": 1700059, "nameEn": "Abitibi-Témiscamingue", "homePageSEOUrl": "/h-abitibi-temiscamingue/1700059", "leaf": False,
        },
        {
            "migratedLocation": True,
            "children": [
                {"migratedLocation": True, "children": [], "nameFr": "Lévis", "regionLabel": None, "id": 1700063, "nameEn": "Lévis", "homePageSEOUrl": "/h-levis/1700063", "leaf": True},
                {"migratedLocation": True, "children": [], "nameFr": "Thetford Mines", "regionLabel": None, "id": 1700064, "nameEn": "Thetford Mines", "homePageSEOUrl": "/h-thetford-mines/1700064", "leaf": True},
                {"migratedLocation": True, "children": [], "nameFr": "St-Georges-de-Beauce", "regionLabel": None, "id": 1700065, "nameEn": "St-Georges-de-Beauce", "homePageSEOUrl": "/h-st-georges-de-beauce/1700065", "leaf": True},
            ],
            "nameFr": "Chaudière-Appalaches", "regionLabel": "Québec", "id": 1700062, "nameEn": "Chaudière-Appalaches", "homePageSEOUrl": "/h-chaudiere-appalaches/1700062", "leaf": False,
        },
    ],
}


class TestParseLocationsResponse(unittest.TestCase):
    def test_strips_js_var_wrapper(self):
        raw = "var locationsTree = " + json.dumps(SAMPLE_TREE) + ";"
        self.assertEqual(parse_locations_response(raw), SAMPLE_TREE)

    def test_accepts_pure_json(self):
        raw = json.dumps(SAMPLE_TREE)
        self.assertEqual(parse_locations_response(raw), SAMPLE_TREE)


class TestFlattenLocationsTree(unittest.TestCase):
    def test_collects_only_leaves(self):
        leaves = flatten_locations_tree(SAMPLE_TREE)
        ids = {leaf["id"] for leaf in leaves}
        # Les régions (Grand Montréal=80002, Abitibi-Témiscamingue=1700059,
        # Chaudière-Appalaches=1700062) ne sont PAS des lieux de recherche valides.
        self.assertNotIn(80002, ids)
        self.assertNotIn(1700059, ids)
        self.assertNotIn(1700062, ids)
        self.assertEqual(len(leaves), 9)
        self.assertIn(1700279, ids)  # Longueuil / South Shore

    def test_leaf_has_expected_fields(self):
        leaves = flatten_locations_tree(SAMPLE_TREE)
        longueuil = next(l for l in leaves if l["id"] == 1700279)
        self.assertEqual(longueuil["nameEn"], "Longueuil / South Shore")
        self.assertEqual(longueuil["nameFr"], "Longueuil/Rive Sud")
        self.assertEqual(longueuil["homePageSEOUrl"], "/h-longueuil-rive-sud/1700279")


class TestLocationSlugFromSeoUrl(unittest.TestCase):
    def test_extracts_slug(self):
        self.assertEqual(location_slug_from_seo_url("/h-longueuil-rive-sud/1700279"), "longueuil-rive-sud")

    def test_returns_none_for_empty(self):
        self.assertIsNone(location_slug_from_seo_url(None))
        self.assertIsNone(location_slug_from_seo_url(""))


class TestBuildLocationLookup(unittest.TestCase):
    def setUp(self):
        self.lookup = build_location_lookup(flatten_locations_tree(SAMPLE_TREE))

    def test_english_name_resolves(self):
        key = ListingParser.normalize_city_name("Longueuil / South Shore")
        self.assertEqual(self.lookup[key]["id"], 1700279)

    def test_french_name_resolves(self):
        key = ListingParser.normalize_city_name("Longueuil/Rive Sud")
        self.assertEqual(self.lookup[key]["id"], 1700279)

    def test_slug_captured(self):
        key = ListingParser.normalize_city_name("Val-d'Or")
        self.assertEqual(self.lookup[key]["slug"], "val-dor")


class TestResolveLocation(unittest.TestCase):
    def setUp(self):
        self.lookup = build_location_lookup(flatten_locations_tree(SAMPLE_TREE))

    def test_exact_match(self):
        result = resolve_location("Rouyn-Noranda", self.lookup)
        self.assertEqual(result["id"], 1700060)

    def test_prefix_match_for_slash_grouped_regions(self):
        """Régression : Kijiji regroupe Longueuil sous "Longueuil / South Shore" — une
        recherche pour juste "Longueuil" doit quand même résoudre vers 1700279."""
        result = resolve_location("Longueuil", self.lookup)
        self.assertEqual(result["id"], 1700279)

    def test_no_match_returns_none(self):
        self.assertIsNone(resolve_location("Ville Inexistante Xyz", self.lookup))

    def test_empty_lookup_returns_none(self):
        self.assertIsNone(resolve_location("Longueuil", {}))

    def test_empty_city_name_returns_none(self):
        self.assertIsNone(resolve_location("", self.lookup))

    def test_partial_substring_match_no_longer_resolves(self):
        """Régression (2026-07-27) : un ancien 3e palier de repli par correspondance
        partielle/substring a été retiré — validé empiriquement contre les 192 lieux
        Kijiji réels et les 839 municipalités QC (`city_coordinates.json`), il matchait
        à tort des villes québécoises vers des lieux homonymes d'AUTRES provinces (voir
        les cas ci-dessous, tous réellement observés). Un simple lien "un seul candidat
        partiel" (ex: "springfield nord" pour "Springfield") ne doit plus résoudre du
        tout : mieux vaut ignorer la ville pour Kijiji (loggé par l'appelant) qu'un
        risque de scanner la mauvaise province silencieusement."""
        lookup = {"springfield nord": {"id": 111, "slug": "springfield-nord"}}
        self.assertIsNone(resolve_location("Springfield", lookup))

    def test_cross_province_homonym_no_longer_false_matches(self):
        """Régression (2026-07-27) : cas réels observés avec l'ancien palier substring —
        des municipalités québécoises matchaient à tort un lieu Kijiji homonyme d'une
        autre province, faute de contexte géographique dans une simple comparaison de
        chaînes ("Waterloo" (QC) vers "Kitchener / Waterloo" (ON), "Abbotsford" (QC,
        Saint-Paul-d'Abbotsford) vers "Abbotsford" (BC), "Stoke" (QC) vers "Revelstoke"
        (BC), "Oka" (QC) vers "Muskoka" (ON))."""
        lookup = {
            "kitchener / waterloo": {"id": 1, "slug": "kitchener-waterloo"},
            "abbotsford": {"id": 2, "slug": "abbotsford"},
            "revelstoke": {"id": 3, "slug": "revelstoke"},
            "muskoka": {"id": 4, "slug": "muskoka"},
        }
        self.assertIsNone(resolve_location("Waterloo", lookup))
        self.assertIsNone(resolve_location("Saint-Paul-d'Abbotsford", lookup))
        self.assertIsNone(resolve_location("Stoke", lookup))
        self.assertIsNone(resolve_location("Oka", lookup))

    def test_quebec_city_no_longer_ambiguous_with_chibougamau(self):
        """Régression (2026-07-27) : cas réel observé avec les 192 lieux Kijiji —
        "Québec" matchait partiellement à la fois "Ville de Québec" (le bon lieu) ET
        "Chibougamau / Nord-du-Québec" (mot "quebec" partagé, lieu totalement
        différent), rendant la résolution ambiguë (`None`) pour l'une des villes les
        plus probables à être configurées dans cette appli. Sans palier substring, plus
        d'ambiguïté possible — mais "Québec" seul (sans "City"/"Ville de") ne matche
        plus non plus (aucun des deux paliers restants ne le couvre) : limitation
        connue, voir TODO.md."""
        lookup = {
            "chibougamau / nord du quebec": {"id": 1700284, "slug": "chibougamau-nord-du-quebec"},
            "quebec city": {"id": 1700124, "slug": "ville-de-quebec"},
            "ville de quebec": {"id": 1700124, "slug": "ville-de-quebec"},
        }
        self.assertEqual(resolve_location("Quebec City", lookup)["id"], 1700124)
        self.assertEqual(resolve_location("Ville de Quebec", lookup)["id"], 1700124)
        self.assertIsNone(resolve_location("Quebec", lookup))


class TestBuildSearchUrl(unittest.TestCase):
    def test_builds_expected_pattern(self):
        url = build_search_url(613, 1700279, "guitare électrique", category_slug="guitar", location_slug="longueuil-rive-sud")
        self.assertEqual(url, "https://www.kijiji.ca/b-guitar/longueuil-rive-sud/guitare-electrique/k0c613l1700279")

    def test_query_with_special_characters_is_slugified(self):
        url = build_search_url(613, 1700279, "Ampli 100W (Marshall)!")
        self.assertIn("ampli-100w-marshall", url)

    def test_defaults_used_when_slugs_not_provided(self):
        url = build_search_url(613, 1700279, "guitare")
        self.assertEqual(url, "https://www.kijiji.ca/b-recherche/lieu/guitare/k0c613l1700279")


class TestNearestConfiguredCity(unittest.TestCase):
    """`nearest_configured_city` sert à contourner l'imprécision de `location.name`
    (choix du vendeur, incohérent — voir docs/reference/ARCHITECTURE.md § kijiji/) en
    utilisant les coordonnées GPS de l'annonce à la place."""

    # Sainte-Julie, QC (~15 km de Longueuil, la plus proche des 4 villes configurées).
    SAINTE_JULIE = (45.5906, -73.3306)

    def test_returns_nearest_city(self):
        lat, lng = self.SAINTE_JULIE
        result = nearest_configured_city(lat, lng, CITY_COORDINATES)
        self.assertEqual(result["city"], "longueuil")
        self.assertTrue(10 < result["distance_km"] < 20, result)

    def test_respects_max_radius_km_excludes_too_far(self):
        lat, lng = self.SAINTE_JULIE
        result = nearest_configured_city(lat, lng, CITY_COORDINATES, max_radius_km=10)
        self.assertIsNone(result)

    def test_respects_max_radius_km_includes_within_range(self):
        lat, lng = self.SAINTE_JULIE
        result = nearest_configured_city(lat, lng, CITY_COORDINATES, max_radius_km=20)
        self.assertEqual(result["city"], "longueuil")

    def test_returns_none_for_missing_coordinates(self):
        self.assertIsNone(nearest_configured_city(None, -73.5105, CITY_COORDINATES))
        self.assertIsNone(nearest_configured_city(45.5369, None, CITY_COORDINATES))

    def test_returns_none_for_empty_city_coordinates(self):
        self.assertIsNone(nearest_configured_city(45.5369, -73.5105, {}))

    def test_ignores_malformed_entries(self):
        malformed = {"broken": {"lat": 45.5}, "longueuil": {"lat": 45.5369, "lng": -73.5105}}
        lat, lng = self.SAINTE_JULIE
        result = nearest_configured_city(lat, lng, malformed)
        self.assertEqual(result["city"], "longueuil")

    def test_non_numeric_coordinates_do_not_win_as_false_zero_distance(self):
        """Régression : scraping.utils.calculate_distance() capture toute exception et
        retourne 0 — sans validation de type explicite, une entrée avec des lat/lng non
        numériques (ex: chaîne malformée dans city_coordinates) ferait planter
        math.radians(), calculate_distance renverrait 0, et cette entrée "gagnerait"
        silencieusement comme ville la plus proche (0 étant la distance minimale
        possible), peu importe la vraie ville la plus proche."""
        bad_coords = {
            "faux": {"lat": "not-a-number", "lng": -73.5},
            "longueuil": {"lat": 45.5369, "lng": -73.5105},
        }
        lat, lng = self.SAINTE_JULIE
        result = nearest_configured_city(lat, lng, bad_coords)
        self.assertEqual(result["city"], "longueuil")

    def test_non_numeric_input_coordinates_return_none(self):
        self.assertIsNone(nearest_configured_city("not-a-number", -73.5105, CITY_COORDINATES))

    def test_boolean_coordinates_are_not_treated_as_numbers(self):
        """`bool` est une sous-classe d'`int` en Python — `True`/`False` ne doivent pas
        être acceptés comme coordonnées valides."""
        bad_coords = {"faux": {"lat": True, "lng": False}}
        self.assertIsNone(nearest_configured_city(45.5369, -73.5105, bad_coords))


if __name__ == "__main__":
    unittest.main()
