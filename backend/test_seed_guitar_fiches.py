"""Tests du chargeur des fiches techniques (backend/scripts/seed_guitar_fiches.py). Validation sans base ; le chargement
réel tourne contre un Postgres JETABLE (`KB_TEST_DATABASE_URL`), comme les autres tests de la base de connaissances."""
import os
import tempfile
import unittest

os.environ.setdefault("APP_ID_TARGET", "test")
os.environ.setdefault("USER_IDS_TARGET", "test_user")

from backend import guitar_knowledge as gk
from backend.scripts import seed_guitar_fiches as sf

HEADER = """---
slug: demo
titre: Fiche de démonstration
categorie: reglage            # commentaire toléré
difficulte: 2
duree: 30 min
statut: brouillon
revision: 2026-10-15
alias: truss rod coincé, action haute
{extra}---

# Fiche de démonstration

> Résumé court de la fiche.

## Étapes

Voir [l'autre fiche](autre.md) pour la suite.

## Sources et liens

{sources}
"""
TWO_SOURCES = ("- [StewMac : Neck relief](https://stewmac.com/a) : mesure du relief\n"
               "- [Premier Guitar : Neck relief](https://www.premierguitar.com/b) : réglage par petits pas\n")


def make(text, name="demo.md"):
    path = os.path.join(tempfile.mkdtemp(), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return sf.load_fiche(path)


def doc(sources=TWO_SOURCES, extra=""):
    return HEADER.format(sources=sources, extra=extra)


class TestParsing(unittest.TestCase):
    def test_front_matter_with_comments_and_lists(self):
        f = make(doc(extra="concerne: Gibson, Les Paul   # facultatif\n"))
        self.assertEqual(f["meta"]["categorie"], "reglage")
        self.assertEqual(f["meta"]["alias"], ["truss rod coincé", "action haute"])
        self.assertEqual(f["meta"]["concerne"], ["Gibson", "Les Paul"])
        self.assertEqual(f["summary"], "Résumé court de la fiche.")

    def test_sources_are_parsed_with_publisher_title_and_kind(self):
        f = make(doc())
        self.assertEqual([s["publisher"] for s in f["sources"]], ["StewMac", "Premier Guitar"])
        self.assertEqual(f["sources"][1]["kind"], "press")
        self.assertTrue(f["sources"][0]["excerpt"].startswith("[résumé] mesure"))
        self.assertEqual(gk.confidence_of(f["sources"]), "sourced")

    def test_a_missing_header_is_refused(self):
        with self.assertRaises(sf.SeedError):
            sf.split_front_matter("# pas d'en-tête\n")


class TestValidation(unittest.TestCase):
    def check(self, text, name="demo.md", known=("demo", "autre")):
        return sf.validate_fiche(make(text, name), set(known))

    def test_a_good_fiche_is_valid(self):
        self.assertEqual(self.check(doc()), [])

    def test_a_fiche_without_source_is_refused(self):
        self.assertTrue(any("AUCUNE source" in p for p in self.check(doc(sources="Aucune pour l'instant.\n"))))

    def test_a_single_publisher_is_valid_but_single_source(self):
        f = make(doc(sources="- [StewMac : A](https://stewmac.com/a) : x\n- [StewMac : B](https://stewmac.com/b) : y\n"))
        self.assertEqual(sf.validate_fiche(f, {"demo", "autre"}), [])
        self.assertEqual(gk.confidence_of(f["sources"]), "single_source")

    def test_unknown_values_and_slug_mismatch(self):
        problems = self.check(doc().replace("categorie: reglage", "categorie: magie").replace("statut: brouillon", "statut: fini"))
        self.assertTrue(any("categorie" in p for p in problems))
        self.assertTrue(any("statut" in p for p in problems))
        self.assertTrue(any("différent du nom du fichier" in p for p in self.check(doc(), name="autre-nom.md")))

    def test_a_broken_cross_reference_is_refused(self):
        self.assertTrue(any("autre.md" in p for p in self.check(doc(), known=("demo",))))

    def test_generic_alias_is_refused_but_precise_expressions_pass(self):
        problems = self.check(doc().replace("alias: truss rod coincé, action haute", "alias: action"))
        self.assertTrue(any("« action »" in p for p in problems))
        self.assertTrue(gk.fiche_alias_usable("action haute"))
        self.assertFalse(gk.fiche_alias_usable("manche"))
        self.assertFalse(gk.fiche_alias_usable("guitare"))


class TestShippedFiches(unittest.TestCase):
    def test_every_shipped_fiche_is_valid_and_sourced(self):
        paths = sf.list_paths()
        self.assertTrue(paths)
        slugs = {os.path.splitext(os.path.basename(p))[0] for p in paths}
        for path in paths:
            f = sf.load_fiche(path)
            self.assertEqual(sf.validate_fiche(f, slugs), [], path)
            self.assertEqual(gk.confidence_of(f["sources"]), "sourced", path)   # ≥ 2 éditeurs distincts


@unittest.skipUnless(os.getenv("KB_TEST_DATABASE_URL"),
                     "définir KB_TEST_DATABASE_URL (base Postgres JETABLE) pour tester le chargement des fiches")
class TestLoadIntoPostgres(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        self.conn = psycopg.connect(os.environ["KB_TEST_DATABASE_URL"], autocommit=True, row_factory=dict_row)
        self.addCleanup(self.conn.close)
        with open(os.path.join(os.path.dirname(__file__), "api", "schema.sql"), encoding="utf-8") as fh:
            self.conn.execute(fh.read())
        self.conn.execute("TRUNCATE guitar_knowledge, guitar_knowledge_alias, guitar_knowledge_versions, "
                          "guitar_knowledge_source, guitar_knowledge_fiche, guitar_knowledge_link CASCADE")
        self.addCleanup(gk.configure_version, "validated")
        self.addCleanup(gk.invalidate_cache)
        gk.configure_version("latest")
        gk.invalidate_cache()
        self.conn.execute("INSERT INTO guitar_knowledge_versions (version, source, validated) VALUES (1,'t',true)")
        self.conn.execute("""INSERT INTO guitar_knowledge (id, kind, name, relevance, source, kb_version, curated)
                             VALUES ('manual:gibson','brand','Gibson','guitars','manual',1,true)""")
        self.conn.execute("INSERT INTO guitar_knowledge_alias VALUES ('gibson','manual:gibson','Gibson','manual')")
        self.dir = tempfile.mkdtemp()

    def _fiche(self, text, name="demo.md"):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def _load(self, *paths, force=False):
        planned = sf.plan(self.conn, list(paths), known_slugs={"demo", "autre"}, force=force)
        return planned, sf.write(self.conn, planned)

    def test_write_creates_rows_without_creating_a_version(self):
        path = self._fiche(doc(extra="concerne: Gibson\n"))
        planned, written = self._load(path)
        self.assertEqual(written, 1)
        row = self.conn.execute("SELECT * FROM guitar_knowledge WHERE id = 'fiche:demo'").fetchone()
        self.assertEqual((row["kind"], row["kb_version"], row["confidence"], row["source"]), ("fiche", 0, "sourced", "manual"))
        fiche = self.conn.execute("SELECT * FROM guitar_knowledge_fiche WHERE knowledge_id = 'fiche:demo'").fetchone()
        self.assertEqual((fiche["categorie"], fiche["statut"], fiche["difficulte"]), ("reglage", "brouillon", 2))
        self.assertIn("Résumé court", fiche["body_md"])
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge_source WHERE knowledge_id = 'fiche:demo'"
                                           ).fetchone()["n"], 2)
        link = self.conn.execute("SELECT * FROM guitar_knowledge_link").fetchone()
        self.assertEqual((link["from_id"], link["to_id"], link["rel"], link["origin"]), ("manual:gibson", "fiche:demo", "fiche_pour", "fiche"))
        # AUCUNE version créée : la version validée reste la 1
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge_versions").fetchone()["n"], 1)

    def test_loaded_fiche_is_found_by_its_aliases_and_never_by_the_portier(self):
        self._load(self._fiche(doc()))
        gk.invalidate_cache()
        found = gk.find_ids(self.conn, "Gibson avec truss rod coincé", kinds=gk.FICHE_KINDS)
        self.assertEqual(set(found), {"fiche:demo"})
        self.assertEqual(set(gk.find_ids(self.conn, "Gibson avec truss rod coincé")), {"manual:gibson"})

    def test_unchanged_fiche_is_skipped_and_force_rewrites(self):
        path = self._fiche(doc())
        self._load(path)
        planned, written = self._load(path)
        self.assertEqual((written, planned[0]["unchanged"]), (0, True))
        self.assertEqual(self._load(path, force=True)[1], 1)

    def test_removed_source_and_alias_disappear_on_reload(self):
        path = self._fiche(doc())
        self._load(path)
        self._fiche(doc(sources=TWO_SOURCES.splitlines()[0] + "\n").replace("alias: truss rod coincé, action haute", "alias: action haute"))
        self._load(path)
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge_source WHERE knowledge_id = 'fiche:demo'"
                                           ).fetchone()["n"], 1)
        norms = {r["alias_norm"] for r in self.conn.execute("SELECT alias_norm FROM guitar_knowledge_alias WHERE knowledge_id = 'fiche:demo'")}
        self.assertNotIn("truss rod coince", norms)
        self.assertIn("action haute", norms)

    def test_manual_aliases_and_sources_are_never_touched(self):
        path = self._fiche(doc())
        self._load(path)
        self.conn.execute("INSERT INTO guitar_knowledge_alias VALUES ('mon alias','fiche:demo','mon alias','manual')")
        self.conn.execute("""INSERT INTO guitar_knowledge_source (knowledge_id, url, kind, publisher, excerpt, origin)
                             VALUES ('fiche:demo','https://exemple.com/x','other','Moi','note','manual')""")
        self._load(path, force=True)
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge_alias WHERE source = 'manual' AND knowledge_id = 'fiche:demo'"
                                           ).fetchone()["n"], 1)
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge_source WHERE origin = 'manual' AND knowledge_id = 'fiche:demo'"
                                           ).fetchone()["n"], 1)

    def test_unknown_brand_in_concerne_is_refused(self):
        path = self._fiche(doc(extra="concerne: Marque Inconnue\n"))
        with self.assertRaises(sf.SeedError):
            sf.plan(self.conn, [path], known_slugs={"demo", "autre"})

    def test_orphans_and_prune(self):
        path = self._fiche(doc())
        planned, _ = self._load(path)
        self.assertEqual(sf.orphans(self.conn, planned), [])
        self.assertEqual(sf.orphans(self.conn, []), ["fiche:demo"])
        sf.prune(self.conn, ["fiche:demo", "manual:gibson"])      # une marque n'est jamais supprimée par --prune
        self.assertIsNone(self.conn.execute("SELECT 1 AS x FROM guitar_knowledge WHERE id = 'fiche:demo'").fetchone())
        self.assertIsNotNone(self.conn.execute("SELECT 1 AS x FROM guitar_knowledge WHERE id = 'manual:gibson'").fetchone())


if __name__ == "__main__":
    unittest.main()
