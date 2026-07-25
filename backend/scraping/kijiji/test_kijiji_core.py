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


if __name__ == "__main__":
    unittest.main()
