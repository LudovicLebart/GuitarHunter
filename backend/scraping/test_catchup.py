"""Tests purs de `backend/scraping/catchup.py`."""
import unittest

from backend.scraping.catchup import CatchUpTracker, catchup_allowed


class TestCatchUpTracker(unittest.TestCase):
    def test_stops_after_k_known_in_a_row(self):
        t = CatchUpTracker(3)
        self.assertFalse(t.known())
        self.assertFalse(t.known())
        self.assertTrue(t.known())

    def test_new_card_breaks_the_run(self):
        t = CatchUpTracker(3)
        t.known()
        t.known()
        t.unknown()
        self.assertFalse(t.known())
        self.assertFalse(t.known())
        self.assertTrue(t.known())

    def test_disabled_when_zero(self):
        t = CatchUpTracker(0)
        for _ in range(50):
            self.assertFalse(t.known())

    def test_not_done_before_any_card(self):
        self.assertFalse(CatchUpTracker(1).done)


class TestCatchupAllowed(unittest.TestCase):
    def test_first_scan_of_a_search_is_a_full_pass(self):
        self.assertFalse(catchup_allowed(0, 6))

    def test_following_scans_may_catch_up(self):
        for done in (1, 2, 5):
            self.assertTrue(catchup_allowed(done, 6))

    def test_every_nth_scan_is_a_full_pass(self):
        self.assertFalse(catchup_allowed(6, 6))
        self.assertTrue(catchup_allowed(7, 6))
        self.assertFalse(catchup_allowed(12, 6))

    def test_no_periodic_pass_when_disabled(self):
        self.assertTrue(catchup_allowed(6, 0))


if __name__ == "__main__":
    unittest.main()
