"""Boucle défilement/traitement de `FacebookScraper.scan_marketplace()` avec un faux navigateur :
arrêt « scan rattrapé », plafond `max_ads`, fin de liste, tri perdu, arrêt manuel, liste raccourcie."""
import unittest
from unittest import mock

from scraping import core
from scraping.config import ScraperConfig
from scraping.core import FacebookScraper

BATCH = 20
SORTED_URL = "https://www.facebook.com/marketplace/1/search/?sortBy=creation_time_descend"


class FakeLink:
    def __init__(self, fb_id):
        self.fb_id = fb_id

    def get_attribute(self, name):
        return f"/marketplace/item/{self.fb_id}/"


class FakeLocator:
    def __init__(self, links):
        self.links = links

    def all(self):
        return list(self.links)


def growing(total):
    """Instantanés successifs de la liste : BATCH cartes de plus à chaque défilement, jusqu'à `total`."""
    return [list(range(1, min(total, n) + 1)) for n in range(BATCH, total + BATCH, BATCH)]


class FakePage:
    """`snapshots[k]` = ids des cartes présentes après k défilements (le dernier instantané se répète)."""
    def __init__(self, snapshots, url=SORTED_URL):
        self.snapshots = snapshots
        self.wheels = 0
        self.url = url
        self.mouse = mock.Mock(wheel=self._wheel)

    def _wheel(self, dx, dy):
        self.wheels += 1

    def goto(self, *a, **k): pass
    def evaluate(self, *a, **k): pass
    def close(self): pass
    def get_by_role(self, *a, **k): return mock.Mock()

    def locator(self, selector):
        ids = self.snapshots[min(self.wheels, len(self.snapshots) - 1)]
        return FakeLocator([FakeLink(i) for i in ids])


def make_scraper(known_run):
    scraper = FacebookScraper({}, {"montreal": "1"}, config=ScraperConfig(catchup_known_run=known_run))
    scraper._ensure_session = lambda: None
    scraper._close_login_popup = lambda p: None
    scraper._apply_filters = lambda *a: None
    scraper._is_valid_detail_page = lambda *a: False   # repli sur la carte : pas de fiche à parser
    scraper.is_city_allowed = lambda loc: True
    return scraper


def run_scan(snapshots, known_ids, known_run, max_ads=50, url=SORTED_URL, allow_catchup=True, stop_event=None):
    page = FakePage(snapshots, url)
    scraper = make_scraper(known_run)
    # new_page() sert d'abord la page de recherche, puis des fiches détail (pages vides)
    pages = iter([page])
    scraper.context = mock.Mock(new_page=lambda: next(pages, FakePage([[]])))
    card = lambda link, location, logger=None: {"title": f"t{link.fb_id}", "price": 100, "imageUrl": "", "location": "Montréal, QC"}
    scan_config = {"search_query": "guitar", "location": "montreal", "min_price": 0, "max_price": 500, "max_ads": max_ads}
    skip = lambda fb_id, price: int(fb_id) in known_ids
    with mock.patch.object(core.ListingParser, "parse_listing_card", side_effect=card), \
         mock.patch.object(core.time, "sleep"):
        result = scraper.scan_marketplace(scan_config, skip, stop_event=stop_event, allow_catchup=allow_catchup)
    return result, page


class TestScanLoop(unittest.TestCase):
    def test_stops_when_caught_up_without_scrolling(self):
        # Cartes 1-5 nouvelles, 6+ déjà connues : 3 connues d'affilée -> arrêt, sans défiler.
        result, page = run_scan(growing(60), set(range(6, 61)), known_run=3)
        self.assertEqual(len(result["deals"]), 5)
        self.assertTrue(result["stopped_caught_up"])
        self.assertEqual(result["skipped_known"], 3)
        self.assertEqual(page.wheels, 0)
        self.assertEqual(result["total_cards_seen"], BATCH)

    def test_new_card_after_known_ones_breaks_the_run(self):
        # 6-8 connues, 9 nouvelle, 10+ connues : la série repart de zéro à la carte 9.
        known = set(range(6, 9)) | set(range(10, 61))
        result, _ = run_scan(growing(60), known, known_run=4)
        self.assertEqual(len(result["deals"]), 6)   # 1-5 et 9
        self.assertTrue(result["stopped_caught_up"])
        self.assertEqual(result["skipped_known"], 3 + 4)

    def test_disabled_scrolls_to_end_of_list(self):
        result, page = run_scan(growing(60), set(range(6, 61)), known_run=0)
        self.assertFalse(result["stopped_caught_up"])
        self.assertEqual(result["total_cards_seen"], 60)
        self.assertEqual(result["skipped_known"], 55)
        self.assertEqual(len(result["deals"]), 5)

    def test_max_ads_caps_new_ads_and_scrolling_stops_with_it(self):
        result, page = run_scan(growing(60), set(), known_run=10, max_ads=7)
        self.assertEqual(len(result["deals"]), 7)
        self.assertEqual(page.wheels, 0)   # 7 annonces nouvelles tiennent dans les 20 premières cartes

    def test_no_catchup_stop_when_date_sort_is_lost(self):
        # Tri retombé sur la pertinence : des cartes connues en tête ne disent rien de la suite.
        url = "https://www.facebook.com/marketplace/1/search/?query=guitar"
        result, _ = run_scan(growing(60), set(range(6, 61)), known_run=3, url=url)
        self.assertFalse(result["stopped_caught_up"])
        self.assertEqual(result["skipped_known"], 55)

    def test_allow_catchup_false_forces_a_full_pass(self):
        result, _ = run_scan(growing(60), set(range(6, 61)), known_run=3, allow_catchup=False)
        self.assertFalse(result["stopped_caught_up"])
        self.assertEqual(result["total_cards_seen"], 60)

    def test_end_of_list_stops_scrolling_with_catchup_on(self):
        # 30 cartes, toutes nouvelles : 1 défilement charge tout, 2 de plus ne changent rien.
        result, page = run_scan(growing(30), set(), known_run=3)
        self.assertEqual(len(result["deals"]), 30)
        self.assertFalse(result["stopped_caught_up"])
        self.assertEqual(page.wheels, 3)

    def test_stop_during_scroll_returns_an_empty_result(self):
        # Appels à is_set : début du scan, carte 1, puis le défilement (qui annule le scan).
        stop = mock.Mock(is_set=mock.Mock(side_effect=[False, False, True]))
        result, _ = run_scan([[1]], set(), known_run=0, stop_event=stop)
        self.assertEqual(result["deals"], [])
        self.assertEqual(result["total_cards_seen"], 0)

    def test_shortened_list_is_reread_from_the_start(self):
        # Après un défilement, la liste n'a plus que 2 cartes (nœuds retirés) : 5 et 6, jamais vues.
        result, _ = run_scan([[1, 2, 3, 4], [5, 6]], set(), known_run=0)
        self.assertEqual(sorted(d["id"] for d in result["deals"]), ["1", "2", "3", "4", "5", "6"])


if __name__ == "__main__":
    unittest.main()
