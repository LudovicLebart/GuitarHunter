import unittest
from scraping.core import FacebookScraper


class FakePage:
    """Double minimal de playwright.sync_api.Page — seul `.url` est lu par _is_valid_detail_page."""
    def __init__(self, url):
        self.url = url


class TestIsValidDetailPage(unittest.TestCase):
    def setUp(self):
        self.scraper = FacebookScraper(city_coordinates={}, city_mapping={})

    def test_valid_detail_page(self):
        page = FakePage("https://www.facebook.com/marketplace/item/123456789/")
        self.assertTrue(self.scraper._is_valid_detail_page(page, "123456789"))

    def test_redirect_to_feed_is_invalid(self):
        page = FakePage("https://www.facebook.com/marketplace/")
        self.assertFalse(self.scraper._is_valid_detail_page(page, "123456789"))

    def test_redirect_to_login_is_invalid(self):
        page = FakePage("https://www.facebook.com/login/?next=%2Fmarketplace%2F")
        self.assertFalse(self.scraper._is_valid_detail_page(page, "123456789"))

    def test_mismatched_item_id_is_invalid(self):
        page = FakePage("https://www.facebook.com/marketplace/item/000000000/")
        self.assertFalse(self.scraper._is_valid_detail_page(page, "123456789"))


if __name__ == "__main__":
    unittest.main()
