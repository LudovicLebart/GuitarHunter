"""Tests de l'amorçage sourcé (backend/scripts/seed_guitar_knowledge.py) : validation, confiance calculée, et
écriture sur un vrai Postgres (KB_TEST_DATABASE_URL, ignoré sinon)."""
import copy
import glob
import json
import os
import unittest

os.environ.setdefault("APP_ID_TARGET", "test")
os.environ.setdefault("USER_IDS_TARGET", "test_user")

from backend.scripts import seed_guitar_knowledge as sk


def entry(**over):
    base = {
        "slug": "vantage", "kind": "brand", "name": "Vantage", "description": "Marque de guitares.",
        "sources": [
            {"url": "https://en.wikipedia.org/wiki/Matsumoku", "publisher": "Wikipedia", "kind": "wikipedia",
             "excerpt": "Vantage production began in 1979"},
            {"url": "https://vintagejapanguitars.com/matsumoku-gakki-en/", "publisher": "Vintage Japan Guitars",
             "kind": "collector", "excerpt": "brands such as … Vantage …"},
        ],
    }
    base.update(over)
    return base


class TestValidation(unittest.TestCase):
    def test_valid_entry(self):
        self.assertEqual(sk.validate_entry(entry()), [])

    def test_entry_without_source_is_refused(self):
        problems = sk.validate_entry(entry(sources=[]))
        self.assertTrue(any("AUCUNE source" in p for p in problems))

    def test_source_needs_url_publisher_and_excerpt(self):
        bad = entry(sources=[{"url": "ftp://x", "kind": "blog"}])
        text = " ".join(sk.validate_entry(bad))
        for expected in ("url http(s)", "éditeur", "citation", "inconnu"):
            self.assertIn(expected, text)

    def test_long_excerpt_is_refused(self):
        e = entry()
        e["sources"][0]["excerpt"] = "x" * 400
        self.assertTrue(any("trop longue" in p for p in sk.validate_entry(e)))

    def test_missing_fields_bad_kind_bad_year_bad_alias(self):
        problems = " ".join(sk.validate_entry(entry(kind="magasin", description="", active_from="1979",
                                                    aliases=["ab", "6120"], slug="Mon Slug")))
        for expected in ("description", "kind « magasin »", "année", "inexploitable", "slug"):
            self.assertIn(expected, problems)

    def test_confidence_counts_distinct_publisher_domains(self):
        self.assertEqual(sk.confidence_of(entry()["sources"]), "sourced")
        two_pages_same_site = [
            {"url": "https://en.wikipedia.org/wiki/A"}, {"url": "https://fr.wikipedia.org/wiki/A"},
            {"url": "https://en.wikipedia.org/wiki/B"}]
        self.assertEqual(sk.confidence_of(two_pages_same_site[:1]), "single_source")
        self.assertEqual(sk.confidence_of([{"url": "https://www.jedistar.com/a"}, {"url": "https://jedistar.com/b"}]),
                         "single_source")     # « www. » ne fait pas un 2e éditeur
        # Wikipédia dans deux langues = UN éditeur ; deux blogs d'un même hébergeur = DEUX éditeurs
        self.assertEqual(sk.confidence_of([{"url": "https://en.wikipedia.org/wiki/A"}, {"url": "https://fr.wikipedia.org/wiki/A"}]),
                         "single_source")
        self.assertEqual(sk.confidence_of([{"url": "https://unblog.blogspot.com/a"}, {"url": "https://autreblog.blogspot.com/b"}]),
                         "sourced")
        self.assertEqual(sk.confidence_of([{"url": "https://unblog.blogspot.com/a"}, {"url": "https://unblog.blogspot.com/b"}]),
                         "single_source")

    def test_duplicate_slugs_are_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump([entry(), entry()], fh)
            with self.assertRaises(sk.SeedError):
                sk.load_entries([path])


def patch(**over):
    base = {"patch": "Vox", "relevance_override": "guitars", "hunt_notes": "Amplis ET guitares.",
            "sources": entry()["sources"]}
    base.update(over)
    return base


class TestPatchValidation(unittest.TestCase):
    def test_valid_patch(self):
        self.assertEqual(sk.validate_entry(patch()), [])

    def test_patch_needs_two_distinct_sites(self):
        one = patch(sources=entry()["sources"][:1])
        self.assertTrue(any("AU MOINS 2 sources" in p for p in sk.validate_entry(one)))
        same_site = patch(sources=[{"url": "https://en.wikipedia.org/wiki/A", "publisher": "W", "excerpt": "x"},
                                   {"url": "https://fr.wikipedia.org/wiki/A", "publisher": "W", "excerpt": "y"}])
        self.assertTrue(any("AU MOINS 2 sources" in p for p in sk.validate_entry(same_site)))

    def test_patch_field_rules(self):
        problems = " ".join(sk.validate_entry(patch(relevance_override="peut-être", tier="luxe", description="non")))
        for expected in ("relevance_override invalide", "tier invalide", "champs non autorisés"):
            self.assertIn(expected, problems)
        self.assertTrue(any("rien à corriger" in p for p in sk.validate_entry(
            {"patch": "Vox", "sources": entry()["sources"]})))


class TestShippedSeedFiles(unittest.TestCase):
    """Les fichiers de fiches livrés dans le dépôt doivent tous être valides (aucune fiche sans source)."""

    def test_every_shipped_entry_is_valid_and_sourced(self):
        paths = sorted(glob.glob(os.path.join(sk.SEED_DIR, "*.json")))
        self.assertTrue(paths)
        entries = sk.load_entries(paths)
        for e in entries:
            label = e.get("name") or e.get("patch")
            self.assertEqual(sk.validate_entry(e), [], label)
            self.assertGreaterEqual(len(e["sources"]), 1, f"{label} : aucune source")
            # une fiche à source unique est permise (stockée, jamais injectée) mais doit rester l'exception
            if len(e["sources"]) < 2 and not e.get("patch"):
                self.assertEqual(sk.confidence_of(e["sources"]), "single_source")


@unittest.skipUnless(os.getenv("KB_TEST_DATABASE_URL"),
                     "définir KB_TEST_DATABASE_URL (base Postgres JETABLE) pour tester l'écriture")
class TestSeedAgainstPostgres(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        from backend import guitar_knowledge as gk
        self.gk = gk
        gk.configure_version("latest")
        self.addCleanup(gk.configure_version, "validated")
        self.conn = psycopg.connect(os.environ["KB_TEST_DATABASE_URL"], autocommit=True, row_factory=dict_row)
        self.addCleanup(self.conn.close)
        with open(os.path.join(os.path.dirname(__file__), "api", "schema.sql"), encoding="utf-8") as fh:
            self.conn.execute(fh.read())
        self.conn.execute("TRUNCATE guitar_knowledge, guitar_knowledge_alias, guitar_knowledge_versions CASCADE")
        self.conn.execute("INSERT INTO guitar_knowledge_versions (version, source) VALUES (3, 't')")
        self.conn.execute("""INSERT INTO guitar_knowledge (id, kind, name, relevance, source, kb_version) VALUES
            ('wd:matsumoku', 'company', 'Matsumoku', 'unknown', 'wikidata', 3),
            ('wd:godin', 'company', 'Godin', 'guitars', 'wikidata', 3),
            ('wd:godin2', 'brand', 'Godin', 'guitars', 'wikidata', 3)""")   # « Godin » ambigu : company + brand
        self.gk.invalidate_cache()

    def _plan(self, entries):
        return sk.plan(self.conn, copy.deepcopy(entries))

    def test_write_resolves_names_writes_sources_and_aliases(self):
        planned = self._plan([entry(made_by=["Matsumoku"], aliases=["Vantage Guitars"], tier="entry")])
        self.assertEqual(sk.write(self.conn, planned), 4)        # nouvelle version (l'existante est la 3), non validée
        row = self.conn.execute("SELECT * FROM guitar_knowledge WHERE id='manual:vantage'").fetchone()
        self.assertEqual((row["made_by"], row["curated"], row["source"], row["confidence"], row["kb_version"], row["tier"]),
                         (["wd:matsumoku"], True, "manual", "sourced", 4, "entry"))
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge_source WHERE origin='manual'")
                         .fetchone()["n"], 2)
        aliases = {r["alias_norm"] for r in self.conn.execute("SELECT alias_norm FROM guitar_knowledge_alias").fetchall()}
        self.assertEqual(aliases, {"vantage", "vantage guitars"})

    def test_ambiguous_or_unknown_reference_is_refused_with_all_problems(self):
        with self.assertRaises(sk.SeedError) as ctx:
            self._plan([entry(parent="Godin"), entry(slug="x", name="X", parent="Inexistante")])
        message = str(ctx.exception)
        self.assertIn("ambigu", message)
        self.assertIn("aucune fiche de ce nom", message)

    def test_reference_by_exact_id_and_by_slug_of_the_same_batch(self):
        planned = self._plan([entry(slug="usine", kind="factory", name="Usine X", parent="wd:godin"),
                              entry(slug="marque", name="Marque Y", made_by=["usine"])])
        by_slug = {p["slug"]: p for p in planned}
        self.assertEqual(by_slug["usine"]["parent_id"], "wd:godin")
        self.assertEqual(by_slug["marque"]["made_by_ids"], ["manual:usine"])

    def test_rerun_is_idempotent_and_keeps_manual_curation(self):
        planned = self._plan([entry(aliases=["Vantage Guitars"])])
        sk.write(self.conn, planned)
        self.conn.execute("UPDATE guitar_knowledge SET hunt_notes='chercher les Avenger', tier='mid' WHERE id='manual:vantage'")
        self.conn.execute("INSERT INTO guitar_knowledge_alias VALUES ('avenger series','manual:vantage','Avenger','manual')")
        self.conn.execute("""INSERT INTO guitar_knowledge_source (knowledge_id, url, kind, origin)
                             VALUES ('manual:vantage', 'https://perso.example/v', 'collector', 'manual')""")
        sk.write(self.conn, self._plan([entry(aliases=["Vantage Guitars"])]))      # 2e passage
        row = self.conn.execute("SELECT * FROM guitar_knowledge WHERE id='manual:vantage'").fetchone()
        self.assertEqual((row["hunt_notes"], row["tier"]), ("chercher les Avenger", "mid"))   # rien n'est écrasé
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge WHERE id='manual:vantage'")
                         .fetchone()["n"], 1)
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge_alias WHERE knowledge_id='manual:vantage'")
                         .fetchone()["n"], 3)
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge_source WHERE knowledge_id='manual:vantage'")
                         .fetchone()["n"], 3)

    def test_single_source_fiche_is_stored_but_never_found(self):
        one = entry(slug="obscur", name="Marque Obscure", sources=entry()["sources"][:1])
        sk.write(self.conn, self._plan([one, entry()]))
        self.gk.invalidate_cache()
        self.assertEqual(self.conn.execute("SELECT confidence FROM guitar_knowledge WHERE id='manual:obscur'")
                         .fetchone()["confidence"], "single_source")
        self.assertEqual(self.gk.find_ids(self.conn, "vends marque obscure vintage"), {})     # jamais injectée
        self.assertIn("manual:vantage", self.gk.find_ids(self.conn, "guitare vantage 1979"))   # 2 sources : trouvée

    def test_name_as_alias_false_keeps_a_common_word_out(self):
        sk.write(self.conn, self._plan([entry(slug="profile-guitars", name="Profile", name_as_alias=False,
                                             aliases=["Profile Guitars"])]))
        self.gk.invalidate_cache()
        self.assertEqual(self.gk.find_ids(self.conn, "Accordeur à pince PROFILE PT-3000BK"), {})
        self.assertIn("manual:profile-guitars", self.gk.find_ids(self.conn, "Profile Guitars Silhouette 1985"))

    def _add_vox(self):
        self.conn.execute("""INSERT INTO guitar_knowledge (id, kind, name, description, relevance, source, kb_version)
                             VALUES ('wd:vox', 'brand', 'Vox', 'fabricant d''accessoires de musique', 'accessories', 'wikidata', 3)""")
        self.conn.execute("INSERT INTO guitar_knowledge_alias VALUES ('vox', 'wd:vox', 'Vox', 'wikidata')")
        self.gk.invalidate_cache()

    def test_patch_overrides_relevance_and_makes_the_brand_findable(self):
        self._add_vox()
        self.assertEqual(self.gk.find_ids(self.conn, "Guitare Vox Phantom 1965"), {})        # accessoire : jamais trouvée
        sk.write(self.conn, self._plan([patch()]))
        self.gk.invalidate_cache()
        self.assertIn("wd:vox", self.gk.find_ids(self.conn, "Guitare Vox Phantom 1965"))
        fiche = self.gk.lookup(self.conn, "Guitare Vox Phantom 1965")[0]
        self.assertEqual(fiche["relevance"], "guitars")                                      # pertinence effective
        self.assertIn("Amplis ET guitares", self.gk.format_for_prompt([fiche]))              # notes, pas « accessoires »
        self.assertNotIn("accessoires de musique", self.gk.format_for_prompt([fiche]))

    def test_seed_and_patch_go_into_a_new_unvalidated_version(self):
        """Un amorçage n'entre jamais en prod sans validation : la fiche corrigée sort de la version validée."""
        self.conn.execute("UPDATE guitar_knowledge_versions SET validated = true WHERE version = 3")
        self._add_vox()
        self.conn.execute("UPDATE guitar_knowledge SET relevance = 'guitars' WHERE id = 'wd:vox'")   # visible en v3
        self.gk.invalidate_cache()
        self.gk.configure_version("validated")
        self.assertIn("wd:vox", self.gk.find_ids(self.conn, "guitare vox"))
        version = sk.write(self.conn, self._plan([patch(), entry(slug="nouvelle", name="Marque Nouvelle")]), notes="test")
        self.assertEqual(version, 4)
        row = self.conn.execute("SELECT validated, source, notes, counts FROM guitar_knowledge_versions WHERE version = 4").fetchone()
        self.assertEqual((row["validated"], row["source"], row["notes"], row["counts"]),
                         (False, "seed", "test", {"fiches": 1, "corrections": 1}))
        self.gk.invalidate_cache()
        self.assertEqual(self.gk.find_ids(self.conn, "guitare vox et marque nouvelle"), {})     # rien de la v4 tant que non validée
        self.gk.configure_version("latest")
        self.assertEqual(set(self.gk.find_ids(self.conn, "guitare vox et marque nouvelle")), {"wd:vox", "manual:nouvelle"})
        self.conn.execute("UPDATE guitar_knowledge_versions SET validated = true WHERE version = 4")
        self.gk.configure_version("validated")
        self.assertEqual(set(self.gk.find_ids(self.conn, "guitare vox et marque nouvelle")), {"wd:vox", "manual:nouvelle"})

    def test_patch_never_overwrites_existing_notes_and_survives_a_reimport(self):
        import contextlib
        from unittest.mock import patch as mock_patch
        from backend.scripts import import_guitar_knowledge_wikidata as imp
        conn = self.conn

        class _Pool:
            @contextlib.contextmanager
            def connection(self):
                yield conn

        pool_patcher = mock_patch("backend.pg_db.init_pool", return_value=_Pool())
        pool_patcher.start()
        self.addCleanup(pool_patcher.stop)
        self._add_vox()
        self.conn.execute("UPDATE guitar_knowledge SET hunt_notes = 'MES NOTES' WHERE id = 'wd:vox'")
        sk.write(self.conn, self._plan([patch(hunt_notes="notes du patch")]))
        row = self.conn.execute("SELECT hunt_notes, relevance_override, curated FROM guitar_knowledge WHERE id='wd:vox'").fetchone()
        self.assertEqual((row["hunt_notes"], row["relevance_override"], row["curated"]), ("MES NOTES", "guitars", True))
        rec = {"id": "wd:vox", "kind": "brand", "name": "Vox", "description": "fabricant d'accessoires", "parent_id": None,
               "countries": None, "active_from": None, "active_to": None, "relevance": "accessories",
               "wikidata_qid": "vox", "wikipedia_url": None, "aliases": ["Vox"], "raw": {}}
        keep = {**rec, "id": "wd:godin", "name": "Godin", "aliases": ["Godin"]}
        imp.write_records([rec, keep], "reimport")                                            # l'import ré-écrit relevance
        row = self.conn.execute("SELECT relevance, relevance_override FROM guitar_knowledge WHERE id='wd:vox'").fetchone()
        self.assertEqual((row["relevance"], row["relevance_override"]), ("accessories", "guitars"))   # la surcharge survit

    def test_patch_on_unknown_or_ambiguous_target_is_refused(self):
        with self.assertRaises(sk.SeedError):
            self._plan([patch(patch="Inexistante")])
        with self.assertRaises(sk.SeedError) as ctx:
            self._plan([patch(patch="Godin")])                                                # deux fiches « Godin » dans ce jeu d'essai
        self.assertIn("ambigu", str(ctx.exception))

    def test_patch_can_flip_a_guitar_brand_back_to_accessories(self):
        self.conn.execute("""INSERT INTO guitar_knowledge (id, kind, name, relevance, source, kb_version)
                             VALUES ('wd:pedals', 'company', 'Boutik', 'guitars', 'wikidata', 3)""")
        self.conn.execute("INSERT INTO guitar_knowledge_alias VALUES ('boutik', 'wd:pedals', 'Boutik', 'wikidata')")
        self.gk.invalidate_cache()
        self.assertIn("wd:pedals", self.gk.find_ids(self.conn, "pedale boutik"))
        sk.write(self.conn, self._plan([patch(patch="Boutik", relevance_override="accessories", hunt_notes=None)]))
        self.gk.invalidate_cache()
        self.assertEqual(self.gk.find_ids(self.conn, "pedale boutik"), {})

    def test_shipped_batch_plans_against_a_kb_containing_its_references(self):
        # Le lot livré ne doit dépendre que de fiches « Godin » et « Matsumoku » uniques dans la base réelle.
        self.conn.execute("DELETE FROM guitar_knowledge WHERE id = 'wd:godin2'")
        self.conn.execute("""INSERT INTO guitar_knowledge (id, kind, name, relevance, source, kb_version) VALUES
            ('wd:vox', 'brand', 'Vox', 'accessories', 'wikidata', 3), ('wd:supro', 'company', 'Supro', 'accessories', 'wikidata', 3)""")
        entries = sk.load_entries(sorted(glob.glob(os.path.join(sk.SEED_DIR, "*.json"))))
        planned = sk.plan(self.conn, entries)
        self.assertEqual(len(planned), len(entries))
        sk.write(self.conn, planned)
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge WHERE source='manual'").fetchone()["n"],
                         len([e for e in entries if not e.get("patch")]))
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge WHERE relevance_override = 'guitars'")
                         .fetchone()["n"], len([e for e in entries if e.get("patch")]))


if __name__ == "__main__":
    unittest.main()
