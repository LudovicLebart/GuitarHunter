"""Tests de la base de connaissances « univers des guitares » (backend/guitar_knowledge.py) et de
son script d'import (backend/scripts/import_guitar_knowledge_wikidata.py) — sans Postgres ni réseau :
la connexion et les réponses Wikimedia sont simulées."""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("APP_ID_TARGET", "test")
os.environ.setdefault("USER_IDS_TARGET", "test_user")

from backend import guitar_knowledge as gk
from backend import llm_usage
from backend.scripts import import_guitar_knowledge_wikidata as imp


def _ent(description):
    return {"descriptions": {"en": {"value": description}}}


class _FakeConn:
    """Connexion minimale : `execute(...).fetchall()` renvoie les alias donnés, en comptant les appels."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def execute(self, *_args, **_kwargs):
        self.calls += 1
        result = MagicMock()
        result.fetchall.return_value = self.rows
        return result


class TestStripSuffix(unittest.TestCase):
    def test_suffix_only_removed_as_a_whole_word(self):
        self.assertEqual(imp.strip_suffix("Marco Guitars"), "Marco")
        self.assertEqual(imp.strip_suffix("Nico"), "Nico")
        self.assertEqual(imp.strip_suffix("Ricoh"), "Ricoh")
        self.assertEqual(imp.strip_suffix("Fender Musical Instruments Corporation"), "Fender")
        self.assertEqual(imp.strip_suffix("Gibson Brands, Inc."), "Gibson Brands")


class TestRelevance(unittest.TestCase):
    def test_accessory_makers_whose_description_mentions_guitar(self):
        for description in ("guitar string manufacturer", "guitar pedal maker", "guitar amplifier manufacturer"):
            self.assertEqual(imp.relevance_of(_ent(description), False), "accessories", description)

    def test_guitar_makers_stay_guitars(self):
        self.assertEqual(imp.relevance_of(_ent("American guitar manufacturer"), False), "guitars")
        self.assertEqual(imp.relevance_of(_ent("guitar and amplifier manufacturer"), False), "guitars")
        # ambigu (guitares ET micros) : on ne l'exclut pas, une fiche en moins vaut mieux qu'une fiche fausse
        self.assertEqual(imp.relevance_of(_ent("manufacturer of guitars and pickups"), False), "guitars")

    def test_pure_accessory_and_unknown(self):
        self.assertEqual(imp.relevance_of(_ent("tuning machine manufacturer"), False), "accessories")
        self.assertEqual(imp.relevance_of(_ent("watch company"), False), "unknown")
        self.assertEqual(imp.relevance_of(_ent("anything"), True), "guitars")


class TestDerivedAliases(unittest.TestCase):
    def test_generic_ambiguous_and_colliding_aliases_are_dropped(self):
        records = [
            {"aliases": ["Yamaha Eterna"], "_derived": ["Eterna"]},          # unique → gardé
            {"aliases": ["Fender Deluxe"], "_derived": ["Deluxe"]},          # mot générique → écarté
            {"aliases": ["Gibson Vega"], "_derived": ["Vega"]},              # produit deux fois → écarté
            {"aliases": ["Martin Vega"], "_derived": ["Vega"]},
            {"aliases": ["Ibanez Aria"], "_derived": ["Aria"]},              # = nom d'une autre fiche → écarté
            {"aliases": ["Aria"], "_derived": []},
        ]
        imp._merge_derived_aliases(records)
        self.assertIn("Eterna", records[0]["aliases"])
        self.assertNotIn("Deluxe", records[1]["aliases"])
        self.assertNotIn("Vega", records[2]["aliases"] + records[3]["aliases"])
        self.assertNotIn("Aria", records[4]["aliases"])
        self.assertTrue(all("_derived" not in r for r in records))


class TestWikiClientGet(unittest.TestCase):
    def _client(self, responses):
        client = imp.WikiClient(pause=0)
        client.session = MagicMock()
        client.session.get.side_effect = responses
        return client

    def _resp(self, status, headers=None, payload=None):
        resp = MagicMock()
        resp.status_code = status
        resp.headers = headers or {}
        resp.json.return_value = payload or {}
        resp.raise_for_status.side_effect = None if status < 400 else RuntimeError(f"HTTP {status}")
        return resp

    @patch("backend.scripts.import_guitar_knowledge_wikidata.time.sleep")
    def test_retry_after_as_http_date_does_not_abort(self, _sleep):
        client = self._client([
            self._resp(429, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
            self._resp(200, payload={"ok": 1}),
        ])
        self.assertEqual(client._get("https://x.org/api", {}), {"ok": 1})

    @patch("backend.scripts.import_guitar_knowledge_wikidata.time.sleep")
    def test_server_error_and_timeout_are_retried(self, _sleep):
        client = self._client([
            self._resp(500),
            imp.requests.Timeout("lent"),
            self._resp(200, payload={"ok": 2}),
        ])
        self.assertEqual(client._get("https://x.org/api", {}), {"ok": 2})

    @patch("backend.scripts.import_guitar_knowledge_wikidata.time.sleep")
    def test_optional_sparql_route_failure_does_not_abort_the_import(self, _sleep):
        client = self._client([self._resp(500)] * 4)
        self.assertEqual(imp.collect_from_products(client), set())


class TestAliasCache(unittest.TestCase):
    def setUp(self):
        gk.invalidate_cache()
        self.addCleanup(gk.invalidate_cache)

    def test_empty_alias_table_is_cached_until_ttl(self):
        conn = _FakeConn([])
        gk.find_ids(conn, "fender stratocaster")
        gk.find_ids(conn, "gibson les paul")
        self.assertEqual(conn.calls, 1)

    def test_fuzzy_match_is_memoized_and_filters_by_first_or_last_letter(self):
        conn = _FakeConn([{"alias_norm": "stratocaster", "knowledge_id": "wd:1"}])
        self.assertEqual(gk.find_ids(conn, "fendr stratocster")["wd:1"][1], "fuzzy")
        with patch("backend.guitar_knowledge.difflib.get_close_matches") as spy:
            gk.find_ids(conn, "stratocster")  # déjà vu → aucun nouveau calcul de ratio
            spy.assert_not_called()

    def test_generic_model_words_never_become_aliases(self):
        conn = _FakeConn([{"alias_norm": "deluxe", "knowledge_id": "wd:9"}])
        self.assertEqual(gk.find_ids(conn, "peavey deluxe amp"), {})


class TestModelUnavailableClassification(unittest.TestCase):
    def test_retired_model_is_classified_model_unavailable(self):
        self.assertEqual(
            llm_usage.classify_error(Exception("404 models/gemini-x is not found for API version v1beta")),
            "model_unavailable")
        self.assertEqual(llm_usage.classify_error(type("NotFoundError", (Exception,), {})("gone")),
                         "model_unavailable")

    def test_other_categories_take_precedence_over_not_found_wording(self):
        self.assertEqual(llm_usage.classify_error(Exception("Connection error: host not found")), "connection")
        self.assertEqual(llm_usage.classify_error(TimeoutError("timed out")), "timeout")


if __name__ == "__main__":
    unittest.main()
