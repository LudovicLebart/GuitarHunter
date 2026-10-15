"""Tri automatique des fiches par règles : catégories, raisons, approbation sans toucher les décisions humaines."""
import os
import unittest
from collections import Counter

from backend.scripts import knowledge_triage as kt


def fiche(fid, name, **kw):
    f = {"id": fid, "name": name, "kind": "brand", "description": "Fabricant canadien de guitares électriques.",
         "countries": ["CA"], "active_from": 1970, "active_to": None, "relevance": "guitars", "aliases": [name],
         "parent_name": None, "parent_id": None, "from_maker_category": True, "source": "wikidata",
         "hard": [], "flags": [], "trusted": False, "state": None}
    f.update(kw)
    return f


def run(*fs):
    by_id = {f["id"]: f for f in fs}
    owners = kt.alias_owners(list(fs))
    return {f["id"]: kt.triage(f, by_id, owners) for f in fs}


class TestTriage(unittest.TestCase):
    def test_clean_import_from_the_makers_category_is_safe(self):
        self.assertEqual(run(fiche("a", "Marquea"))["a"], (kt.SAFE, []))

    def test_each_doubt_is_reported_with_its_reason(self):
        cases = {
            "hors catégorie": fiche("a", "Marquea", from_maker_category=False),
            "pertinence unknown": fiche("a", "Marquea", relevance="unknown"),
            "pays absent": fiche("a", "Marquea", countries=[]),
            "luthier non curé": fiche("a", "Marquea", kind="luthier"),
            "série sans marque mère": fiche("a", "Marquea", kind="line"),
            "non importée": fiche("a", "Marquea", source="forum"),
        }
        for needle, f in cases.items():
            cat, reasons = run(f)["a"]
            self.assertEqual(cat, kt.CHECK, needle)
            self.assertTrue(any(needle.split()[0] in r for r in reasons), (needle, reasons))

    def test_a_series_with_its_parent_does_not_need_the_makers_category_nor_a_country(self):
        parent = fiche("p", "Fendera")
        line = fiche("l", "Stratoa", kind="line", parent_id="p", from_maker_category=False, countries=[])
        self.assertEqual(run(parent, line)["l"], (kt.SAFE, []))

    def test_hard_failures_trusted_decided_and_accessories_are_set_apart(self):
        r = run(fiche("h", "Hard", hard=["année de début incohérente (1750)"]), fiche("t", "Trust", trusted=True),
                fiche("d", "Decide", state="rejected"), fiche("x", "Accessoire", relevance="accessories"))
        self.assertEqual([r[k][0] for k in "htdx"], [kt.FALSE, kt.DONE, kt.DONE, kt.OFFTOPIC])
        self.assertIn("année de début incohérente (1750)", r["h"][1])

    def test_an_alias_shared_with_an_unrelated_fiche_is_a_homonym_risk(self):
        a, b = fiche("a", "Marquea", aliases=["Marquea", "Eclipse"]), fiche("b", "Marqueb", aliases=["Marqueb", "Eclipse"])
        r = run(a, b)
        self.assertEqual(r["a"][0], kt.CHECK)
        self.assertIn("eclipse", r["a"][1][0])

    def test_aliases_shared_inside_one_family_are_fine(self):
        company = fiche("c", "Fender Musical Instruments Corporation", aliases=["Fender", "FMIC"], kind="company")
        brand = fiche("b", "Fender", parent_id="c")
        sibling = fiche("s", "Squier", parent_id="c", aliases=["Squier", "Fender Squier"])
        r = run(company, brand, sibling)
        self.assertEqual([r[k][0] for k in "cbs"], [kt.SAFE] * 3)

    def test_sparse_is_a_flag_not_a_category(self):
        f = fiche("a", "Marquea", flags=["fiche creuse"])
        self.assertEqual(run(f)["a"][0], kt.SAFE)
        rows = [(f, kt.SAFE, [])]
        s = kt.summarize(rows, Counter({"a": 3}))
        self.assertEqual((s["sparse"], s["sparse_found"], s["found"][kt.SAFE]), (1, 1, 1))


@unittest.skipUnless(os.getenv("KB_TEST_DATABASE_URL"), "définir KB_TEST_DATABASE_URL (base Postgres JETABLE)")
class TestPostgres(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        from backend import guitar_knowledge as gk
        from backend.test_guitar_knowledge import use_latest_kb
        self.gk = gk
        self.conn = psycopg.connect(os.environ["KB_TEST_DATABASE_URL"], autocommit=True, row_factory=dict_row)
        self.addCleanup(self.conn.close)
        with open(os.path.join(os.path.dirname(__file__), "api", "schema.sql"), encoding="utf-8") as fh:
            self.conn.execute(fh.read())
        self.conn.execute("TRUNCATE guitar_knowledge, guitar_knowledge_alias, guitar_knowledge_versions, guitar_deals CASCADE")
        use_latest_kb(self)
        for fid, name, origin, countries, desc in (
                ("wd:a", "Marquea", "category:en", "{CA}", "Fabricant canadien de guitares électriques, actif depuis 1970."),
                ("wd:b", "Marqueb", "list:en", "{CA}", "Fabricant canadien de guitares électriques, actif depuis 1970."),
                ("wd:c", "Marquec", "category:en", "{US}", "guitares")):
            self.conn.execute(
                """INSERT INTO guitar_knowledge (id, kind, name, description, countries, relevance, source, kb_version, raw)
                   VALUES (%s,'brand',%s,%s,%s,'guitars','wikidata',1,%s)""",
                (fid, name, desc, countries, '{"origin":["%s"]}' % origin))
            self.conn.execute("INSERT INTO guitar_knowledge_alias VALUES (%s,%s,%s,'wikidata')", (name.lower(), fid, name))
        self.conn.execute("INSERT INTO guitar_knowledge_source (knowledge_id, url, kind, title) VALUES "
                          "('wd:b','https://www.wikidata.org/wiki/Q2','wikidata','Q2')")
        self.conn.execute("INSERT INTO guitar_deals (id, title, description) VALUES ('d1','Marqueb très secret','texte privé')")
        self.gk.invalidate_cache()

    def _status(self, fid):
        return self.conn.execute("SELECT review_status, review_note, reviewed_digest FROM guitar_knowledge WHERE id=%s",
                                 (fid,)).fetchone()

    def test_categories_apply_and_human_decisions_survive(self):
        rows = kt.run_triage(self.conn)
        cats = {f["id"]: c for f, c, _ in rows}
        self.assertEqual(cats, {"wd:a": kt.SAFE, "wd:b": kt.CHECK, "wd:c": kt.SAFE})
        self.conn.execute("UPDATE guitar_knowledge SET review_status='rejected', review_note='homonyme' WHERE id='wd:c'")
        rows = kt.run_triage(self.conn)
        self.assertEqual(kt.apply_safe(self.conn, rows, dry_run=True, log=lambda *_: None), ["wd:a"])
        self.assertIsNone(self._status("wd:a")["review_status"])
        kt.apply_safe(self.conn, rows, log=lambda *_: None)
        self.assertEqual(self._status("wd:a")["review_status"], "approved")
        self.assertIn("sans IA", self._status("wd:a")["review_note"])
        self.assertTrue(self._status("wd:a")["reviewed_digest"])
        self.assertEqual(self._status("wd:c"), {"review_status": "rejected", "review_note": "homonyme", "reviewed_digest": None})

    def test_the_gate_serves_what_was_approved_and_a_changed_fiche_loses_its_approval(self):
        kt.apply_safe(self.conn, kt.run_triage(self.conn), log=lambda *_: None)
        self.gk.invalidate_cache()
        self.gk.configure_review_gate(True)
        self.assertEqual(sorted(f["id"] for f in self.gk.lookup(self.conn, "marquea marqueb marquec")), ["wd:a", "wd:c"])
        self.conn.execute("UPDATE guitar_knowledge SET description = 'Autre texte sur des guitares.' WHERE id='wd:a'")
        self.assertEqual([f["id"] for f in self.gk.lookup(self.conn, "marquea")], [])

    def test_export_has_facts_and_sources_but_no_listing_text(self):
        import json
        rows = kt.run_triage(self.conn)
        from backend.scripts import knowledge_gate_report as rep
        hits, _ = rep.hit_counts(self.conn)
        data = kt.export_rows(self.conn, rows, hits)
        self.assertEqual([x["id"] for x in data], ["wd:b"])                 # a et c : saines et non creuses -> hors export
        self.assertEqual(data[0]["sources"][0]["url"], "https://www.wikidata.org/wiki/Q2")
        blob = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("texte privé", blob)
        self.assertNotIn("très secret", blob)


if __name__ == "__main__":
    unittest.main()
