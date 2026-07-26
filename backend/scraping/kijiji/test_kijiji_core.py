import unittest

from scraping.kijiji.core import KijijiScraper
from scraping.kijiji.parser import KijijiListingParser


class FakePage:
    """Double minimal de playwright.sync_api.Page — seul `.url` est lu par _is_valid_detail_page."""
    def __init__(self, url):
        self.url = url


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


if __name__ == "__main__":
    unittest.main()
