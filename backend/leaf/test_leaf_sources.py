"""Tests des sources Leaf sur du HTML INVENTÉ (dépôt public : aucune vraie annonce) + non-régression du
parseur Kijiji guitares (le paramètre `prefixes` ne doit rien changer par défaut)."""
import json
import unittest
from unittest import mock

from backend.leaf import dry_run, pipeline
from backend.leaf.sources import BlockedError, autohebdo, kijiji_autos
from backend.leaf.sources.detail import DetailFetcher, merge_detail


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
        try:
            from backend.scraping.kijiji.parser import KijijiListingParser
        except ImportError:
            self.skipTest("Playwright absent : le parseur Guitar Hunter n'est pas importable ici")
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


# ───────────────────────── Fiches (détail) ─────────────────────────
def _kijiji_detail_html(description, trim_values=("SV",)):
    entry = _autos_entry(description=description)
    entry["attributes"]["all"].append({"canonicalName": "cartrim", "canonicalValues": [], "values": list(trim_values)})
    return _kijiji_html([entry])


def _autohebdo_detail_html(description="", **vehicle):
    listing_details = {
        "description": description,
        "vehicle": {"modelYear": "2017", "mileageInKmRaw": 65000, "hadAccident": None,
                    "equipment": {"comfort": [{"id": "Sièges chauffants"}, {"id": "Régulateur de vitesse"}]},
                    "rawData": {"condition": {"damage": {"isCurrentlyDamaged": False}}}, **vehicle},
        "location": {"city": "VILLE FICTIVE", "latitude": 45.7, "longitude": -73.9},
        "seller": {"isDealer": True},
    }
    data = {"props": {"pageProps": {"listingDetails": listing_details}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'


class TestKijijiDetail(unittest.TestCase):
    def test_full_description_trim_and_location(self):
        d = kijiji_autos.parse_detail_page(_kijiji_detail_html("Texte complet.\nLeafSpy SOH 88 %"), "111")
        self.assertIn("SOH 88", d["description"])
        self.assertEqual((d["trim"], d["latitude"], d["seller_type"]), ("SV", 45.5, "ownr"))

    def test_trim_absent(self):
        html = _kijiji_html([_autos_entry()])
        self.assertIsNone(kijiji_autos.parse_detail_page(html, "111")["trim"])

    def test_unusable_page(self):
        self.assertIsNone(kijiji_autos.parse_detail_page("<html></html>"))
        self.assertIsNone(kijiji_autos.parse_detail_page(_kijiji_html([]), "999"))


class TestAutoHebdoDetail(unittest.TestCase):
    def test_description_cleaned_and_fields(self):
        html = _autohebdo_detail_html("<p>L&#x27;auto est jamais accidentée</p><br>Pneus d&#x27;hiver inclus")
        d = autohebdo.parse_detail_page(html)
        self.assertEqual(d["description"], "L'auto est jamais accidentée Pneus d'hiver inclus")
        self.assertEqual((d["city"], d["latitude"], d["seller_type"]), ("Ville Fictive", 45.7, "delr"))
        self.assertEqual((d["year"], d["km"]), (2017, 65000))
        self.assertEqual(d["equipment"], ["Sièges chauffants", "Régulateur de vitesse"])
        self.assertFalse(d["currently_damaged"])
        self.assertIsNone(d["had_accident"])               # absent = inconnu, jamais « non »

    def test_unusable_page(self):
        self.assertIsNone(autohebdo.parse_detail_page("<html></html>"))
        self.assertIsNone(autohebdo.parse_detail_page('<script id="__NEXT_DATA__">{oups</script>'))


class TestDetailPhotos(unittest.TestCase):
    """La fiche donne plus de photos que la liste (Kijiji : ≈ 10 contre 5) ; une image de remplacement n'est pas une photo."""
    def test_kijiji_detail_returns_all_photos_of_the_page(self):
        photos = [f"https://exemple.invalid/p{i}.jpg" for i in range(10)]
        html = _kijiji_html([_autos_entry(imageUrls=photos)])
        self.assertEqual(kijiji_autos.parse_detail_page(html, "111")["image_urls"], photos)

    def test_autohebdo_detail_photos_and_placeholder(self):
        def page(**extra):
            details = json.loads(_autohebdo_detail_html("t").split('json">')[1].split("</script>")[0])
            details["props"]["pageProps"]["listingDetails"].update(extra)
            return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(details)}</script>'
        urls = ["https://exemple.invalid/a.jpg/1280x960.webp", "https://exemple.invalid/b.jpg/1280x960.webp"]
        self.assertEqual(autohebdo.parse_detail_page(page(images=urls, isCoverImagePlaceholder=False))["image_urls"], urls)
        self.assertEqual(autohebdo.parse_detail_page(page(images=urls, isCoverImagePlaceholder=True))["image_urls"], [])
        self.assertEqual(autohebdo.parse_detail_page(page(images=["http://non-https.invalid/x.jpg", 3]))["image_urls"], [])

    def test_merge_takes_the_longer_photo_list_and_never_shrinks(self):
        raw = {"source": "kijiji", "image_urls": ["a", "b"]}
        self.assertEqual(merge_detail(raw, {"image_urls": ["a", "b", "c"]})["image_urls"], ["a", "b", "c"])
        self.assertEqual(merge_detail(raw, {"image_urls": ["z"]})["image_urls"], ["a", "b"])
        self.assertEqual(merge_detail(raw, {})["image_urls"], ["a", "b"])


class TestFacebookSource(unittest.TestCase):
    """`deal_to_raw` est pur ; `collect_facebook` est testé avec un faux scraper (aucun navigateur, aucun réseau)."""
    DEAL = {"id": "9001", "title": "Nissan Leaf 2017 SV", "price": 5500.0, "description": "Annonce Marketplace. 98 000 km, SOH 90 %",
            "imageUrl": "https://exemple.invalide/a.jpg", "imageUrls": ["https://exemple.invalide/a.jpg", "http://non-https.invalide/b.jpg"],
            "location": "Ville-Test, QC", "latitude": 45.5, "longitude": -73.3}

    def test_deal_to_raw_maps_to_the_common_format(self):
        from backend.leaf.sources import facebook
        raw = facebook.deal_to_raw(self.DEAL)
        self.assertEqual((raw["id"], raw["source"], raw["source_id"], raw["price"]), ("leaf_facebook_9001", "facebook", "9001", 5500))
        self.assertEqual((raw["title"], raw["city"], raw["latitude"], raw["image_urls"]),
                         ("Nissan Leaf 2017 SV", "Ville-Test, QC", 45.5, ["https://exemple.invalide/a.jpg"]))
        self.assertEqual(raw["url"], "https://www.facebook.com/marketplace/item/9001/")
        self.assertTrue(all(raw[k] is None for k in ("year", "km", "trim", "vin")))       # rien de deviné : lu plus tard dans le texte

    def test_deal_without_id_or_price_is_handled(self):
        from backend.leaf.sources import facebook
        self.assertIsNone(facebook.deal_to_raw({"title": "x"}))
        self.assertIsNone(facebook.deal_to_raw({**self.DEAL, "price": None})["price"])
        self.assertEqual(facebook.deal_to_raw({**self.DEAL, "imageUrls": []})["image_urls"], ["https://exemple.invalide/a.jpg"])

    def test_raw_feeds_the_pipeline_with_year_km_and_soh_read_from_the_text(self):
        from backend.leaf.sources import facebook
        result = pipeline.evaluate_listings([facebook.deal_to_raw(self.DEAL)], {"max_price": 7500})
        kept = result["kept"][0]
        self.assertEqual((kept["year"], kept["km"], kept["trim"], kept["soh_announced"]), (2017, 98000, "SV", 90.0))

    def _scan(self, scraper):
        from backend.leaf.sources import facebook
        closed = []
        scraper.close_session = lambda: closed.append(1)
        scan = {"min_price": 1500, "max_price": 7500, "facebook_city": {"id": "123", "name": "Ville-Test"}}
        raws, run = facebook.collect_facebook(scan, scraper_factory=lambda *a: scraper)
        return raws, run, closed

    def test_collect_ok_then_closes_the_session(self):
        class Fake:
            def scan_marketplace(self, cfg, skip, **kw):
                self.cfg = cfg
                return {"deals": [FakeDeal], "total_cards_seen": 4, "rejected_out_of_list": 0, "dropped_no_location": 0,
                        "anti_bot_blocked": False, "error": None}
        FakeDeal = self.DEAL
        raws, run, closed = self._scan(Fake())
        self.assertEqual((len(raws), run["outcome"], run["cards_seen"]), (1, "ok", 4))
        self.assertEqual(closed, [1])

    def test_collect_reports_block_and_never_raises(self):
        class Blocked:
            def scan_marketplace(self, cfg, skip, **kw):
                return {"deals": [], "total_cards_seen": 0, "anti_bot_blocked": True, "error": None}

        class Boom:
            def scan_marketplace(self, cfg, skip, **kw):
                raise RuntimeError("navigateur indisponible")
        raws, run, closed = self._scan(Blocked())
        self.assertEqual((raws, run["outcome"], closed), ([], "blocked", [1]))
        raws, run, closed = self._scan(Boom())
        self.assertEqual((raws, run["outcome"], closed), ([], "error", [1]))
        self.assertIn("navigateur indisponible", run["detail"])

    def test_facebook_deal_is_not_reread_nor_flagged_unreadable_and_keeps_listing_without_year(self):
        from backend.leaf.sources import facebook
        calls = []
        deal = {**self.DEAL, "title": "Nissan Leaf SV", "description": "Annonce Marketplace. Très propre."}
        result = pipeline.evaluate_listings([facebook.deal_to_raw(deal)], {"max_price": 7500},
                                            detail_fetcher=lambda raw: calls.append(1) or None)
        self.assertEqual(calls, [])                                       # la fiche a déjà été lue par le scraper Facebook
        kept = result["kept"][0]
        self.assertNotIn("detail_unavailable", kept["flags"])
        self.assertIn("year_unknown", kept["flags"])                       # gardée, pas écartée en silence
        self.assertIn("year_unknown", kept["risk_flags"])

    def test_year_is_still_required_for_sources_with_structured_year(self):
        result = pipeline.evaluate_listings([{"id": "x", "title": "Nissan Leaf", "price": 5000, "model": "leaf", "km": 1000}], {})
        self.assertEqual(result["ignored"][0]["ignored_reason"], "year")

    def test_scraper_gets_city_coordinates_skip_callback_and_stop_event(self):
        from backend.leaf.sources import facebook
        seen = {}

        class Fake:
            def scan_marketplace(self, cfg, skip, **kw):
                seen.update(skip=skip, stop=kw.get("stop_event"))
                return {"deals": [], "total_cards_seen": 1, "anti_bot_blocked": False, "error": None}

            def close_session(self):
                pass
        factory_args = []
        scan = {"min_price": 1, "max_price": 2, "facebook_city": {"id": "1", "name": "Ville-Test", "latitude": 45.5, "longitude": -73.3}}
        skip, stop = (lambda i, p: True), object()
        facebook.collect_facebook(scan, scraper_factory=lambda *a: factory_args.append(a) or Fake(), should_skip=skip, stop_event=stop)
        self.assertEqual(factory_args[0][3], {"latitude": 45.5, "longitude": -73.3})
        self.assertIs(seen["skip"], skip)
        self.assertIs(seen["stop"], stop)

    def test_busy_browsers_skip_facebook_without_losing_other_sources(self):
        import threading
        from backend.leaf import hunter
        guard = threading.Semaphore(1)
        guard.acquire()                                                    # tous les navigateurs sont pris
        with mock.patch.object(hunter, "BROWSER_WAIT_S", 0.05):
            raws, runs = hunter.collect_sources({"sources": ["facebook"], "years": [], "pages": 1, "min_price": 1, "max_price": 2},
                                                browser_guard=guard)
        self.assertEqual((raws, runs[0]["source"], runs[0]["outcome"]), ([], "facebook", "skipped"))
        self.assertIn("occupés", runs[0]["detail"])

    def test_no_facebook_city_means_nothing_is_launched(self):
        from backend.leaf.sources import facebook
        called = []
        raws, run = facebook.collect_facebook({"min_price": 0, "max_price": 1, "facebook_city": None},
                                              scraper_factory=lambda *a: called.append(1))
        self.assertEqual((raws, run["outcome"], called), ([], "skipped", []))


class TestDuplicatesWithoutKm(unittest.TestCase):
    """Annonces Facebook : pas de kilométrage structuré, donc la règle « même km » ne s'applique pas. Règle dédiée, plus stricte."""
    BASE = {"title": "Nissan Leaf SV 2017", "price": 6950, "year": 2017, "trim": "SV", "km": None, "latitude": 45.66, "longitude": -73.93, "city": "Mirabel, QC"}

    def same(self, **b):
        from backend.leaf import dedup
        return dedup.same_vehicle(self.BASE, {**self.BASE, **b})

    def test_identical_ads_from_one_dealer_are_probable_duplicates(self):
        self.assertTrue(self.same())
        self.assertTrue(self.same(title="  nissan LEAF sv, 2017 !! ", price=6960))              # casse, ponctuation, prix à 1 %

    def test_any_difference_that_could_mean_another_car_breaks_the_match(self):
        self.assertFalse(self.same(price=6500))                                                  # autre prix
        self.assertFalse(self.same(title="Nissan Leaf S 2017"))                                  # autre titre
        self.assertFalse(self.same(year=2016))
        self.assertFalse(self.same(latitude=45.8, longitude=-73.9))                              # plus de 1 km
        self.assertFalse(self.same(price=None))
        self.assertFalse(self.same(title=""))

    def test_without_gps_the_city_decides(self):
        no_gps = {"latitude": None, "longitude": None}
        self.assertTrue(self.same(**no_gps, city="mirabel qc"))
        self.assertFalse(self.same(**no_gps, city="Laval, QC"))
        self.assertFalse(self.same(**no_gps, city=""))

    def test_a_listing_with_a_km_never_matches_one_without(self):
        self.assertFalse(self.same(km=90000))                                                    # un seul km connu : on ne confirme pas
        from backend.leaf import dedup
        self.assertTrue(dedup.same_vehicle({**self.BASE, "km": 90000}, {**self.BASE, "km": 90500}))   # règle avec km inchangée
        self.assertTrue(dedup.same_vehicle({**self.BASE, "vin": "abc"}, {**self.BASE, "vin": "ABC", "price": 1}))   # le VIN prime


class TestMergeAndFetcher(unittest.TestCase):
    RAW = {"source": "kijiji", "source_id": "111", "url": "https://exemple.invalid/leaf/111",
           "description": "Texte tronqué ...", "trim": None, "city": "", "year": 2016, "km": 100000}

    def test_merge_prefers_longest_description_and_fills_blanks(self):
        merged = merge_detail(self.RAW, {"description": "Texte tronqué et la suite complète", "trim": "SL",
                                         "city": "Ville", "km": 1, "equipment": ["x"], "had_accident": True})
        self.assertEqual(merged["description"], "Texte tronqué et la suite complète")
        self.assertEqual((merged["trim"], merged["city"], merged["km"]), ("SL", "Ville", 100000))   # km déjà connu
        self.assertTrue(merged["had_accident"] and merged["detail_fetched"])
        self.assertIsNone(self.RAW["trim"])                                                          # entrée intacte

    def test_merge_keeps_longer_list_description(self):
        merged = merge_detail({**self.RAW, "description": "Longue description de la liste"}, {"description": "court"})
        self.assertEqual(merged["description"], "Longue description de la liste")

    def test_fetcher_parses_by_source(self):
        f = DetailFetcher(fetch=lambda url: _kijiji_detail_html("Description complète"))
        self.assertEqual(f(self.RAW)["description"], "Description complète")
        self.assertEqual((f.fetched, f.failed), (1, 0))

    def test_fetcher_unknown_source_or_no_url_makes_no_request(self):
        calls = []
        f = DetailFetcher(fetch=lambda url: calls.append(url) or "")
        self.assertIsNone(f({**self.RAW, "source": "autre"}))
        self.assertIsNone(f({**self.RAW, "url": None}))
        self.assertEqual(calls, [])

    def test_fetcher_failure_is_counted_not_raised(self):
        f = DetailFetcher(fetch=lambda url: "<html></html>")
        self.assertIsNone(f(self.RAW))
        self.assertEqual(f.failed, 1)

        def boom(url):
            raise RuntimeError("réseau")
        g = DetailFetcher(fetch=boom)
        self.assertIsNone(g(self.RAW))
        self.assertEqual(g.failed, 1)

    def test_fetcher_stops_after_block(self):
        calls = []

        def blocked(url):
            calls.append(url)
            raise BlockedError("HTTP 429")
        f = DetailFetcher(fetch=blocked)
        self.assertIsNone(f(self.RAW))
        self.assertIsNone(f(self.RAW))
        self.assertTrue(f.blocked)
        self.assertEqual(len(calls), 1)                     # aucune insistance après le blocage

    def test_fetcher_uses_given_logger(self):
        import logging
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)
        logger = logging.getLogger("bot.testuser.leaf")
        logger.addHandler(Capture())

        def blocked(url):
            raise BlockedError("HTTP 403")
        DetailFetcher(fetch=blocked, logger=logger)(self.RAW)
        self.assertTrue(any("[Leaf]" in r.getMessage() for r in records))


class TestPipelineWithDetail(unittest.TestCase):
    BASE = {"id": "a", "source": "kijiji", "source_id": "1", "url": "u", "title": "2016 Nissan Leaf SV", "price": 4000,
            "year": 2016, "km": 100000, "model": "leaf", "description": "court ..."}

    def test_rejection_visible_only_on_detail(self):
        sans = pipeline.evaluate_listings([self.BASE])
        self.assertEqual(len(sans["kept"]), 1)             # liste seule : rien ne trahit la batterie
        avec = pipeline.evaluate_listings([self.BASE], detail_fetcher=lambda raw: {"description": "LeafSpy SOH 62,5 %"})
        self.assertEqual(len(avec["rejected"]), 1)
        self.assertIn("soh_below_80", avec["rejected"][0]["reject_reasons"])

    def test_filters_rerun_on_enriched_data(self):
        out = pipeline.evaluate_listings([{**self.BASE, "km": None}],
                                         detail_fetcher=lambda raw: {"km": 190000, "description": "x" * 20})
        self.assertEqual(out["ignored"][0]["ignored_reason"], "km")

    def test_distance_applied_after_detail_gives_gps(self):
        raw = {**self.BASE, "source": "autohebdo"}                           # la liste AutoHebdo n'a pas de GPS
        home = {"latitude": 45.5, "longitude": -73.6, "max_km": 100}
        far = pipeline.evaluate_listings([raw], home=home, detail_fetcher=lambda r: {"latitude": 48.4, "longitude": -71.1})
        self.assertEqual(far["ignored"][0]["ignored_reason"], "distance")
        near = pipeline.evaluate_listings([raw], home=home, detail_fetcher=lambda r: {"latitude": 45.6, "longitude": -73.7})
        self.assertEqual(len(near["kept"]), 1)

    def test_unreadable_detail_keeps_listing_with_flag(self):
        out = pipeline.evaluate_listings([self.BASE], detail_fetcher=lambda raw: None)
        self.assertEqual(len(out["kept"]), 1)
        self.assertIn("detail_unavailable", out["kept"][0]["flags"])

    def test_detail_fetched_only_for_listings_passing_list_filters(self):
        calls = []
        raws = [self.BASE, {**self.BASE, "id": "b", "year": 2012}, {**self.BASE, "id": "c", "price": 99999}]
        pipeline.evaluate_listings(raws, detail_fetcher=lambda raw: calls.append(raw["id"]) or None)
        self.assertEqual(calls, ["a"])                     # une seule requête de fiche : les autres sont hors périmètre

    def test_structured_damage_rejects(self):
        out = pipeline.evaluate_listings([self.BASE], detail_fetcher=lambda raw: {"had_accident": True})
        self.assertIn("accident:declared_accident", out["rejected"][0]["reject_reasons"])

    def test_equipment_list_feeds_mentions(self):
        out = pipeline.evaluate_listings([self.BASE], detail_fetcher=lambda raw: {"equipment": ["Sièges chauffants"]})
        self.assertTrue(out["kept"][0]["mentions"]["heated_seats"])


if __name__ == "__main__":
    unittest.main()
