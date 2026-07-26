import json
import unittest

from scraping.kijiji.core import KijijiScraper
from scraping.kijiji.parser import KijijiListingParser


class FakePage:
    """Double minimal de playwright.sync_api.Page — seul `.url` est lu par _is_valid_detail_page."""
    def __init__(self, url):
        self.url = url


class FakeLocator:
    """Double minimal de playwright.sync_api.Locator — juste ce dont parse_details_page a besoin."""
    def __init__(self, text=None, count=0):
        self._text = text
        self._count = count

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def inner_text(self):
        return self._text or ""

    def get_attribute(self, name):
        return None

    def all(self):
        return []


class FakeNextDataPage:
    """Double minimal de Page pour tester parse_details_page via __NEXT_DATA__. Seuls
    `.url` et `.locator('script#__NEXT_DATA__')` sont exercés dans le cas nominal
    observé en test live (__NEXT_DATA__ fournit déjà title/description/price/location/
    images, donc les autres sélecteurs — JSON-LD, DOM — ne sont jamais appelés)."""
    def __init__(self, url, next_data_json_text):
        self.url = url
        self._next_data_json_text = next_data_json_text

    def locator(self, selector):
        if selector == "script#__NEXT_DATA__":
            return FakeLocator(text=self._next_data_json_text, count=1)
        return FakeLocator(count=0)


# Structure réelle observée en test live du 2026-07-26 (annonce Kijiji 1740804650,
# Longueuil), simplifiée aux champs consommés par KijijiListingParser.
NEXT_DATA_SAMPLE = {
    "props": {
        "pageProps": {
            "listingId": "1740804650",
            "__APOLLO_STATE__": {
                "StandardListing:1740804650": {
                    "__typename": "StandardListing",
                    "id": "1740804650",
                    "description": "Guitare fonctionne parfaitement viens avec un ampli et des corde de rechange.",
                    "imageUrls": [
                        "https://media.kijiji.ca/api/v1/ca-prod-fsbo-ads/images/4e/1.jpg",
                        "https://media.kijiji.ca/api/v1/ca-prod-fsbo-ads/images/83/2.jpg",
                    ],
                    "price": {"__typename": "StandardAmountPrice", "amount": 22000, "currency": "CAD"},
                    "location": {
                        "__typename": "ListingLocation",
                        "id": 1700279,
                        "name": "Longueuil / South Shore",
                        "coordinates": {"__typename": "LocationCoordinates", "latitude": 45.58, "longitude": -73.32},
                    },
                },
                "Category:613": {"__typename": "Category", "id": 613},
            },
        }
    }
}

# Structure réelle observée en test live du 2026-07-26 sur une page de RÉSULTATS de
# recherche (b-guitare/longueuil-rive-sud/.../k0c613l1700279) : plusieurs StandardListing
# au même niveau, chacun avec une seule URL d'aperçu (contrairement à la fiche détail).
NEXT_DATA_SEARCH_RESULTS_SAMPLE = {
    "props": {
        "pageProps": {
            "__APOLLO_STATE__": {
                "StandardListing:1740804650": {
                    "__typename": "StandardListing",
                    "id": "1740804650",
                    "title": "Guitare electrique ",
                    "description": "Guitare fonctionne parfaitement viens avec un ampli et des corde de rechange.",
                    "imageCount": 4,
                    "imageUrls": ["https://media.kijiji.ca/api/v1/ca-prod-fsbo-ads/images/4e/1.jpg"],
                    "url": "https://www.kijiji.ca/v-guitar/longueuil-rive-sud/guitare-electrique/1740804650",
                    "price": {"__typename": "StandardAmountPrice", "amount": 22000},
                    "location": {"__typename": "ListingLocation", "id": 1700279, "name": "Longueuil / South Shore"},
                },
                "StandardListing:1741128618": {
                    "__typename": "StandardListing",
                    "id": "1741128618",
                    "title": "Ensemble Guitare acoustique et accessoires",
                    "description": "A vendre guitare Beaver Creek et accessoires",
                    "imageCount": 6,
                    "imageUrls": ["https://media.kijiji.ca/api/v1/ca-prod-fsbo-ads/images/aa/1.jpg"],
                    "url": "https://www.kijiji.ca/v-guitar/longueuil-rive-sud/ensemble-guitare-acoustique-et-accessoires/1741128618",
                    "price": {"__typename": "StandardAmountPrice", "amount": 12000},
                    "location": {"__typename": "ListingLocation", "id": 1700279, "name": "Saint-Bruno-de-Montarville"},
                },
                "Category:613": {"__typename": "Category", "id": 613},
                "Location:1700279": {"__typename": "Location", "id": 1700279},
            },
        }
    }
}

# Deux villes différentes pour vérifier que l'extraction du lieu/prix n'est pas figée
# sur une seule ville (Longueuil, dans les échantillons ci-dessus) — Sainte-Julie est
# une vraie annonce vue dans les résultats "hors rayon" du test live du 2026-07-26 ;
# Québec est une entrée synthétique (même schéma StandardListing) pour couvrir une
# ville bien plus éloignée, toutes deux étant des villes réellement configurables comme
# zones de scan dans l'app (docs/reference/ARCHITECTURE.md § Villes & Géocodage).
STANDARD_LISTING_SAINTE_JULIE = {
    "__typename": "StandardListing",
    "id": "1732987805",
    "title": "Pédale de guitare Marshall Bluesbreaker II ( BB-2 )",
    "description": "Le son Blues d'un Marshall dans une pédale. Vérifiée et tout fonctionne.",
    "imageCount": 3,
    "imageUrls": ["https://media.kijiji.ca/api/v1/ca-prod-fsbo-ads/images/bb/1.jpg"],
    "url": "https://www.kijiji.ca/v-guitar/longueuil-rive-sud/pedale-de-guitare-marshall-bluesbreaker-ii-bb-2/1732987805",
    "price": {"__typename": "StandardAmountPrice", "amount": 10000},
    "location": {"__typename": "ListingLocation", "id": 1700433, "name": "Sainte-Julie"},
}
STANDARD_LISTING_QUEBEC = {
    "__typename": "StandardListing",
    "id": "9999999999",
    "title": "Guitare classique Québec",
    "description": "Guitare classique en bon état, à vendre à Québec.",
    "imageCount": 2,
    "imageUrls": ["https://media.kijiji.ca/api/v1/ca-prod-fsbo-ads/images/qc/1.jpg"],
    "url": "https://www.kijiji.ca/v-guitar/quebec-city/guitare-classique-quebec/9999999999",
    "price": {"__typename": "StandardAmountPrice", "amount": 15000},
    "location": {"__typename": "ListingLocation", "id": 1700423, "name": "Québec"},
}
NEXT_DATA_MULTI_CITY_SAMPLE = {
    "props": {
        "pageProps": {
            "__APOLLO_STATE__": {
                "StandardListing:1732987805": STANDARD_LISTING_SAINTE_JULIE,
                "StandardListing:9999999999": STANDARD_LISTING_QUEBEC,
                "Category:613": {"__typename": "Category", "id": 613},
            },
        }
    }
}


class TestExtractKijijiId(unittest.TestCase):
    def test_standard_ad_url(self):
        url = "https://www.kijiji.ca/v-guitars-amps/city-of-montreal/fender-stratocaster/1234567890"
        self.assertEqual(KijijiListingParser.extract_kijiji_id(url), "1234567890")

    def test_ad_url_with_query_params(self):
        url = "https://www.kijiji.ca/v-guitars-amps/city-of-montreal/gibson-les-paul/9876543210?enableSearchNavigationFlag=true"
        self.assertEqual(KijijiListingParser.extract_kijiji_id(url), "9876543210")

    def test_non_ad_url_returns_none(self):
        self.assertIsNone(KijijiListingParser.extract_kijiji_id("https://www.kijiji.ca/b-canada/guitare/k0"))

    def test_empty_url_returns_none(self):
        self.assertIsNone(KijijiListingParser.extract_kijiji_id(""))

    def test_intermediate_numeric_segment_does_not_shadow_trailing_id(self):
        """Régression : un segment numérique intermédiaire (ex: code de lieu/catégorie)
        ne doit pas être pris pour l'ID — seul le dernier segment du chemin compte."""
        url = "https://www.kijiji.ca/v-guitares-basses/12345/city-slug/987654321"
        self.assertEqual(KijijiListingParser.extract_kijiji_id(url), "987654321")

    def test_trailing_slash_is_handled(self):
        url = "https://www.kijiji.ca/v-guitars-amps/city-of-montreal/fender-stratocaster/1234567890/"
        self.assertEqual(KijijiListingParser.extract_kijiji_id(url), "1234567890")


class TestExtractLocationSlug(unittest.TestCase):
    def test_real_url_from_live_test(self):
        """URL testée en conditions réelles le 2026-07-26 — JSON-LD/DOM ne donnaient pas
        de localisation, ce repli doit la fournir."""
        url = "https://www.kijiji.ca/v-guitar/longueuil-rive-sud/guitare-electrique/1740804650"
        self.assertEqual(KijijiListingParser.extract_location_slug(url), "Longueuil Rive Sud")

    def test_non_ad_url_returns_none(self):
        self.assertIsNone(KijijiListingParser.extract_location_slug("https://www.kijiji.ca/b-canada/guitare/k0"))

    def test_empty_url_returns_none(self):
        self.assertIsNone(KijijiListingParser.extract_location_slug(""))


class TestIsValidDetailPage(unittest.TestCase):
    def setUp(self):
        self.scraper = KijijiScraper()

    def test_valid_detail_page(self):
        page = FakePage("https://www.kijiji.ca/v-guitars-amps/city-of-montreal/fender-stratocaster/1234567890")
        self.assertTrue(self.scraper._is_valid_detail_page(page, "1234567890"))

    def test_redirect_to_login_is_invalid(self):
        page = FakePage("https://www.kijiji.ca/login/?next=%2F")
        self.assertFalse(self.scraper._is_valid_detail_page(page, "1234567890"))

    def test_mismatched_id_is_invalid(self):
        page = FakePage("https://www.kijiji.ca/v-guitars-amps/city-of-montreal/fender-stratocaster/0000000000")
        self.assertFalse(self.scraper._is_valid_detail_page(page, "1234567890"))

    def test_shorter_id_substring_of_longer_id_is_invalid(self):
        """Régression : "123" ne doit pas être validé juste parce qu'il apparaît comme
        sous-chaîne d'un ID plus long ("45123") ailleurs dans l'URL."""
        page = FakePage("https://www.kijiji.ca/v-guitars-amps/city-of-montreal/fender-stratocaster/45123")
        self.assertFalse(self.scraper._is_valid_detail_page(page, "123"))


class TestConstructorIsKeywordOnly(unittest.TestCase):
    def test_positional_args_are_rejected(self):
        """Régression : évite qu'un futur appel copié-collé depuis FacebookScraper(...)
        (arguments positionnels) lie silencieusement les mauvaises valeurs à config/logger."""
        with self.assertRaises(TypeError):
            KijijiScraper({}, {})


class TestExtractImagesFromJsonLd(unittest.TestCase):
    def test_single_string_image(self):
        result = KijijiListingParser._extract_images_from_json_ld({"image": "https://x/1.jpg"})
        self.assertEqual(result, ["https://x/1.jpg"])

    def test_list_of_strings(self):
        result = KijijiListingParser._extract_images_from_json_ld(
            {"image": ["https://x/1.jpg", "https://x/2.jpg"]}
        )
        self.assertEqual(result, ["https://x/1.jpg", "https://x/2.jpg"])

    def test_list_of_image_objects(self):
        result = KijijiListingParser._extract_images_from_json_ld(
            {"image": [{"@type": "ImageObject", "url": "https://x/1.jpg"}]}
        )
        self.assertEqual(result, ["https://x/1.jpg"])

    def test_missing_image_key_returns_empty_list(self):
        self.assertEqual(KijijiListingParser._extract_images_from_json_ld({}), [])


class TestPickStandardListing(unittest.TestCase):
    def test_direct_path(self):
        result = KijijiListingParser._pick_standard_listing(NEXT_DATA_SAMPLE)
        self.assertEqual(result["id"], "1740804650")
        self.assertEqual(result["location"]["name"], "Longueuil / South Shore")

    def test_fallback_scan_when_listing_id_missing(self):
        """Régression : si le chemin direct (pageProps.listingId) change/disparaît, on
        retrouve quand même l'annonce en scannant les clés StandardListing: de l'état Apollo."""
        data = json.loads(json.dumps(NEXT_DATA_SAMPLE))  # copie profonde
        del data["props"]["pageProps"]["listingId"]
        result = KijijiListingParser._pick_standard_listing(data)
        self.assertEqual(result["id"], "1740804650")

    def test_returns_none_when_no_standard_listing(self):
        data = {"props": {"pageProps": {"__APOLLO_STATE__": {"Category:613": {"__typename": "Category"}}}}}
        self.assertIsNone(KijijiListingParser._pick_standard_listing(data))

    def test_returns_none_on_malformed_input(self):
        self.assertIsNone(KijijiListingParser._pick_standard_listing({}))


class TestPickAllStandardListings(unittest.TestCase):
    """Basé sur la structure réelle d'une page de résultats de recherche Kijiji
    (test live du 2026-07-26, b-guitare/longueuil-rive-sud/.../k0c613l1700279) —
    plusieurs StandardListing au même niveau, indexés par ID."""

    def test_extracts_all_listings_indexed_by_id(self):
        result = KijijiListingParser._pick_all_standard_listings(NEXT_DATA_SEARCH_RESULTS_SAMPLE)
        self.assertEqual(set(result.keys()), {"1740804650", "1741128618"})
        self.assertEqual(result["1740804650"]["title"], "Guitare electrique ")
        self.assertEqual(result["1741128618"]["price"]["amount"], 12000)

    def test_ignores_non_listing_entries(self):
        result = KijijiListingParser._pick_all_standard_listings(NEXT_DATA_SEARCH_RESULTS_SAMPLE)
        self.assertNotIn("613", result)
        self.assertNotIn("1700279", result)

    def test_returns_empty_dict_when_no_standard_listing(self):
        data = {"props": {"pageProps": {"__APOLLO_STATE__": {"Category:613": {"__typename": "Category"}}}}}
        self.assertEqual(KijijiListingParser._pick_all_standard_listings(data), {})

    def test_returns_empty_dict_on_malformed_input(self):
        self.assertEqual(KijijiListingParser._pick_all_standard_listings({}), {})


class TestPickAllStandardListingsMultipleCities(unittest.TestCase):
    """Régression : l'extraction ne doit pas être accidentellement figée sur une seule
    ville (Longueuil, dans les autres échantillons de ce fichier) — vérifié ici avec
    Sainte-Julie et Québec, deux villes réellement configurables comme zones de scan
    dans l'app (voir docs/reference/ARCHITECTURE.md § Villes & Géocodage)."""

    def test_extracts_distinct_locations_per_listing(self):
        result = KijijiListingParser._pick_all_standard_listings(NEXT_DATA_MULTI_CITY_SAMPLE)
        self.assertEqual(result["1732987805"]["location"]["name"], "Sainte-Julie")
        self.assertEqual(result["9999999999"]["location"]["name"], "Québec")

    def test_extracts_distinct_prices_per_listing(self):
        result = KijijiListingParser._pick_all_standard_listings(NEXT_DATA_MULTI_CITY_SAMPLE)
        self.assertEqual(result["1732987805"]["price"]["amount"], 10000)
        self.assertEqual(result["9999999999"]["price"]["amount"], 15000)


class TestParseDetailsPageViaNextData(unittest.TestCase):
    """Test de bout en bout basé sur la structure réelle observée en test live du
    2026-07-26 (annonce Kijiji 1740804650, Longueuil) — régression sur le bug où le
    lieu revenait `None` malgré un __NEXT_DATA__ complet."""

    def test_extracts_price_location_coordinates_from_next_data(self):
        page = FakeNextDataPage(
            url="https://www.kijiji.ca/v-guitar/longueuil-rive-sud/guitare-electrique/1740804650",
            next_data_json_text=json.dumps(NEXT_DATA_SAMPLE),
        )
        result = KijijiListingParser.parse_details_page(page, "Guitare electrique", "1740804650")

        self.assertEqual(result["price"], 220)
        self.assertTrue(result["price_found"])
        self.assertEqual(result["location"], "Longueuil / South Shore")
        self.assertEqual(result["latitude"], 45.58)
        self.assertEqual(result["longitude"], -73.32)
        self.assertEqual(len(result["imageUrls"]), 2)
        self.assertIn("Guitare fonctionne parfaitement", result["description"])


class TestParseDetailsPageMultipleCities(unittest.TestCase):
    """Même test de bout en bout que TestParseDetailsPageViaNextData, mais sur deux
    autres villes (Sainte-Julie, Québec) pour confirmer que le prix et le lieu ne sont
    pas juste corrects par coïncidence pour l'annonce de Longueuil testée en premier."""

    def test_sainte_julie_listing(self):
        next_data = {
            "props": {
                "pageProps": {
                    "listingId": "1732987805",
                    "__APOLLO_STATE__": {"StandardListing:1732987805": STANDARD_LISTING_SAINTE_JULIE},
                }
            }
        }
        page = FakeNextDataPage(
            url=STANDARD_LISTING_SAINTE_JULIE["url"],
            next_data_json_text=json.dumps(next_data),
        )
        result = KijijiListingParser.parse_details_page(page, "Pédale de guitare Marshall Bluesbreaker II", "1732987805")

        self.assertEqual(result["price"], 100)
        self.assertTrue(result["price_found"])
        self.assertEqual(result["location"], "Sainte-Julie")

    def test_quebec_city_listing(self):
        next_data = {
            "props": {
                "pageProps": {
                    "listingId": "9999999999",
                    "__APOLLO_STATE__": {"StandardListing:9999999999": STANDARD_LISTING_QUEBEC},
                }
            }
        }
        page = FakeNextDataPage(
            url=STANDARD_LISTING_QUEBEC["url"],
            next_data_json_text=json.dumps(next_data),
        )
        result = KijijiListingParser.parse_details_page(page, "Guitare classique Québec", "9999999999")

        self.assertEqual(result["price"], 150)
        self.assertTrue(result["price_found"])
        self.assertEqual(result["location"], "Québec")


if __name__ == "__main__":
    unittest.main()
