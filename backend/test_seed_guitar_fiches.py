"""Tests du chargeur des fiches techniques (backend/scripts/seed_guitar_fiches.py). Validation sans base ; le chargement
réel tourne contre un Postgres JETABLE (`KB_TEST_DATABASE_URL`), comme les autres tests de la base de connaissances."""
import os
import tempfile
import unittest
from unittest.mock import patch

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

    def test_source_url_with_balanced_parentheses_is_kept(self):
        f = make(doc(sources="- [Wikipédia : Les Paul](https://fr.wikipedia.org/wiki/Les_Paul_(guitare)) : modèle\n"
                             "- [StewMac : A](https://stewmac.com/a) : x\n"))
        self.assertEqual(f["sources"][0]["url"], "https://fr.wikipedia.org/wiki/Les_Paul_(guitare)")
        self.assertEqual(len(f["sources"]), 2)

    def test_an_unreadable_source_bullet_is_reported_not_ignored(self):
        f = make(doc(sources=TWO_SOURCES + "- https://exemple.com/sans-lien-markdown\n"))
        problems = sf.validate_fiche(f, {"demo", "autre"})
        self.assertTrue(any("puce de source illisible" in p for p in problems))
        only_bad = make(doc(sources="- pas une source\n"))
        self.assertFalse(any("AUCUNE source" in p for p in sf.validate_fiche(only_bad, {"demo", "autre"})))

    def test_sources_section_variants_are_found(self):
        for heading in ("## Sources et liens utiles", "### Sources et liens"):
            f = make(doc().replace("## Sources et liens", heading))
            self.assertEqual(len(f["sources"]), 2, heading)

    def test_missing_section_and_empty_section_have_different_messages(self):
        no_section = make(doc().replace("## Sources et liens", "## Autre"))
        self.assertTrue(any("introuvable" in p for p in sf.validate_fiche(no_section, {"demo", "autre"})))
        empty = make(doc(sources="Aucune pour l'instant.\n"))
        self.assertTrue(any("la section existe" in p for p in sf.validate_fiche(empty, {"demo", "autre"})))

    def test_a_hash_followed_by_a_digit_is_not_a_comment(self):
        f = make(doc().replace("titre: Fiche de démonstration", "titre: Réglage #1 du manche   # vrai commentaire"))
        self.assertEqual(f["meta"]["titre"], "Réglage #1 du manche")

    def test_only_a_whole_line_of_three_dashes_closes_the_header(self):
        with self.assertRaises(sf.SeedError):
            sf.split_front_matter("---\nslug: demo\n----\ntitre: T\n---\ncorps\n")
        meta, body = sf.split_front_matter("---\nslug: demo\n---\ncorps\n")
        self.assertEqual((meta["slug"], body), ("demo", "corps\n"))

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

    def test_difficulte_and_duree_are_required(self):
        problems = self.check(doc().replace("difficulte: 2\n", "").replace("duree: 30 min\n", ""))
        self.assertTrue(any("« difficulte » manquant" in p for p in problems))
        self.assertTrue(any("« duree » manquant" in p for p in problems))

    def test_a_fiche_with_no_usable_alias_at_all_is_refused(self):
        problems = self.check(doc().replace("titre: Fiche de démonstration", "titre: Réglage").replace(
            "alias: truss rod coincé, action haute\n", ""))
        self.assertTrue(any("aucun alias exploitable" in p for p in problems))

    def test_a_broken_cross_reference_is_refused(self):
        self.assertTrue(any("autre.md" in p for p in self.check(doc(), known=("demo",))))

    def test_generic_alias_is_refused_but_precise_expressions_pass(self):
        problems = self.check(doc().replace("alias: truss rod coincé, action haute", "alias: action"))
        self.assertTrue(any("« action »" in p for p in problems))
        self.assertTrue(gk.fiche_alias_usable("action haute"))
        self.assertTrue(gk.fiche_alias_usable("truss rod coince"))
        self.assertFalse(gk.fiche_alias_usable("manche"))
        self.assertFalse(gk.fiche_alias_usable("guitare"))

    def test_multi_word_alias_made_only_of_common_words_is_refused(self):
        for alias in ("manche corps", "cordes frettes", "neck relief", "relief du manche", "cordes et frettes"):
            self.assertFalse(gk.fiche_alias_usable(gk.normalize(alias)), alias)
            problems = self.check(doc().replace("alias: truss rod coincé, action haute", f"alias: {alias}, action haute"))
            self.assertTrue(any(f"« {alias} »" in p for p in problems), alias)


class TestPruneDecision(unittest.TestCase):
    def test_prune_is_refused_without_yes_in_dry_run_or_with_an_incomplete_directory(self):
        full = tempfile.mkdtemp()
        open(os.path.join(full, sf.SENTINEL), "w").close()
        empty = tempfile.mkdtemp()
        self.assertEqual(sf.prune_decision(False, False, True, full)[0], False)
        self.assertEqual(sf.prune_decision(True, True, True, full)[0], False)       # dry-run
        self.assertEqual(sf.prune_decision(True, False, False, full)[0], False)     # sans --yes
        refused, message = sf.prune_decision(True, False, True, empty)              # dossier incomplet
        self.assertFalse(refused)
        self.assertIn("introuvable", message)
        self.assertEqual(sf.prune_decision(True, False, True, full), (True, ""))


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

    def test_plan_and_orphans_work_before_the_fiche_tables_exist(self):
        """Un --dry-run (lecture seule) peut précéder le premier chargement réel, qui applique le schéma."""
        self.conn.execute("DROP TABLE guitar_knowledge_link, guitar_knowledge_fiche")
        planned = sf.plan(self.conn, [self._fiche(doc())], known_slugs={"demo", "autre"})
        self.assertFalse(planned[0]["unchanged"])
        self.assertEqual(sf.orphans(self.conn, planned), [])
        self.assertFalse(sf._has_fiche_tables(self.conn))

    def test_a_change_of_alias_rules_replays_an_unchanged_file(self):
        path = self._fiche(doc())
        self._load(path)
        self.assertTrue(self._load(path)[0][0]["unchanged"])
        with patch.object(sf, "FICHE_STOP", frozenset(gk.FICHE_STOP | {"nouveau"})):
            planned, written = self._load(path)
        self.assertEqual((planned[0]["unchanged"], written), (False, 1))

    def test_a_lost_brand_link_is_restored_without_force(self):
        path = self._fiche(doc(extra="concerne: Gibson\n"))
        self._load(path)
        self.conn.execute("DELETE FROM guitar_knowledge_link")      # marque supprimée puis recréée sous le même id
        planned, written = self._load(path)
        self.assertEqual((planned[0]["unchanged"], written), (False, 1))
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge_link").fetchone()["n"], 1)

    def test_a_concerne_id_that_does_not_exist_is_refused_with_the_fiche_name(self):
        for ref in ("manual:marque-inexistante", "wd:Q123"):
            path = self._fiche(doc(extra=f"concerne: {ref}\n"))
            with self.assertRaises(sf.SeedError) as ctx:
                sf.plan(self.conn, [path], known_slugs={"demo", "autre"})
            self.assertIn("demo.md", str(ctx.exception))
            self.assertIn(ref, str(ctx.exception))

    def test_a_concerne_id_must_be_a_brand_not_a_fiche(self):
        self._load(self._fiche(doc()))
        path = self._fiche(doc(extra="concerne: fiche:demo\n").replace("slug: demo", "slug: autre"), "autre.md")
        with self.assertRaises(sf.SeedError):
            sf.plan(self.conn, [path], known_slugs={"demo", "autre"})

    def test_reload_resets_the_columns_a_hand_made_row_could_have_changed(self):
        self.conn.execute("""INSERT INTO guitar_knowledge (id, kind, name, relevance, relevance_override, source, kb_version,
                             curated) VALUES ('fiche:demo','brand','x','accessories','accessories','wikidata',7,false)""")
        self._load(self._fiche(doc()))
        row = self.conn.execute("SELECT * FROM guitar_knowledge WHERE id = 'fiche:demo'").fetchone()
        self.assertEqual((row["kind"], row["relevance"], row["relevance_override"], row["curated"], row["source"],
                          row["kb_version"]), ("fiche", "guitars", None, True, "manual", 0))

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
