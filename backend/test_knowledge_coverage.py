"""Tests de la carte des trous (backend/scripts/knowledge_coverage.py) : logique pure avec une recherche
simulée, plus un test de bout en bout sur un vrai Postgres (KB_TEST_DATABASE_URL, ignoré sinon)."""
import csv
import os
import tempfile
import unittest

os.environ.setdefault("APP_ID_TARGET", "test")
os.environ.setdefault("USER_IDS_TARGET", "test_user")

from backend.scripts import knowledge_coverage as kc

KINDS = {"wd:fender": "brand", "wd:strat": "line", "wd:teisco": "company", "wd:ritter": "luthier"}


def fake_find(*texts):
    """Recherche simulée : reconnaît fender / stratocaster / teisco / (le luthier n'est jamais une marque)."""
    blob = " ".join(t or "" for t in texts).lower()
    found = {}
    if "fender" in blob:
        found["wd:fender"] = ("fender", "exact")
    if "stratocaster" in blob:
        found["wd:strat"] = ("stratocaster", "exact")
    if "teisco" in blob:
        found["wd:teisco"] = ("teisco", "fuzzy")
    if "ritter" in blob:
        found["wd:ritter"] = ("ritter", "exact")
    return found


def row(title, brand, model="", status="analyzed", verdict="FAIR", price=100, link=None):
    return {"id": title, "title": title, "brand_any": brand, "model_name": model, "status": status,
            "verdict": verdict, "price": price, "link": link or f"https://x/{title}"}


class TestAnalyze(unittest.TestCase):
    def setUp(self):
        self.rows = [
            row("Fender Stratocaster 1979", "Fender", "Stratocaster", verdict="PEPITE"),
            row("Fender Bronco", "Fender", "Bronco"),                                      # marque connue, modèle absent
            row("Guitare Kalamazoo KG-1", "Kalamazoo", "KG-1", verdict="PEPITE", price=300),
            row("Kalamazoo lap steel", "KALAMAZOO", "", verdict="FAIR", price=150),      # même marque, autre casse
            row("Kalamazoo amp", "kalamazöo", "", status="rejected", verdict="REJECTED_ITEM", price=50),
            row("Vieille guitare", "Inconnu", ""),                                         # pas une marque
            row("Teisco May Queen", "Teisco", "May Queen"),                                # reconnue seulement en approximatif
            row("Guitare sans marque", "", ""),
            row("Ritter Instruments", "Ritter", "", verdict="COLLECTION"),                 # luthier ≠ marque
        ]
        self.report = kc.analyze(self.rows, KINDS, fake_find, min_count=1)

    def test_brand_variants_are_grouped_and_counted(self):
        gap = next(g for g in self.report["gaps"] if g["brand"] == "kalamazoo")
        self.assertEqual((gap["n_listings"], gap["n_gems"], gap["n_accepted"], gap["n_rejected"]), (3, 1, 1, 1))
        self.assertEqual(gap["median_price"], 150)
        self.assertEqual(set(gap["variants"]), {"Kalamazoo", "KALAMAZOO", "kalamazöo"})
        self.assertEqual(len(gap["sample_titles"]), 3)

    def test_gems_rank_first(self):
        # Kalamazoo (1 pépite) et Ritter (1 pépite : un luthier n'est pas une marque connue) passent avant les autres
        self.assertEqual([g["brand"] for g in self.report["gaps"]][:2], ["kalamazoo", "ritter"])

    def test_non_brands_are_skipped_and_counted(self):
        self.assertEqual(self.report["brands"]["no_brand"], 2)                             # « Inconnu » et vide
        self.assertNotIn("inconnu", {g["brand"] for g in self.report["gaps"]})

    def test_fuzzy_only_recognition_is_reported_separately(self):
        self.assertEqual(self.report["brands"]["fuzzy_only"], 1)                           # Teisco
        self.assertEqual(self.report["brands"]["exact"], 2)                                # les deux Fender
        self.assertEqual(self.report["brands"]["missing"], 4)                              # 3 Kalamazoo + Ritter

    def test_listing_coverage_by_group(self):
        cov = self.report["listing_coverage"]
        self.assertEqual(cov["all"], {"total": 9, "recognized": 3})    # Strat, Bronco, Teisco (Ritter = luthier, non compté)
        self.assertEqual(cov["gem"]["total"], 3)
        self.assertEqual(cov["rejected"], {"total": 1, "recognized": 0})

    def test_model_gaps_only_for_known_brands(self):
        gaps = {(g["brand"], g["model"]) for g in self.report["model_gaps"]}
        self.assertIn(("fender", "bronco"), gaps)
        self.assertNotIn(("fender", "stratocaster"), gaps)                                 # série connue
        self.assertFalse(any(b == "kalamazoo" for b, _ in gaps))                           # marque inconnue = trou de marque

    def test_min_count_filters_rare_gaps(self):
        report = kc.analyze(self.rows, KINDS, fake_find, min_count=2)
        self.assertEqual([g["brand"] for g in report["gaps"]], ["kalamazoo"])

    def test_csv_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gaps.csv")
            kc.write_csv(self.report, path)
            with open(path, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        kal = next(r for r in rows if r["brand"] == "kalamazoo")
        self.assertEqual((kal["type"], kal["n_gems"], kal["decision"]), ("marque_absente", "1", ""))
        self.assertTrue(any(r["type"] == "modele_absent" and r["model"] == "bronco" for r in rows))

    def test_known_accessory_brands_are_not_gaps(self):
        rows = [row("Pédale delay", "Line 6"), row("Câble", "D'Addario")]
        report = kc.analyze(rows, KINDS, fake_find, min_count=1, accessory_brands={"line 6", "d addario"})
        self.assertEqual(report["gaps"], [])
        self.assertEqual(report["brands"]["known_accessory"], 2)

    def test_word_order_variants_are_merged(self):
        rows = [row("Catania Carmelo acoustic 1963", "Carmelo Catania", verdict="PEPITE"),
                row("Carmelo Catania guitare", "Catania Carmelo")]
        gaps = kc.analyze(rows, KINDS, fake_find, min_count=1)["gaps"]
        self.assertEqual(len(gaps), 1)
        self.assertEqual((gaps[0]["n_listings"], gaps[0]["n_pepites"]), (2, 1))
        self.assertEqual(set(gaps[0]["variants"]), {"Carmelo Catania", "Catania Carmelo"})

    def test_probable_type_from_titles(self):
        rows = [row("Pédale delay Joyo", "Joyo"), row("Joyo overdrive pedal", "Joyo"), row("Joyo guitare", "Joyo"),
                row("Ampli Orange 20W", "Orange"), row("Amplificateur guitare", "Orange"),
                row("Guitare Yamaki 1975", "Yamaki")]
        gaps = {g["brand"]: g for g in kc.analyze(rows, KINDS, fake_find, min_count=1)["gaps"]}
        self.assertEqual(gaps["joyo"]["probable_type"], "pedale/effet")
        self.assertEqual(gaps["orange"]["probable_type"], "ampli")
        self.assertEqual(gaps["yamaki"]["probable_type"], "guitare/autre")

    def test_non_guitar_gaps_are_hidden_unless_requested(self):
        import contextlib
        import io
        rows = [row("Ampli Orange 20W", "Orange"), row("Amplificateur guitare", "Orange"),
                row("Guitare Yamaki 1975", "Yamaki"), row("Guitare Yamaki", "Yamaki")]
        report = kc.analyze(rows, KINDS, fake_find, min_count=1)
        report["kb_fiches"] = 4
        for all_types, expect_orange in ((False, False), (True, True)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                kc.print_report(report, top=10, all_types=all_types)
            out = buf.getvalue()
            self.assertIn("yamaki", out)
            self.assertEqual("orange" in out.split("2b.")[1].split("== 3.")[0].lower(), expect_orange, all_types)

    def test_multiline_titles_do_not_break_the_report_or_csv(self):
        rows = [row("Guitare Yamaki\nSeulement 99$\ndans Montréal", "Yamaki")] * 2
        report = kc.analyze(rows, KINDS, fake_find, min_count=1)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            report["kb_fiches"] = 1
            kc.print_report(report, top=5)
        self.assertNotIn("Seulement", buf.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "g.csv")
            kc.write_csv(report, path)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(len(list(csv.DictReader(fh))), 1)

    def test_print_report_runs(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.report["kb_fiches"] = 4
            kc.print_report(self.report, top=5)
        out = buf.getvalue()
        self.assertIn("COUVERTURE", out)
        self.assertIn("kalamazoo", out)


@unittest.skipUnless(os.getenv("KB_TEST_DATABASE_URL"),
                     "définir KB_TEST_DATABASE_URL (base Postgres JETABLE) pour le test de bout en bout")
class TestAgainstPostgres(unittest.TestCase):
    def test_end_to_end_and_read_only_guarantee(self):
        import psycopg
        from psycopg.rows import dict_row
        from backend import guitar_knowledge as gk
        url = os.environ["KB_TEST_DATABASE_URL"]
        admin = psycopg.connect(url, autocommit=True, row_factory=dict_row)
        self.addCleanup(admin.close)
        with open(os.path.join(os.path.dirname(__file__), "api", "schema.sql"), encoding="utf-8") as fh:
            admin.execute(fh.read())
        admin.execute("TRUNCATE guitar_knowledge, guitar_knowledge_alias, guitar_knowledge_versions, guitar_deals CASCADE")
        admin.execute("INSERT INTO guitar_knowledge_versions (version, source) VALUES (1, 't')")
        admin.execute("""INSERT INTO guitar_knowledge (id, kind, name, relevance, source, kb_version)
                         VALUES ('wd:fender', 'brand', 'Fender', 'guitars', 'wikidata', 1)""")
        admin.execute("INSERT INTO guitar_knowledge_alias VALUES ('fender', 'wd:fender', 'Fender', 'wikidata')")
        admin.execute("""INSERT INTO guitar_knowledge (id, kind, name, relevance, source, kb_version)
                         VALUES ('wd:pedals', 'company', 'Maxon', 'accessories', 'wikidata', 1)""")
        admin.execute("INSERT INTO guitar_knowledge_alias VALUES ('maxon', 'wd:pedals', 'Maxon', 'wikidata')")
        admin.execute("INSERT INTO guitar_deals (id, title, brand, status, verdict) VALUES ('m1', 'Maxon OD808', 'Maxon', 'analyzed', 'FAIR')")
        for i, (title, brand, status, verdict) in enumerate([
                ("Fender Jazzmaster", "Fender", "analyzed", "FAIR"),
                ("Kalamazoo KG-1", "Kalamazoo", "analyzed", "PEPITE"),
                ("Kalamazoo KG-2", "Kalamazoo", "rejected", "REJECTED_ITEM")]):
            admin.execute("INSERT INTO guitar_deals (id, title, brand, status, verdict, price) VALUES (%s,%s,%s,%s,%s,120)",
                          (f"d{i}", title, brand, status, verdict))
        # une annonce rejetée sans `brand` final : la marque du Portier (gatekeeper_brand) sert de repli
        admin.execute("INSERT INTO guitar_deals (id, title, status, verdict, gatekeeper_brand) "
                      "VALUES ('d9', 'Kalamazoo lap steel', 'rejected', 'REJECTED_ITEM', 'Kalamazoo')")
        gk.invalidate_cache()

        conn = psycopg.connect(url, row_factory=dict_row)
        conn.read_only = True
        self.addCleanup(conn.close)
        report = kc.run_analysis(conn, min_count=2)
        gap = report["gaps"][0]
        self.assertEqual((gap["brand"], gap["n_listings"], gap["n_gems"], gap["n_rejected"]), ("kalamazoo", 3, 1, 2))
        self.assertEqual(report["brands"]["exact"], 1)
        self.assertEqual(report["brands"]["known_accessory"], 1)     # Maxon : accessoire connu, pas un trou
        self.assertEqual([g["brand"] for g in report["gaps"]], ["kalamazoo"])
        with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("DELETE FROM guitar_deals")


if __name__ == "__main__":
    unittest.main()
