"""Tests de `repair_fb_city_ids.py` : logique de décision pure (sans Facebook) et application réelle contre
un Postgres local (se saute proprement si injoignable, comme backend/test_pg_repository.py)."""
import json
import os
import tempfile
import unittest

import psycopg
from psycopg.rows import dict_row

from backend.scraping import city_verification as cv
from backend.scraping.city_finder import CityLookupResult
from backend.scripts import repair_fb_city_ids as rep

QUEBEC_CARDS = ["Montréal, QC"] * 8 + ["Longueuil, QC"] * 4 + ["Laval, QC"]
FRANCE_CARDS = ["Riom, ARA"] * 8 + ["Clermont-Ferrand, ARA"] * 4


def row(pk, name, fb=None, lat=None, lon=None):
    return {"id": pk, "name": name, "fb_location_id": fb, "latitude": lat, "longitude": lon, "needs_review": False}


class TestStaticFindings(unittest.TestCase):
    def test_findings(self):
        rows = [
            row("edmonton", "Sherbrooke", None, 45.518, -73.567),
            row("1", "Montréal", None, 45.518, -73.567),
            row("2", "Longueuil", "LEQd5KcAfql2B4QA1sDM", 45.54, -73.51),
            row("3", "Saint-Hubert", "9", 45.49, -73.42),
            row("9", "Brossard", None, 45.45, -73.46),
            row("10", "Saint-Hubert", None, 45.49, -73.42),
        ]
        f = rep.static_findings(rows)
        self.assertTrue(any("non numérique" in m for m in f["edmonton"]))
        self.assertTrue(any("douteuses" in m for m in f["edmonton"]))
        self.assertTrue(any("non numérique" in m for m in f["2"]))
        self.assertTrue(any("partage son ID avec : Brossard" in m for m in f["3"]))
        self.assertTrue(any("doublon" in m for m in f["3"]))

    def test_clean_city_has_no_finding(self):
        self.assertEqual(rep.static_findings([row("1", "Granby", None, 45.4, -72.73)]), {})


class TestClassifyCurrent(unittest.TestCase):
    GAZ = {"montreal": (45.5, -73.57), "longueuil": (45.54, -73.51), "bromont": (45.32, -72.65)}

    def test_good_id_is_ok(self):
        r = row("103", "Bromont", None, 45.32, -72.65)
        status, _, score = rep.classify_current(r, "Bromont · Dans un rayon de 65 km", QUEBEC_CARDS, "QC", self.GAZ)
        self.assertEqual(status, rep.OK)
        self.assertEqual(score["part_province"], 1.0)

    def test_french_id_needs_a_lookup_even_though_the_page_says_bromont(self):
        """Mesure réelle : le bouton de lieu de l'ID français affichait « Bromont » ; seules les cartes le trahissent."""
        r = row("110035235685771", "Bromont", None, 45.32, -72.65)
        status, detail, _ = rep.classify_current(r, "Bromont · Dans un rayon de 65 km", FRANCE_CARDS, "QC", self.GAZ)
        self.assertEqual(status, rep.NEEDS_LOOKUP)

    def test_text_id_needs_a_lookup_without_any_probe(self):
        status, _, score = rep.classify_current(row("edmonton", "Sherbrooke"), "", [], "QC", self.GAZ)
        self.assertEqual((status, score), (rep.NEEDS_LOOKUP, None))

    def test_neighbouring_city_alias_is_accepted_when_proximity_is_verifiable(self):
        r = row("5", "Saint-Hubert", "8", 45.49, -73.42)
        gaz = {**self.GAZ, "saint hubert": (45.49, -73.42)}
        status, detail, _ = rep.classify_current(r, "Longueuil · Dans un rayon de 65 km", ["Longueuil, QC"] * 5, "QC", gaz)
        self.assertEqual(status, rep.ALIAS_OK)
        self.assertIn("Longueuil", detail)

    def test_alias_without_trusted_coordinates_is_ambiguous_not_accepted(self):
        r = row("5", "Saint-Hubert", "8", None, None)
        status, _, _ = rep.classify_current(r, "Longueuil · Dans un rayon de 65 km", ["Longueuil, QC"] * 5, "QC", self.GAZ)
        self.assertEqual(status, rep.AMBIGU)

    def test_thin_feed_is_indeterminate(self):
        r = row("7", "Sutton", None, 45.1, -72.6)
        status, _, _ = rep.classify_current(r, "Sutton · Dans un rayon de 65 km", ["Sutton, QC"], "QC", self.GAZ)
        self.assertEqual(status, rep.INDETERMINE)


class TestClassifyLookup(unittest.TestCase):
    def res(self, status, cid=None):
        return CityLookupResult(cid, None, "x", status, "détail", [])

    def test_new_verified_id_is_a_fix(self):
        self.assertEqual(rep.classify_lookup(row("110", "Bromont"), self.res(cv.VERIFIED, "103")), (rep.A_CORRIGER, "détail", "103"))

    def test_same_id_is_ok(self):
        self.assertEqual(rep.classify_lookup(row("103", "Bromont"), self.res(cv.VERIFIED, "103"))[0], rep.OK)

    def test_fb_location_id_counts_as_the_current_id(self):
        self.assertEqual(rep.classify_lookup(row("110", "Bromont", "103"), self.res(cv.VERIFIED, "103"))[0], rep.OK)

    def test_other_statuses_never_produce_an_id(self):
        for status, expected in ((cv.AMBIGUOUS, rep.AMBIGU), (cv.INDETERMINATE, rep.INDETERMINE), (cv.NOT_FOUND, rep.INTROUVABLE)):
            self.assertEqual(rep.classify_lookup(row("1", "X"), self.res(status)), (expected, "détail", None))


class TestPlanUpdates(unittest.TestCase):
    def results(self, **kw):
        base = {"name": "Bromont", "status": rep.A_CORRIGER, "current_id": "110", "new_id": "103"}
        return {"b": {**base, **kw}}

    def test_update_when_database_still_matches_the_report(self):
        self.assertEqual(rep.plan_updates(self.results(), {"b": row("b", "Bromont", "110")}), [("b", "update", "103")])
        # ID actuel déduit de la clé primaire quand fb_location_id est vide : ici « b » ≠ « 110 » -> la base a changé.
        self.assertEqual(rep.plan_updates(self.results(), {"b": row("b", "Bromont", None)})[0][1], "skip")
        self.assertEqual(rep.plan_updates(self.results(), {"b": row("110", "Bromont", None)}), [("b", "update", "103")])

    def test_uses_fb_location_id_over_primary_key(self):
        self.assertEqual(rep.plan_updates(self.results(), {"b": row("zzz", "Bromont", "110")})[0][1], "update")

    def test_already_applied_is_a_noop(self):
        self.assertEqual(rep.plan_updates(self.results(), {"b": row("b", "Bromont", "103")})[0][1], "noop")

    def test_database_changed_since_the_report_is_skipped(self):
        plan = rep.plan_updates(self.results(), {"b": row("b", "Bromont", "555")})
        self.assertEqual(plan[0][1], "skip")
        self.assertIn("a changé", plan[0][2])

    def test_missing_city_is_skipped(self):
        self.assertEqual(rep.plan_updates(self.results(), {})[0][1], "skip")

    def test_only_fixes_are_planned(self):
        results = {k: {"name": k, "status": s, "current_id": "1", "new_id": "2"} for k, s in
                   (("a", rep.OK), ("b", rep.AMBIGU), ("c", rep.INTROUVABLE), ("d", rep.ECHEC), ("e", rep.ALIAS_OK))}
        self.assertEqual(rep.plan_updates(results, {k: row(k, k, "1") for k in results}), [])


def _dsn():
    return os.getenv("DATABASE_URL", "postgresql://guitarhunter@localhost/guitarhunter")


def _pg_reachable():
    try:
        with psycopg.connect(_dsn(), connect_timeout=2):
            return True
    except Exception:
        return False


@unittest.skipUnless(_pg_reachable(), "Postgres non joignable via DATABASE_URL depuis cet environnement.")
class TestApplyAgainstPostgres(unittest.TestCase):
    PK_FIX, PK_STALE = "repair-test-fix", "repair-test-stale"

    def setUp(self):
        with open("backend/api/schema.sql", encoding="utf-8") as f:
            schema_sql = f.read()
        self.conn = psycopg.connect(_dsn(), row_factory=dict_row, autocommit=True)
        self.conn.execute(schema_sql)
        self._cleanup()
        self.conn.execute("INSERT INTO cities (id, name, needs_review) VALUES (%s, 'Bromont test', true)", (self.PK_FIX,))
        self.conn.execute("INSERT INTO cities (id, name, fb_location_id) VALUES (%s, 'Beloeil test', '999')", (self.PK_STALE,))
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._cleanup()
        self.conn.close()
        self.tmp.cleanup()

    def _cleanup(self):
        self.conn.execute("DELETE FROM cities WHERE id LIKE 'repair-test-%'")

    def _db_rows(self):
        return {r["id"]: r for r in self.conn.execute(
            "SELECT id, name, latitude, longitude, fb_location_id, needs_review, created_by FROM cities WHERE id LIKE 'repair-test-%'").fetchall()}

    def _results(self):
        return {
            self.PK_FIX: {"name": "Bromont test", "status": rep.A_CORRIGER, "current_id": self.PK_FIX, "new_id": "103"},
            self.PK_STALE: {"name": "Beloeil test", "status": rep.A_CORRIGER, "current_id": "111", "new_id": "104"},
        }

    def test_apply_updates_only_the_fb_location_id_and_is_idempotent(self):
        results, rows = self._results(), self._db_rows()
        plan = rep.plan_updates(results, rows)
        done = rep.apply_plan(self.conn, plan, results, rows, self.tmp.name)
        self.assertEqual(done, 1)  # Beloeil : la base (999) a changé depuis le rapport (111) -> ignorée

        after = self._db_rows()
        self.assertEqual(after[self.PK_FIX]["fb_location_id"], "103")
        self.assertEqual(after[self.PK_FIX]["id"], self.PK_FIX)            # clé primaire intacte
        self.assertFalse(after[self.PK_FIX]["needs_review"])
        self.assertEqual(after[self.PK_STALE]["fb_location_id"], "999")    # non touchée

        backups = [f for f in os.listdir(self.tmp.name) if f.startswith("cities_backup_")]
        self.assertEqual(len(backups), 1)
        with open(os.path.join(self.tmp.name, backups[0]), encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual([r["id"] for r in saved], [self.PK_FIX])
        self.assertIsNone(saved[0]["fb_location_id"])                      # état AVANT écriture

        # Seconde application : plus rien à faire.
        plan2 = rep.plan_updates(results, self._db_rows())
        self.assertEqual({p[0]: p[1] for p in plan2}, {self.PK_FIX: "noop", self.PK_STALE: "skip"})
        self.assertEqual(rep.apply_plan(self.conn, plan2, results, self._db_rows(), self.tmp.name), 0)

    def test_user_preferences_survive_the_correction(self):
        self.conn.execute("INSERT INTO users (uid) VALUES ('repair-test-user') ON CONFLICT DO NOTHING")
        self.conn.execute("INSERT INTO user_city_prefs (user_id, city_id, active) VALUES ('repair-test-user', %s, true)", (self.PK_FIX,))
        try:
            results, rows = self._results(), self._db_rows()
            rep.apply_plan(self.conn, rep.plan_updates(results, rows), results, rows, self.tmp.name)
            pref = self.conn.execute("SELECT active FROM user_city_prefs WHERE user_id='repair-test-user' AND city_id=%s", (self.PK_FIX,)).fetchone()
            self.assertTrue(pref["active"])
        finally:
            self.conn.execute("DELETE FROM users WHERE uid = 'repair-test-user'")


class _FakeDriver:
    """Faux Facebook : `probes` {id: (libellé du bouton de lieu, cartes)}, `suggestions` {nom: [(libellé, id)]}."""

    def __init__(self, probes, suggestions):
        self.probes, self.suggestions, self.probed = probes, suggestions, []

    def probe(self, city_id):
        self.probed.append(city_id)
        landed, cards = self.probes[city_id]
        from backend.scraping.city_finder import ProbeResult
        return ProbeResult(cards, landed)

    def list_suggestions(self, name):
        return [label for label, _ in self.suggestions.get(name, [])]

    def select(self, name, label, occurrence=0):
        from backend.scraping.city_finder import SelectResult
        city_id = [i for l, i in self.suggestions[name] if l == label][occurrence]
        return SelectResult(city_id, city_id, True, None)


@unittest.skipUnless(_pg_reachable(), "Postgres non joignable via DATABASE_URL depuis cet environnement.")
class TestRunReportWithFakeFacebook(unittest.TestCase):
    """Colle de `run_report` : lecture des villes, sonde, recherche, rapport JSON et reprise — sans Facebook."""

    def setUp(self):
        from argparse import Namespace
        with open("backend/api/schema.sql", encoding="utf-8") as f:
            schema_sql = f.read()
        self.conn = psycopg.connect(_dsn(), row_factory=dict_row, autocommit=True)
        self.conn.execute(schema_sql)
        self._cleanup()
        for pk, name in (("rtest-110", "Bromont rtest"), ("rtest-777", "Granby rtest"), ("texte-rtest", "Sherbrooke rtest")):
            fb = {"rtest-110": "110", "rtest-777": "777"}.get(pk)
            self.conn.execute("INSERT INTO cities (id, name, fb_location_id) VALUES (%s, %s, %s)", (pk, name, fb))
        self.tmp = tempfile.TemporaryDirectory()
        self.report = os.path.join(self.tmp.name, "rapport.json")
        self.args = Namespace(user_id=None, all_catalog=True, only="Bromont rtest,Granby rtest,Sherbrooke rtest",
                              anchors_only=False, max_cities=None, report=self.report, redo=False,
                              province="QC", region="Québec", pause_min=0, pause_max=0)
        self.driver = _FakeDriver(
            probes={
                "110": ("Bromont rtest · Dans un rayon de 65 km", FRANCE_CARDS),   # l'ID français : la page dit « Bromont »
                "103": ("Bromont rtest · Dans un rayon de 65 km", QUEBEC_CARDS),
                "777": ("Granby rtest · Dans un rayon de 65 km", QUEBEC_CARDS),
            },
            suggestions={
                "Bromont rtest": [("Bromont rtest | Ville", "103")],
                "Sherbrooke rtest": [],   # Facebook ne propose rien -> INTROUVABLE
            },
        )

    def tearDown(self):
        self._cleanup()
        self.conn.close()
        self.tmp.cleanup()

    def _cleanup(self):
        self.conn.execute("DELETE FROM cities WHERE name LIKE '% rtest' OR id LIKE '%rtest%'")

    def _run(self):
        from unittest.mock import patch, MagicMock
        with patch("backend.scraping.core.FacebookScraper", MagicMock()), \
             patch("backend.scraping.city_finder.PlaywrightCityDriver", return_value=self.driver), \
             patch("backend.scripts.repair_fb_city_ids.time.sleep"):
            return rep.run_report(self.args)

    def _results(self):
        with open(self.report, encoding="utf-8") as f:
            return json.load(f)["results"]

    def test_report_classifies_each_city_and_never_writes_to_the_database(self):
        self.assertEqual(self._run(), 0)
        r = self._results()
        self.assertEqual(r["rtest-110"]["status"], rep.A_CORRIGER)
        self.assertEqual((r["rtest-110"]["current_id"], r["rtest-110"]["new_id"]), ("110", "103"))
        self.assertEqual(r["rtest-777"]["status"], rep.OK)
        self.assertEqual(r["texte-rtest"]["status"], rep.INTROUVABLE)   # ID texte -> recherche -> aucune suggestion
        self.assertNotIn("texte-rtest", self.driver.probed)             # un ID non numérique n'est jamais sondé
        self.assertEqual(r["rtest-110"]["places"][0][0], "Riom, ARA")   # noms de lieux seulement
        after = {x["id"]: x["fb_location_id"] for x in self.conn.execute("SELECT id, fb_location_id FROM cities WHERE name LIKE '% rtest'").fetchall()}
        self.assertEqual(after, {"rtest-110": "110", "rtest-777": "777", "texte-rtest": None})  # inchangé

    def test_second_run_resumes_without_reprobing_finished_cities(self):
        self._run()
        self.driver.probed.clear()
        self.assertEqual(self._run(), 0)
        self.assertEqual(self.driver.probed, [])
        self.args.redo = True
        self._run()
        self.assertIn("777", self.driver.probed)  # (sonde par ID Facebook, pas par clé primaire)

    def test_max_cities_limits_the_run_and_the_report_resumes_the_rest(self):
        self.args.max_cities = 1
        self._run()
        self.assertEqual(len(self._results()), 1)
        self.args.max_cities = None
        self._run()
        self.assertEqual(len(self._results()), 3)

    def test_blocked_facebook_stops_everything_but_keeps_what_was_done(self):
        from backend.scraping.city_finder import FacebookBlocked
        original = self.driver.probe

        def probe(city_id):
            if city_id == "777":
                raise FacebookBlocked("login")
            return original(city_id)
        self.driver.probe = probe
        self.args.only = "Granby rtest,Bromont rtest"
        code = self._run()
        self.assertEqual(code, 2)
        self.assertNotIn("rtest-777", self._results())

    def test_unknown_city_filter_returns_an_error_code(self):
        self.args.only = "Ville inexistante"
        self.assertEqual(self._run(), 1)


if __name__ == "__main__":
    unittest.main()
