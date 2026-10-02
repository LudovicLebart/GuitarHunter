"""Tests d'intégration de `run_pg_log_archive_job` (fenêtre glissante de 30 jours + archive
interrogeable). Vraie base Postgres, pas de mocks ; se saute proprement si aucun Postgres n'est
joignable (même principe que backend/api/test_logs_api.py)."""
import unittest

from psycopg_pool import ConnectionPool

from backend.api.db import DATABASE_URL
from backend.api.test_deals_api import _pg_reachable
from backend.log_retention import run_pg_log_archive_job
from backend.pg_db import SCHEMA_PATH

UID = "test-uid-log-archive"
OTHER_UID = "test-uid-log-archive-2"


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestLogArchiveJob(unittest.TestCase):
    def setUp(self):
        self.pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=2, open=True)
        with self.pool.connection() as conn:
            conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
            for uid in (UID, OTHER_UID):
                conn.execute("INSERT INTO users (uid) VALUES (%s) ON CONFLICT (uid) DO NOTHING", (uid,))
            conn.execute("DELETE FROM logs WHERE user_id = ANY(%s)", ([UID, OTHER_UID],))
            conn.execute("DELETE FROM logs_archive WHERE user_id = ANY(%s)", ([UID, OTHER_UID],))

    def tearDown(self):
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM users WHERE uid = ANY(%s)", ([UID, OTHER_UID],))  # cascade logs + archive
        self.pool.close()

    def _insert_log(self, table, message, age, uid=UID):
        """`age` : fragment SQL d'intervalle, ex. "40 days"."""
        with self.pool.connection() as conn:
            if table == "logs":
                conn.execute(
                    f"INSERT INTO logs (user_id, message, created_at) VALUES (%s, %s, now() - interval '{age}')",
                    (uid, message),
                )
            else:
                conn.execute(
                    f"INSERT INTO logs_archive (id, user_id, message, created_at) "
                    f"VALUES (nextval('logs_id_seq'), %s, %s, now() - interval '{age}')",
                    (uid, message),
                )

    def _messages(self, table):
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT message FROM {table} WHERE user_id = ANY(%s) ORDER BY id", ([UID, OTHER_UID],),
            ).fetchall()
        return [r[0] for r in rows]

    def test_moves_old_logs_and_keeps_recent_ones(self):
        self._insert_log("logs", "old-40d", "40 days")
        self._insert_log("logs", "recent-20d", "20 days")
        self._insert_log("logs", "fresh", "1 minute")

        moved, purged = run_pg_log_archive_job(self.pool)

        self.assertEqual((moved, purged), (1, 0))
        self.assertEqual(self._messages("logs"), ["recent-20d", "fresh"])
        self.assertEqual(self._messages("logs_archive"), ["old-40d"])

    def test_purges_archive_older_than_12_months_only(self):
        self._insert_log("logs_archive", "archived-400d", "400 days")
        self._insert_log("logs_archive", "archived-60d", "60 days")

        moved, purged = run_pg_log_archive_job(self.pool)

        self.assertEqual((moved, purged), (0, 1))
        self.assertEqual(self._messages("logs_archive"), ["archived-60d"])

    def test_no_row_lost_or_duplicated_across_several_batches(self):
        for i in range(7):
            self._insert_log("logs", f"old-{i}", "40 days", uid=UID if i % 2 else OTHER_UID)
        before = sorted(self._messages("logs"))

        moved, _ = run_pg_log_archive_job(self.pool, batch_size=3)  # 3 + 3 + 1 : plusieurs lots

        self.assertEqual(moved, 7)
        self.assertEqual(self._messages("logs"), [])
        self.assertEqual(sorted(self._messages("logs_archive")), before)

    def test_is_idempotent(self):
        self._insert_log("logs", "old-40d", "40 days")
        run_pg_log_archive_job(self.pool)

        moved, purged = run_pg_log_archive_job(self.pool)

        self.assertEqual((moved, purged), (0, 0))
        self.assertEqual(self._messages("logs_archive"), ["old-40d"])

    def test_never_raises_on_database_error(self):
        self.pool.close()  # pool fermé : le job doit loguer l'erreur, pas planter le watchdog
        self.assertEqual(run_pg_log_archive_job(self.pool), (0, 0))
        self.pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=2, open=True)  # pour tearDown


if __name__ == "__main__":
    unittest.main()
