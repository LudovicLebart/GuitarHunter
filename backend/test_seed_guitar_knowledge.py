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

    def test_duplicate_slugs_are_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump([entry(), entry()], fh)
            with self.assertRaises(sk.SeedError):
                sk.load_entries([path])


class TestShippedSeedFiles(unittest.TestCase):
    """Les fichiers de fiches livrés dans le dépôt doivent tous être valides (aucune fiche sans source)."""

    def test_every_shipped_entry_is_valid_and_sourced(self):
        paths = sorted(glob.glob(os.path.join(sk.SEED_DIR, "*.json")))
        self.assertTrue(paths)
        entries = sk.load_entries(paths)
        for e in entries:
            self.assertEqual(sk.validate_entry(e), [], e.get("name"))
            self.assertGreaterEqual(len(e["sources"]), 1, f"{e['name']} : aucune source")
            # une fiche à source unique est permise (stockée, jamais injectée) mais doit rester l'exception
            if len(e["sources"]) < 2:
                self.assertEqual(sk.confidence_of(e["sources"]), "single_source")


@unittest.skipUnless(os.getenv("KB_TEST_DATABASE_URL"),
                     "définir KB_TEST_DATABASE_URL (base Postgres JETABLE) pour tester l'écriture")
class TestSeedAgainstPostgres(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        from backend import guitar_knowledge as gk
        self.gk = gk
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
        self.assertEqual(sk.write(self.conn, planned), 3)
        row = self.conn.execute("SELECT * FROM guitar_knowledge WHERE id='manual:vantage'").fetchone()
        self.assertEqual((row["made_by"], row["curated"], row["source"], row["confidence"], row["kb_version"], row["tier"]),
                         (["wd:matsumoku"], True, "manual", "sourced", 3, "entry"))
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

    def test_shipped_batch_plans_against_a_kb_containing_its_references(self):
        # Le lot livré ne doit dépendre que de fiches « Godin » et « Matsumoku » uniques dans la base réelle.
        self.conn.execute("DELETE FROM guitar_knowledge WHERE id = 'wd:godin2'")
        entries = sk.load_entries(sorted(glob.glob(os.path.join(sk.SEED_DIR, "*.json"))))
        planned = sk.plan(self.conn, entries)
        self.assertEqual(len(planned), len(entries))
        sk.write(self.conn, planned)
        self.assertEqual(self.conn.execute("SELECT count(*) AS n FROM guitar_knowledge WHERE source='manual'").fetchone()["n"],
                         len(entries))


if __name__ == "__main__":
    unittest.main()
