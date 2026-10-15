"""Page HTML de relecture des fiches : extraits surlignés, données embarquées, export lu par knowledge_review_apply."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter

from backend.scripts import knowledge_review_apply as apply_
from backend.scripts import knowledge_review_html as rh


def _fiche(fid="wd:a", name="Marquea", **kw):
    f = {"id": fid, "name": name, "kind": "brand", "description": "Fabricant de guitares.", "countries": ["CA"],
         "active_from": 1970, "active_to": None, "relevance": "guitars", "aliases": [name], "parent_name": None,
         "hard": [], "flags": ["source unique"], "trusted": False, "state": None}
    f.update(kw)
    return f


class TestSnippet(unittest.TestCase):
    def test_highlights_the_trigger_ignoring_case_and_accents(self):
        s = rh.snippet_around("Vends une très belle GUERILLA M-SR7 en parfait état, jamais jouée sur scène.", "guerilla m sr7")
        self.assertEqual(s["hit"], "GUERILLA M-SR7")
        self.assertTrue(s["after"].startswith(" en parfait"))
        s = rh.snippet_around("Guitare Épiphone Casino 1966", "epiphone")
        self.assertEqual(s["hit"], "Épiphone")

    def test_whole_words_only(self):
        self.assertEqual(rh.snippet_around("une guitare marqueable", "marque")["hit"], "")

    def test_long_text_is_cut_around_the_hit_with_ellipses(self):
        text = "x " * 400 + "Marquea" + " y" * 400
        s = rh.snippet_around(text, "marquea", width=60)
        self.assertEqual(s["hit"], "Marquea")
        self.assertTrue(s["before"].startswith("…") and s["after"].endswith("…"))
        self.assertLess(len(s["before"]) + len(s["after"]), 100)

    def test_no_match_falls_back_to_the_start_of_the_text(self):
        s = rh.snippet_around("Texte sans rien.", "absent")
        self.assertEqual((s["hit"], s["before"]), ("", "Texte sans rien."))
        self.assertEqual(rh.snippet_around(None, "x"), {"before": "", "hit": "", "after": ""})


class TestPage(unittest.TestCase):
    def _cards(self):
        deal = {"id": "d1", "title": "Marquea </script> test", "description": "Une Marquea rare", "link": "https://x/y",
                "price": 500, "storage_image_urls": ["https://img/1.jpg"], "image_urls": None}
        return rh.build_cards([_fiche()], Counter({"wd:a": 3}), {"wd:a": [{"deal": deal, "alias": "marquea", "how": "exact"}]},
                              {"wd:a": [{"url": "https://wikidata.org/Q1", "kind": "wikidata", "title": "Q1",
                                         "publisher": "Wikidata", "excerpt": None}]})

    def test_card_carries_listing_photo_link_snippet_and_sources(self):
        c = self._cards()[0]
        l = c["listings"][0]
        self.assertEqual((l["image"], l["link"], l["price"], l["snippet"]["hit"]), ("https://img/1.jpg", "https://x/y", "500", "Marquea"))
        self.assertEqual(c["sources"][0]["url"], "https://wikidata.org/Q1")
        self.assertEqual((c["n_hits"], c["years"]), (3, "1970–"))

    def test_embedded_data_cannot_close_the_script_tag(self):
        html = rh.render_html(self._cards(), generated="t")
        body = html.split("const DATA = ", 1)[1].split(";\nconst KEY", 1)[0]
        self.assertNotIn("</", body)
        self.assertEqual(json.loads(body.replace("<\\/", "</"))["fiches"][0]["listings"][0]["title"], "Marquea </script> test")

    @unittest.skipUnless(shutil.which("node"), "node absent")
    def test_script_is_valid_javascript_and_export_round_trips_through_the_parser(self):
        html = rh.render_html(self._cards(), generated="t")
        script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
        with tempfile.TemporaryDirectory() as d:
            full = os.path.join(d, "page.js")
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(script)
            self.assertEqual(subprocess.run(["node", "--check", full]).returncode, 0)
            test = os.path.join(d, "t.js")
            with open(test, "w", encoding="utf-8") as fh:
                fh.write(rh.EXPORT_JS + """
const fiches = [{id:'wd:a',name:'Marquea',kind:'brand'},{id:'wd:b',name:'Marqueb',kind:'line'},{id:'wd:c',name:'Marquec',kind:'brand'},{id:'wd:d',name:'Marqued',kind:'brand'}];
const state = {'wd:a':{d:'A'},'wd:b':{d:'R',note:'années\\nfausses,  c\\'est 1957'},'wd:c':{d:'?'}};
process.stdout.write(exportText(fiches, state));""")
            out = subprocess.run(["node", test], capture_output=True, text=True, check=True).stdout
        self.assertEqual(apply_.parse_sheet(out), [("wd:a", "approved", None), ("wd:b", "rejected", "années fausses, c'est 1957")])


@unittest.skipUnless(os.getenv("KB_TEST_DATABASE_URL"), "définir KB_TEST_DATABASE_URL (base Postgres JETABLE)")
class TestExamplesPostgres(unittest.TestCase):
    def test_hit_counts_collects_recent_examples_and_sources_are_fetched(self):
        import psycopg
        from psycopg.rows import dict_row
        from backend import guitar_knowledge as gk
        from backend.scripts import knowledge_gate_report as rep
        from backend.test_guitar_knowledge import use_latest_kb
        conn = psycopg.connect(os.environ["KB_TEST_DATABASE_URL"], autocommit=True, row_factory=dict_row)
        self.addCleanup(conn.close)
        with open(os.path.join(os.path.dirname(__file__), "api", "schema.sql"), encoding="utf-8") as fh:
            conn.execute(fh.read())
        conn.execute("TRUNCATE guitar_knowledge, guitar_knowledge_alias, guitar_knowledge_versions, guitar_deals CASCADE")
        use_latest_kb(self)
        conn.execute("""INSERT INTO guitar_knowledge (id, kind, name, description, relevance, source, kb_version, raw)
                        VALUES ('wd:a','brand','Marquea','Fabricant américain de guitares électriques, actif depuis 1950.',
                                'guitars','wikidata',1,'{}')""")
        conn.execute("INSERT INTO guitar_knowledge_alias VALUES ('marquea','wd:a','Marquea','wikidata')")
        conn.execute("INSERT INTO guitar_knowledge_source (knowledge_id, url, kind, title) VALUES "
                     "('wd:a','https://www.wikidata.org/wiki/Q1','wikidata','Q1')")
        for i in range(6):
            conn.execute("INSERT INTO guitar_deals (id, title, description, link, \"timestamp\") VALUES (%s,%s,%s,%s, now() - (%s || ' hours')::interval)",
                         (f"d{i}", f"Marquea numéro {i}", "belle guitare", f"https://l/{i}", str(i)))
        gk.invalidate_cache()
        examples = {}
        hits, n = rep.hit_counts(conn, examples=examples)
        self.assertEqual((hits["wd:a"], n), (6, 6))
        self.assertEqual([e["deal"]["id"] for e in examples["wd:a"]], ["d0", "d1", "d2", "d3"])     # les 4 plus récentes
        self.assertEqual(examples["wd:a"][0]["alias"], "marquea")
        self.assertEqual(rh.fetch_sources(conn, ["wd:a"])["wd:a"][0]["url"], "https://www.wikidata.org/wiki/Q1")


if __name__ == "__main__":
    unittest.main()
