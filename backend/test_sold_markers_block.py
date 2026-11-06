"""Tests de `is_block_page_url` (revue R-3-2) : une page de blocage n'est pas une suppression."""
import unittest

from backend.sold_markers import is_block_page_url


class BlockPageUrlTest(unittest.TestCase):
    def test_pages_de_blocage(self):
        for url in (
            "https://www.facebook.com/login/?next=%2Fmarketplace%2Fitem%2F1",
            "https://www.facebook.com/checkpoint/1501092823525282/",
            "https://www.kijiji.ca/captcha?x=1",
            "https://www.google.com/recaptcha/api2/anchor",
        ):
            self.assertTrue(is_block_page_url(url), url)

    def test_fiches_et_accueil(self):
        for url in (
            "https://www.facebook.com/marketplace/item/123456/",
            "https://www.facebook.com/marketplace/",
            "https://www.kijiji.ca/v-guitare/montreal/fender/1234567",
            "", None,
        ):
            self.assertFalse(is_block_page_url(url), url)


if __name__ == "__main__":
    unittest.main()
