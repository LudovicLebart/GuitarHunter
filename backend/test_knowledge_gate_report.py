"""Rapport de la porte de qualité + feuille de relecture + application des décisions (2026-10-14)."""
import os
import unittest
from collections import Counter
from unittest import mock

from backend import guitar_knowledge as gk
from backend.scripts import knowledge_gate_report as rep
from backend.scripts import knowledge_review_apply as apply_
from backend.test_guitar_knowledge import use_latest_kb


def _f(fid, name, **kw):
    base = {"id": fid, "name": name, "kind": "brand", "description": "Fabricant de guitares.", "countries": ["US"],
            "active_from": 1950, "active_to": None, "relevance": "guitars", "n_sources": 1, "aliases": [name],
            "parent_name": None, "hard": [], "flags": [], "trusted": False, "state": None, "served": False,
            "source": "wikidata"}
    base.update(kw)
    return base


class TestSheetParsing(unittest.TestCase):
    SHEET = """en-tête libre

#1  wd:a  |  Marquea  (brand)
   description : x
DECISION: A
#2  wd:b  |  Marqueb  (line)
DECISION: R années fausses, c'est 1957
#3  wd:c  |  Marquec  (brand)
DECISION: ?
#4  wd:d  |  Marqued  (brand)
decision: a
"""

    def test_reads_approvals_rejections_and_notes_and_skips_unknown(self):
        self.assertEqual(apply_.parse_sheet(self.SHEET), [
            ("wd:a", "approved", None), ("wd:b", "rejected", "années fausses, c'est 1957"),
            ("wd:d", "approved", None)])

    def test_decision_without_fiche_is_an_error(self):
        with self.assertRaises(ValueError):
            apply_.parse_sheet("DECISION: A\n")

    def test_second_decision_for_same_fiche_is_an_error(self):
        txt = "#1  wd:a  |  X  (brand)\nDECISION: A\n#2  wd:a  |  X  (brand)\nDECISION: R\n"
        with self.assertRaises(ValueError):
            apply_.parse_sheet(txt)

    def test_two_decisions_under_one_header_do_not_count_twice(self):
        txt = "#1  wd:a  |  X  (brand)\nDECISION: A\nDECISION: R\n"
        with self.assertRaises(ValueError):
            apply_.parse_sheet(txt)


class TestSheetBuilding(unittest.TestCase):
    def test_only_unreviewed_imports_found_in_listings_are_proposed_most_found_first(self):
        fiches = [
            _f("wd:a", "Alpha"), _f("wd:b", "Bravo"), _f("wd:c", "Charlie"),
            _f("wd:t", "Trusted", trusted=True), _f("wd:r", "Revue", state="approved"),
            _f("wd:x", "Accessoire", relevance="accessories"), _f("wd:n", "Jamais trouvée"),
        ]
        hits = Counter({"wd:a": 2, "wd:b": 9, "wd:c": 5, "wd:t": 50, "wd:r": 50, "wd:x": 50})
        text, pool = rep.build_sheet(fiches, hits, top=2)
        self.assertEqual(pool, 3)
        self.assertEqual([i for i in ("wd:b", "wd:c", "wd:a") if f"  {i}  |" in text], ["wd:b", "wd:c"])
        for excluded in ("wd:t", "wd:r", "wd:x", "wd:n"):
            self.assertNotIn(f"  {excluded}  |", text)

    def test_block_carries_what_is_needed_to_judge_and_round_trips_through_the_parser(self):
        f = _f("wd:a", "Alpha", flags=["source unique"], parent_name="Maison", active_from=1960, active_to=1975)
        block = rep.sheet_block(7, f, 12)
        for needle in ("#7  wd:a  |  Alpha  (brand)", "12 annonce(s)", "1960–1975", "Maison", "source unique", "DECISION: ?"):
            self.assertIn(needle, block)
        self.assertEqual(apply_.parse_sheet(block), [])
        self.assertEqual(apply_.parse_sheet(block.replace("DECISION: ?", "DECISION: A ok")), [("wd:a", "approved", "ok")])

    def test_header_of_the_sheet_never_parses_as_a_decision(self):
        self.assertEqual(apply_.parse_sheet(rep.SHEET_HEAD.format(n=3)), [])

    def test_summary_counts(self):
        fiches = [_f("1", "A", served=True, trusted=True), _f("2", "B", hard=["années incohérentes (1750)"]),
                  _f("3", "C"), _f("4", "D", state="rejected", hard=["fiche rejetée à la relecture"])]
        s = rep.summarize(fiches)
        self.assertEqual((s["total"], s["served"], s["hard"], s["to_review"], s["trusted"]), (4, 1, 2, 1, 1))
        self.assertEqual(s["hard_reasons"]["années incohérentes"], 1)


@unittest.skipUnless(os.getenv("KB_TEST_DATABASE_URL"),
                     "définir KB_TEST_DATABASE_URL (base Postgres JETABLE) pour tester le rapport et l'application")
class TestReportAndApplyPostgres(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        self.conn = psycopg.connect(os.environ["KB_TEST_DATABASE_URL"], autocommit=True, row_factory=dict_row)
        self.addCleanup(self.conn.close)
        with open(os.path.join(os.path.dirname(__file__), "api", "schema.sql"), encoding="utf-8") as fh:
            self.conn.execute(fh.read())
        self.conn.execute("TRUNCATE guitar_knowledge, guitar_knowledge_alias, guitar_knowledge_versions CASCADE")
        use_latest_kb(self)
        gk.configure_review_gate(True)

    def _fiche(self, fid, name, desc="Fabricant américain de guitares électriques et de basses, actif depuis les années 1950.",
               **cols):
        self.conn.execute(
            """INSERT INTO guitar_knowledge (id, kind, name, description, active_from, active_to, relevance, source,
                                             kb_version, raw, curated)
               VALUES (%s,'brand',%s,%s,%s,%s,'guitars','wikidata',1,'{"origin":["category:en"]}',%s)""",
            (fid, name, desc, cols.get("active_from"), cols.get("active_to"), cols.get("curated", False)))
        self.conn.execute("INSERT INTO guitar_knowledge_alias VALUES (%s,%s,%s,'wikidata')", (gk.normalize(name), fid, name))
        gk.invalidate_cache()

    def _state(self, fid):
        return self.conn.execute("SELECT review_status, review_note, reviewed_digest FROM guitar_knowledge WHERE id = %s",
                                 (fid,)).fetchone()

    def test_report_classifies_served_hard_and_to_review(self):
        self._fiche("wd:ok", "Correcta", curated=True)
        self._fiche("wd:bad", "Anciennea", curated=True, active_from=1750)
        self._fiche("wd:new", "Nouvellea")
        fiches, by_id = rep.fetch_fiches(self.conn)
        s = rep.summarize(fiches)
        self.assertEqual((s["total"], s["served"], s["hard"], s["to_review"]), (3, 1, 1, 1))
        self.assertTrue(by_id["wd:ok"]["served"])
        self.assertFalse(by_id["wd:bad"]["served"])

    def test_apply_stores_decision_and_digest_then_gate_serves_it(self):
        self._fiche("wd:a", "Marquea")
        self._fiche("wd:b", "Marqueb")
        self.assertEqual([f["id"] for f in gk.lookup(self.conn, "marquea marqueb")], [])
        for kid, status, note in [("wd:a", "approved", None), ("wd:b", "rejected", "homonyme")]:
            self.conn.execute(apply_.UPDATE_SQL, (status, note, kid))
        gk.invalidate_cache()
        self.assertEqual([f["id"] for f in gk.lookup(self.conn, "marquea marqueb")], ["wd:a"])
        self.assertEqual(self._state("wd:b")["review_note"], "homonyme")
        # Un réimport qui change la fiche périme l'approbation.
        self.conn.execute("UPDATE guitar_knowledge SET description = 'Texte différent de guitares.' WHERE id = 'wd:a'")
        self.assertEqual([f["id"] for f in gk.lookup(self.conn, "marquea")], [])

    def test_applied_fiche_leaves_the_review_sheet(self):
        self._fiche("wd:a", "Marquea")
        self._fiche("wd:b", "Marqueb")
        self.conn.execute(apply_.UPDATE_SQL, ("approved", None, "wd:a"))
        fiches, _ = rep.fetch_fiches(self.conn)
        text, pool = rep.build_sheet(fiches, Counter({"wd:a": 3, "wd:b": 2}), top=10)
        self.assertEqual(pool, 1)
        self.assertIn("wd:b", text)
        self.assertNotIn("  wd:a  |", text)

    def test_main_dry_run_writes_nothing_and_unknown_id_aborts(self):
        import tempfile
        self._fiche("wd:a", "Marquea")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write("#1  wd:a  |  Marquea  (brand)\nDECISION: A\n")
            ok = fh.name
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write("#1  wd:inconnue  |  X  (brand)\nDECISION: A\n")
            bad = fh.name
        self.addCleanup(os.remove, ok)
        self.addCleanup(os.remove, bad)
        with mock.patch.dict(os.environ, {"DATABASE_URL": os.environ["KB_TEST_DATABASE_URL"]}):
            apply_.main([ok, "--dry-run"])
            self.assertIsNone(self._state("wd:a")["review_status"])
            with self.assertRaises(SystemExit):
                apply_.main([bad])
            apply_.main([ok])
        self.assertEqual(self._state("wd:a")["review_status"], "approved")
        self.assertTrue(self._state("wd:a")["reviewed_digest"])


if __name__ == "__main__":
    unittest.main()
