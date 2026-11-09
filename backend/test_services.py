"""Tests de backend/services.py : planificateur par bot (R-2-1) et comparaison de config (R-9-10)."""
import datetime
import logging
import unittest

from backend.services import ConfigManager, TaskScheduler


def _jobs(sched, tag=None):
    return sched.jobs(tag)


def _make_due(sched):
    """Rend tous les jobs du planificateur échus."""
    for job in sched.jobs():
        job.next_run = datetime.datetime.now() - datetime.timedelta(seconds=1)


class FakeRepo:
    def __init__(self, config):
        self.config = config

    def get_user_config(self):
        return self.config

    def get_pending_commands(self):
        return []


class TaskSchedulerTest(unittest.TestCase):
    def _make(self, freq=60, purge=True):
        return TaskScheduler(lambda: None, lambda: None, freq, (lambda: None) if purge else None)

    def test_planificateurs_independants(self):
        a, b = self._make(), self._make()
        self.assertFalse(set(map(id, a.jobs())) & set(map(id, b.jobs())))
        self.assertEqual(len(_jobs(a)), 3)
        self.assertEqual(len(_jobs(b)), 3)

    def test_changer_la_frequence_de_a_laisse_b_intact(self):
        a, b = self._make(60), self._make(60)
        job_b = _jobs(b, 'scan')[0]
        a.update_scan_frequency(30)
        self.assertEqual(len(_jobs(a, 'scan')), 1)
        self.assertEqual(_jobs(b, 'scan'), [job_b])

    def test_meme_frequence_ne_replanifie_pas(self):
        a = self._make(60)
        job = _jobs(a, 'scan')[0]
        a.update_scan_frequency(60)
        self.assertEqual(_jobs(a, 'scan'), [job])

    def test_close_retire_les_jobs(self):
        a, b = self._make(), self._make()
        a.close()
        self.assertEqual(_jobs(a), [])
        self.assertEqual(len(_jobs(b)), 3)

    def test_run_pending_n_execute_que_ses_propres_jobs(self):
        calls = []
        a = TaskScheduler(lambda: calls.append("a"), lambda: None, 60)
        b = TaskScheduler(lambda: calls.append("b"), lambda: None, 60)
        _make_due(a)
        _make_due(b)
        b.run_pending()
        self.assertEqual(calls, ["b"])
        a.run_pending()
        self.assertEqual(calls, ["b", "a"])

    def test_exception_d_un_job_ne_remonte_pas_et_replanifie(self):
        def boom():
            raise RuntimeError("echec")
        log = logging.getLogger("test_services_boom")
        a = TaskScheduler(boom, lambda: None, 60, bot_logger=log)
        _make_due(a)
        with self.assertLogs(log, level="ERROR"):
            a.run_pending()  # ne doit pas lever
        job = _jobs(a, 'scan')[0]
        self.assertGreater(job.next_run, datetime.datetime.now())  # replanifié, plus en retard

    def test_sans_purge(self):
        self.assertEqual(len(_jobs(self._make(purge=False))), 2)


class SyncWithDbTest(unittest.TestCase):
    def test_config_stable_signalee_une_seule_fois(self):
        # Valeurs par défaut du bot que la config stockée ne contient pas (R-9-10).
        cm = ConfigManager(FakeRepo({'scanConfig': {'frequency': 60}}),
                           {'frequency': 60, 'kijiji_enabled': True})
        self.assertFalse(cm.sync_with_db(initial=True).config_changed)
        self.assertFalse(cm.sync_with_db().config_changed)

    def test_vrai_changement_de_frequence(self):
        repo = FakeRepo({'scanConfig': {'frequency': 60}})
        cm = ConfigManager(repo, {'frequency': 60, 'kijiji_enabled': True})
        cm.sync_with_db(initial=True)
        repo.config = {'scanConfig': {'frequency': 30}}
        result = cm.sync_with_db()
        self.assertTrue(result.config_changed)
        self.assertEqual(result.new_scan_frequency, 30)
        self.assertTrue(cm.scan_config['kijiji_enabled'])
        self.assertFalse(cm.sync_with_db().config_changed)

    def test_changement_sans_frequence(self):
        repo = FakeRepo({'scanConfig': {'max_price': 100}})
        cm = ConfigManager(repo, {'frequency': 60})
        result = cm.sync_with_db()
        self.assertTrue(result.config_changed)
        self.assertIsNone(result.new_scan_frequency)


if __name__ == '__main__':
    unittest.main()
