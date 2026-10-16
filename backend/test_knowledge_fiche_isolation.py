"""Les fiches techniques de restauration partagent la base `guitar_knowledge` avec les marques : ces tests
garantissent qu'elles ne peuvent JAMAIS entrer dans ce que lit le Portier (liste blanche de types, kb_version 0,
aucune version créée), et que la recherche des fiches ne remonte pas les marques.

Les tests SQL tournent contre un Postgres JETABLE (`KB_TEST_DATABASE_URL`), comme les autres tests de la base ;
le premier ne demande aucune base."""
import os
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("APP_ID_TARGET", "test")
os.environ.setdefault("USER_IDS_TARGET", "test_user")

from backend import guitar_knowledge as gk
from backend.scripts import knowledge_coverage as cov
from backend.scripts import seed_guitar_knowledge as sk


class _Recorder:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        result = MagicMock()
        result.fetchall.return_value = []
        return result


class TestWhitelistByDefault(unittest.TestCase):
    def setUp(self):
        gk.invalidate_cache()
        self.addCleanup(gk.invalidate_cache)

    def test_default_lookup_only_asks_for_brand_kinds(self):
        conn = _Recorder()
        gk.find_ids(conn, "Gibson Les Paul")
        sql, params = conn.calls[-1]
        self.assertIn("k.kind = ANY(%s)", sql)
        self.assertEqual(sorted(params[0]), sorted(gk.BRAND_KINDS))
        self.assertNotIn("fiche", params[0])

    def test_fiche_kinds_are_never_brand_kinds(self):
        self.assertFalse(set(gk.FICHE_KINDS) & set(gk.BRAND_KINDS))
        self.assertEqual(sk.KINDS, set(gk.BRAND_KINDS))      # un amorçage de marques ne peut pas créer de fiche


@unittest.skipUnless(os.getenv("KB_TEST_DATABASE_URL"),
                     "définir KB_TEST_DATABASE_URL (base Postgres JETABLE) pour tester l'isolation des fiches")
class TestFicheIsolationPostgres(unittest.TestCase):
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
        gk.configure_version("validated")
        self.conn.execute("INSERT INTO guitar_knowledge_versions (version, source, validated) VALUES (1,'t',true)")
        self._row("manual:gibson", "brand", "Gibson", "manual", 1, curated=True)
        # Version bien SUPÉRIEURE à la dernière validée : une fiche normale serait exclue par la version, celle-ci
        # doit rester invisible pour le Portier pour une autre raison (son type), pas par hasard.
        self._row("fiche:truss-rod", "fiche", "Ajuster le truss rod", "manual", 99, confidence="sourced",
                  aliases=("truss rod", "gibson"))
        self._row("fiche:neck-reset", "fiche", "Neck reset", "manual", 0, confidence="single_source",
                  aliases=("neck reset",))
        gk.invalidate_cache()

    def _row(self, kid, kind, name, source, version, curated=False, confidence=None, aliases=()):
        self.conn.execute(
            """INSERT INTO guitar_knowledge (id, kind, name, relevance, source, kb_version, curated, confidence)
               VALUES (%s,%s,%s,'guitars',%s,%s,%s,%s)""",
            (kid, kind, name, source, version, curated, confidence))
        for norm in dict.fromkeys(gk.normalize(a) for a in (name, *aliases)):
            if gk.alias_usable(norm):
                self.conn.execute("INSERT INTO guitar_knowledge_alias VALUES (%s,%s,%s,'manual')", (norm, kid, norm))

    def test_portier_search_never_returns_a_fiche(self):
        # « gibson » est aussi un alias de la fiche : seule la marque doit ressortir.
        found = gk.find_ids(self.conn, "Gibson Les Paul, truss rod à régler, neck reset à prévoir")
        self.assertEqual(set(found), {"manual:gibson"})
        fiches = gk.lookup(self.conn, "Gibson Les Paul truss rod neck reset")
        self.assertEqual([f["id"] for f in fiches], ["manual:gibson"])

    def test_portier_prompt_block_never_mentions_a_fiche(self):
        block = gk.format_for_prompt(gk.lookup(self.conn, "Gibson truss rod neck reset"))
        self.assertIn("Gibson", block)
        self.assertNotIn("truss rod", block.lower())
        self.assertNotIn("neck reset", block.lower())

    def test_fiches_do_not_change_the_effective_version(self):
        self.assertEqual(gk.effective_version(self.conn), 1)
        gk.configure_version("latest")
        self.assertEqual(gk.effective_version(self.conn), 1)

    def test_fiche_search_finds_fiches_only_and_ignores_version_and_confidence(self):
        found = gk.find_ids(self.conn, "Gibson avec truss rod coincé, neck reset", kinds=gk.FICHE_KINDS)
        self.assertEqual(set(found), {"fiche:truss-rod", "fiche:neck-reset"})   # y compris single_source, kb_version 99
        rows = gk.lookup(self.conn, "truss rod", kinds=gk.FICHE_KINDS)
        self.assertEqual([r["id"] for r in rows], ["fiche:truss-rod"])

    def test_the_two_searches_use_separate_caches(self):
        gk.find_ids(self.conn, "gibson")
        gk.find_ids(self.conn, "gibson", kinds=gk.FICHE_KINDS)
        self.assertEqual(set(gk.find_ids(self.conn, "gibson")), {"manual:gibson"})
        self.assertEqual(set(gk.find_ids(self.conn, "gibson", kinds=gk.FICHE_KINDS)), {"fiche:truss-rod"})

    def test_a_mixed_query_applies_each_kind_s_own_alias_rule(self):
        # alias « action » ajouté À LA MAIN sur une fiche (le chargeur n'y touche jamais) : refusé à la lecture,
        # même quand la requête mélange marques et fiches.
        self.conn.execute("INSERT INTO guitar_knowledge_alias VALUES ('action','fiche:truss-rod','action','manual')")
        gk.invalidate_cache()
        mixed = gk.BRAND_KINDS + gk.FICHE_KINDS
        self.assertNotIn("fiche:truss-rod", gk.find_ids(self.conn, "belle action sur cette guitare", kinds=mixed))
        self.assertIn("fiche:truss-rod", gk.find_ids(self.conn, "reglage du truss rod", kinds=mixed))
        self.assertIn("manual:gibson", gk.find_ids(self.conn, "Gibson", kinds=mixed))

    def test_an_empty_kinds_means_brands_only_never_everything(self):
        self.assertEqual(set(gk.find_ids(self.conn, "gibson truss rod", kinds=())), {"manual:gibson"})
        self.assertEqual([r["id"] for r in gk.lookup(self.conn, "gibson truss rod", kinds=())], ["manual:gibson"])

    def test_fiche_search_has_no_fuzzy_matching(self):
        self._row("fiche:bourdon", "fiche", "Bourdonnement des cordes", "manual", 0, aliases=("bourdonnement",))
        gk.invalidate_cache()
        self.assertIn("fiche:bourdon", gk.find_ids(self.conn, "un bourdonnement", kinds=gk.FICHE_KINDS))
        self.assertNotIn("fiche:bourdon", gk.find_ids(self.conn, "un bourdonement", kinds=gk.FICHE_KINDS))   # faute de frappe

    def test_a_seed_reference_never_resolves_to_a_fiche(self):
        with self.assertRaises(sk.SeedError):
            sk.resolve_ref(self.conn, "Neck reset", set())
        self.assertEqual(sk.resolve_ref(self.conn, "Gibson", set()), "manual:gibson")

    def test_coverage_statistics_ignore_fiches(self):
        self.assertEqual(set(cov.load_kinds(self.conn)), {"manual:gibson"})
        self.conn.execute("UPDATE guitar_knowledge SET relevance_override = 'accessories' WHERE id = 'fiche:neck-reset'")
        self.assertNotIn("neck reset", cov.load_accessory_aliases(self.conn))


if __name__ == "__main__":
    unittest.main()
