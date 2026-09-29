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


def _typed(description_by_lang, p31=None, label=None):
    ent = {"descriptions": {lang: {"value": v} for lang, v in description_by_lang.items()}, "claims": {}}
    if label:
        ent["labels"] = {"en": {"value": label}}
    if p31:
        ent["claims"]["P31"] = [{"mainsnak": {"datavalue": {"value": {"id": q}}}} for q in p31]
    return ent


class TestRealPreviewCases(unittest.TestCase):
    """Cas constatés sur le premier `--dry-run` réel (2026-09-29) : fabricants de la catégorie classés
    `accessories` à tort, articles « liste » et modèles importés comme entreprises."""

    def test_accessory_verdict_uses_the_primary_description(self):
        # Framus : « firme allemande » en fr, une autre langue parlait d'accessoires — pas un accessoire.
        framus = _typed({"fr": "firme allemande", "de": "Hersteller von Effektgeräten und amplifier"}, label="Framus")
        self.assertNotEqual(imp.relevance_of(framus, False, from_category=True), "accessories")

    def test_real_accessory_makers_of_the_category_stay_accessories(self):
        for label, description in (("EMG, Inc.", "guitar pickups and EQ accessories manufacturer"),
                                   ("Fishman", "guitar pickups, preamps manufacturer"),
                                   ("Maxon Effects", "effect pedals company"),
                                   ("Dean Markley USA", "company that manufactures musical instrument "
                                                        "related products, primarily guitar strings"),
                                   ("Pignose", "portable guitar amp manufacturer")):
            ent = _typed({"en": description}, ["Q4830453"], label=label)
            self.assertEqual(imp.relevance_of(ent, False, from_category=True), "accessories", label)

    def test_maker_named_guitars_from_the_category_is_not_an_accessory(self):
        robin = _typed({"en": "brand of guitar pickups"}, ["Q4830453"], label="Robin Guitars")
        self.assertEqual(imp.relevance_of(robin, False, from_category=True), "unknown")
        self.assertEqual(imp.relevance_of(robin, False, from_category=False), "accessories")

    def test_amplifier_model_from_category_stays_accessory_and_is_a_model(self):
        princeton = _typed({"en": "guitar amplifier produced by Fender introduced in 1947"}, ["Q1339359"])
        self.assertTrue(imp.is_model(princeton))
        self.assertEqual(imp.relevance_of(princeton, False, from_category=True, model=True), "accessories")

    def test_guitar_model_becomes_a_line(self):
        g400 = _typed({"en": "solid body electric guitar model"}, ["Q29982117"])
        self.assertTrue(imp.is_model(g400))
        self.assertEqual(imp.relevance_of(g400, False, from_category=True, model=True), "guitars")

    def test_models_seen_in_the_real_preview(self):
        """Descriptions et types réels du dry-run du 2026-09-29 (Gibson/Danelectro/Ibanez...)."""
        cases = [
            ({"en": "Semi-hollow body electric guitar"}, ["Q29982117"]),       # ES-135
            ({"en": "hollow-body electric guitar"}, ["Q6607"]),                # ES-5
            ({"en": "archtop guitar by Gibson"}, ["Q29982117"]),               # L-5
            ({"en": "dual-pickup hollow bodied guitar"}, []),                  # Danelectro U2
            ({"en": "electric guitar model"}, []),                             # ES-137
            ({"en": "the signature bass for KoRn's bassist Fieldy"}, ["Q64166304"]),  # Ibanez K5
            ({"en": "guitar made by the Gibson Guitar Corporation"}, ["Q78987"]),     # S-1
            ({}, ["Q29982117"]),                                               # GL-1 : type seul
        ]
        for descriptions, types in cases:
            self.assertTrue(imp.is_model(_typed(descriptions, types)), (descriptions, types))

    def test_makers_are_not_models_even_without_wikidata_type(self):
        self.assertFalse(imp.is_model(_typed({"en": "German guitar builder"}, [])))
        self.assertFalse(imp.is_model(_typed({"fr": "entreprise américaine de matériel audio"}, ["Q4830453"])))  # Line 6
        self.assertFalse(imp.is_model(_typed({"en": "manufacturer of effects units"}, ["Q431289"])))           # Supro

    def test_organisations_are_never_models(self):
        company = _typed({"en": "series of guitars, model range"}, ["Q4830453"])
        self.assertFalse(imp.is_model(company))
        self.assertFalse(imp.is_model(_typed({"fr": "firme allemande"})))  # aucun type

    def test_list_pages_are_skipped(self):
        for title in ("list of guitar manufacturers", "list of Yamaha guitars", "Liste des marques de guitares",
                      "list of electric guitar brands"):
            self.assertTrue(imp.is_list_page(_typed({}), title), title)
        self.assertTrue(imp.is_list_page(_typed({}, ["Q13406463"]), "Guitar makers"))
        self.assertFalse(imp.is_list_page(_typed({}), "Listen Guitars"))
        self.assertFalse(imp.is_list_page(_typed({}), "Yamaha"))


class TestBuildRecordsOnRealPreviewCases(unittest.TestCase):
    """`build_records` de bout en bout (Wikimedia simulé) sur les cas du premier dry-run réel."""

    def _entity(self, label, description, p31, claims=None, sitelinks=None):
        ent = _typed({"en": description}, p31)
        ent["labels"] = {"en": {"value": label}}
        ent["claims"].update(claims or {})
        return ent

    def test_wiring(self):
        maker_claim = [{"mainsnak": {"datavalue": {"value": {"id": "Q10"}}}}]
        entities = {
            "Q10": self._entity("Epiphone", "American guitar manufacturer", ["Q4830453"]),
            "Q11": self._entity("Framus", "firme allemande", ["Q167270"]),
            "Q12": self._entity("list of guitar manufacturers", "Wikimedia list article", ["Q13406463"]),
            "Q13": self._entity("Epiphone G-400", "solid body electric guitar model", ["Q29982117"],
                                claims={"P176": maker_claim}),
            "Q14": self._entity("Fender Princeton", "guitar amplifier produced by Fender introduced in 1947",
                                ["Q1339359"]),
        }
        origin = {q: {"category:en"} for q in entities}
        client = MagicMock()
        client.entities.side_effect = lambda qids, props=None: {q: entities[q] for q in qids if q in entities}
        with patch.object(imp, "collect_from_categories", return_value=origin), \
                patch.object(imp, "collect_from_products", return_value=set()):
            records = {r["name"]: r for r in imp.build_records(client, ["en"], 1, with_lines=False)}

        self.assertNotIn("list of guitar manufacturers", records)
        self.assertIn(records["Framus"]["relevance"], ("unknown", "guitars"))  # jamais « accessories »
        self.assertEqual((records["Epiphone G-400"]["kind"], records["Epiphone G-400"]["relevance"]),
                         ("line", "guitars"))
        self.assertEqual(records["Epiphone G-400"]["parent_id"], "wd:Q10")
        self.assertEqual((records["Fender Princeton"]["kind"], records["Fender Princeton"]["relevance"]),
                         ("line", "accessories"))
        self.assertEqual(records["Epiphone"]["kind"], "company")
        self.assertIn("G-400", records["Epiphone G-400"]["aliases"])  # alias dérivé unique, ≥ 4 caractères


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

    def test_very_short_model_numbers_are_not_kept(self):
        records = [{"aliases": ["Gibson S-1"], "_derived": ["S-1"]}]  # « s 1 » = 3 caractères : bruit
        imp._merge_derived_aliases(records)
        self.assertNotIn("S-1", records[0]["aliases"])


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
