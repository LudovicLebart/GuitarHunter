"""Diagnostic `GET /deals/index?perf=1` : réservé aux administrateurs (claim `admin`), mesures lisibles par les origines
autorisées seulement. Même principe que les autres tests d'API : vraie base Postgres, se saute proprement si injoignable."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.auth import get_current_uid
from backend.api.db import DATABASE_URL
from backend.api.main import ALLOWED_ORIGINS, app
from backend.api.test_deals_api import _pg_reachable

UID = "test-uid-perf-1"


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestPerfDiagnostic(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[get_current_uid] = lambda: UID
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()

    def _get(self, admin, origin=None):
        headers = {"Origin": origin} if origin else {}
        with patch("backend.api.main.is_admin_uid", return_value=admin):
            return self.client.get("/deals/index", params={"perf": 1}, headers=headers)

    def test_a_non_admin_gets_the_normal_response_without_measurements(self):
        resp = self._get(admin=False, origin=ALLOWED_ORIGINS[0])
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIsInstance(resp.json(), list)
        self.assertNotIn("server-timing", resp.headers)            # ?perf=1 ignoré en silence, jamais une erreur

    def test_an_admin_gets_the_measurements(self):
        resp = self._get(admin=True, origin=ALLOWED_ORIGINS[0])
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn("sql;dur=", resp.headers["server-timing"])
        self.assertEqual(resp.headers["timing-allow-origin"], ALLOWED_ORIGINS[0])

    def test_timing_is_exposed_only_to_the_allowed_origins(self):
        self.assertEqual(self._get(admin=True, origin=ALLOWED_ORIGINS[1]).headers["timing-allow-origin"], ALLOWED_ORIGINS[1])
        for origin in ("https://exemple-hostile.test", None):
            resp = self._get(admin=True, origin=origin)
            self.assertIn("server-timing", resp.headers)
            self.assertNotIn("timing-allow-origin", resp.headers)

    def test_without_the_parameter_nothing_changes_for_anyone(self):
        with patch("backend.api.main.is_admin_uid", return_value=True) as check:
            resp = self.client.get("/deals/index")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("server-timing", resp.headers)
        check.assert_not_called()                                   # pas de requête Firebase hors diagnostic


if __name__ == "__main__":
    unittest.main()
