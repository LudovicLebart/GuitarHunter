"""Tests de `backend/pricing.py`."""
import unittest

from backend.pricing import normalize_price


class TestNormalizePrice(unittest.TestCase):
    def test_strips_currency_and_spaces(self):
        self.assertEqual(normalize_price(" 150 $ "), 150.0)

    def test_comma_decimal(self):
        self.assertEqual(normalize_price("12,5"), 12.5)

    def test_empty_or_invalid_is_zero(self):
        self.assertEqual(normalize_price(None), 0.0)
        self.assertEqual(normalize_price("Gratuit"), 0.0)
        self.assertEqual(normalize_price("1.2.3"), 0.0)


if __name__ == "__main__":
    unittest.main()
