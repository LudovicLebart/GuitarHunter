"""Tests purs de `backend/scraping/scroll.py`."""
import unittest

from backend.scraping.scroll import ScrollProgress


class TestScrollProgress(unittest.TestCase):
    def test_target_reached(self):
        p = ScrollProgress(30)
        self.assertIsNone(p.observe(20))
        self.assertEqual(p.observe(30), ScrollProgress.TARGET)

    def test_stagnant_after_two_steps_without_growth(self):
        p = ScrollProgress(100)
        self.assertIsNone(p.observe(20))
        self.assertIsNone(p.observe(20))
        self.assertEqual(p.observe(20), ScrollProgress.STAGNANT)

    def test_growth_resets_the_stagnation_counter(self):
        p = ScrollProgress(100)
        p.observe(20)
        self.assertIsNone(p.observe(20))
        self.assertIsNone(p.observe(25))
        self.assertIsNone(p.observe(25))
        self.assertEqual(p.observe(25), ScrollProgress.STAGNANT)

    def test_initial_reading_is_not_a_stagnation(self):
        p = ScrollProgress(100)
        self.assertIsNone(p.observe(0, scrolled=False))
        self.assertIsNone(p.observe(0))
        self.assertEqual(p.observe(0), ScrollProgress.STAGNANT)

    def test_target_wins_over_stagnation(self):
        p = ScrollProgress(20)
        self.assertEqual(p.observe(20, scrolled=False), ScrollProgress.TARGET)


if __name__ == "__main__":
    unittest.main()
