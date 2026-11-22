"""Tests des sources Leaf sur du HTML INVENTÉ (dépôt public : aucune vraie annonce) + non-régression du
parseur Kijiji guitares (le paramètre `prefixes` ne doit rien changer par défaut)."""
import json
import unittest

from backend.leaf import dry_run
from backend.leaf.sources import BlockedError, autohebdo, kijiji_autos
from backend.scraping.kijiji.parser import KijijiListingParser


def _kijiji_html(entries):
    state = {f"AutosListing:{e['id']}": {"__typename": "AutosListing", **e} for e in entries}
    state["StandardListing:777"] = {"__typename": "StandardListing", "id": "777", "title": "Guitare inventée"}
    data = {"props": {"pageProps": {"__APOLLO_STATE__": state}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


def _autos_entry(**kw):
    e = {"id": "111", "title": "2016 Nissan Leaf SV", "description": "Texte inventé",
         "url": "https://exemple.invalid/leaf/111", "imageUrls": ["https://exemple.invalid/1.jpg"],
         "price": {"amount": 449500},
         "location": {"name": "Ville inventée", "address": "1 rue Fictive, Ville, QC",
                      "coordinates": {"latitude": 45.5, "longitude": -73.6}},
         "attributes": {"all": [
             {"canonicalName": "caryear", "canonicalValues": ["2016"]},
             {"canonicalName": "carmileageinkms", "canonicalValues": ["111439"]},
             {"canonicalName": "carmodel", "canonicalValues": ["leaf"]},
             {"canonicalName": "forsaleby", "canonicalValues": ["ownr"]}]}}
    e.update(kw)
    return e


class TestKijijiAutos(unittest.TestCase):
    def test_search_url(self):
        url = kijiji_autos.build_search_url(1, 1500, 7500)
        self.assertEqual(url, "https://www.kijiji.ca/b-autos-camions/quebec/nissan-leaf/k0c174l9001?price=1500__7500&sort=dateDesc")
        self.assertIn("/page-2/", kijiji_autos.build_search_url(2))

    def test_parse_converts_cents_and_attributes(self):
        listings = kijiji_autos.parse_search_page(_kijiji_html([_autos_entry()]))
        self.assertEqual(len(listings), 1)           # le StandardListing n'est pas lu
        a = listings[0]
        self.assertEqual((a["id"], a["price"], a["year"], a["km"]), ("leaf_kijiji_111", 4495, 2016, 111439))
        self.assertEqual((a["model"], a["seller_type"], a["latitude"]), ("leaf", "ownr", 45.5))

    def test_missing_next_data(self):
        self.assertEqual(kijiji_autos.parse_search_page("<html></html>"), [])
        self.assertEqual(kijiji_autos.parse_search_page(""), [])

    def test_missing_attributes_are_none_not_guessed(self):
        listings = kijiji_autos.parse_search_page(_kijiji_html([_autos_entry(attributes={"all": []}, price={})]))
        self.assertEqual((listings[0]["year"], listings[0]["km"], listings[0]["price"]), (None, None, None))


class TestGuitarParserNonRegression(unittest.TestCase):
    def test_default_prefix_still_reads_standard_listings_only(self):
        data = json.loads(_kijiji_html([_autos_entry()]).split('type="application/json">')[1].split("</script>")[0])
        picked = KijijiListingParser._pick_all_standard_listings(data)
        self.assertEqual(list(picked), ["777"])


def _autohebdo_html(items):
    ld = {"@context": "https://schema.org", "@graph": [{
        "@type": "SearchResultsPage",
        "mainEntity": {"@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "item": it} for i, it in enumerate(items)]}}]}
    return f'<script type="application/ld+json">{json.dumps(ld)}</script>'


class TestAutoHebdo(unittest.TestCase):
    ITEM = {"name": "Nissan Leaf SV", "url": "https://exemple.invalid/annonces/leaf-sv-"
            "0d6e8a0d-b48d-42b5-9f83-d6e3ff73c0e2", "offers": {"price": "5995"},
            "mileageFromOdometer": {"value": 110600}}

    def test_search_url(self):
        self.assertEqual(autohebdo.build_search_url(2017), "https://www.autohebdo.net/autos/nissan/leaf/my_2017/reg_qc")

    def test_parse_uses_page_year_and_uuid(self):
        out = autohebdo.parse_results_page(_autohebdo_html([self.ITEM]), page_year=2017)
        self.assertEqual(len(out), 1)
        a = out[0]
        self.assertEqual((a["price"], a["km"], a["year"]), (5995, 110600, 2017))
        self.assertEqual(a["id"], "leaf_autohebdo_0d6e8a0d-b48d-42b5-9f83-d6e3ff73c0e2")
        self.assertIsNone(a["latitude"])             # absent de la liste : jamais inventé

    def test_invalid_json_and_missing_url_are_skipped(self):
        self.assertEqual(autohebdo.parse_results_page('<script type="application/ld+json">{oups</script>'), [])
        self.assertEqual(autohebdo.parse_results_page(_autohebdo_html([{"name": "sans url"}])), [])

    def test_html_entities_in_name(self):
        out = autohebdo.parse_results_page(_autohebdo_html([{**self.ITEM, "name": "Leaf &amp; compagnie"}]), 2016)
        self.assertEqual(out[0]["title"], "Leaf & compagnie")


class TestCollect(unittest.TestCase):
    def test_collect_with_injected_fetch(self):
        pages = {}

        def fake_fetch(url):
            if "kijiji" in url:
                return _kijiji_html([_autos_entry()]) if "page-" not in url else _kijiji_html([])
            return _autohebdo_html([TestAutoHebdo.ITEM])

        raws = dry_run.collect((2016,), 1500, 7500, pages=3, fetch=fake_fetch)
        self.assertEqual(sorted(r["source"] for r in raws), ["autohebdo", "kijiji"])

    def test_blocked_site_stops_without_crashing(self):
        def blocked(url):
            raise BlockedError("HTTP 429")
        self.assertEqual(dry_run.collect((2016, 2017), 1500, 7500, pages=2, fetch=blocked), [])


if __name__ == "__main__":
    unittest.main()
