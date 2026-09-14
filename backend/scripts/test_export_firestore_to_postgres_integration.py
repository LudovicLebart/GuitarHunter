"""Test d'intégration de la partie Postgres de export_firestore_to_postgres.py, contre un vrai
Postgres local (même principe que backend/api/test_*.py : pas de mock côté Postgres, se saute
proprement si injoignable). Le côté Firestore, lui, EST simulé ici (`_FakeDoc`/`_FakeCollection`
ci-dessous) — cette session n'a aucun accès à un Firestore réel (voir docstring en tête de
export_firestore_to_postgres.py) ; les tests purs de mapping (sans aucune notion de Postgres)
sont dans test_export_firestore_to_postgres.py.

Objectif : vérifier ce que les tests purs ne peuvent pas attraper — que le SQL généré s'exécute
réellement sans erreur (noms de colonnes, types, ordre des FK), que la résolution
chat -> proposed_by_message_id fonctionne de bout en bout, et que relancer l'export sur les mêmes
données ne duplique rien (idempotence).

Chaque test fait tout (pool, migration, assertions, nettoyage) dans un SEUL `asyncio.run()` —
un pool asyncpg est lié à la boucle qui l'a créé ; en créer un dans un `asyncio.run()` puis le
réutiliser depuis un autre (ex: setUp/tearDown séparés) casse avec "Event loop is closed" (piège
réel rencontré en écrivant ce fichier)."""
import asyncio
import unittest
from datetime import datetime

import asyncpg

from backend.api.db import DATABASE_URL, SCHEMA_PATH, _register_json_codecs
from backend.scripts.export_firestore_to_postgres import (
    MigrationReport, _ensure_city_exists, _migrate_deal, _upsert, map_city,
)


def _pg_reachable() -> bool:
    async def _check():
        conn = await asyncpg.connect(DATABASE_URL, timeout=2)
        await conn.close()
    try:
        asyncio.run(_check())
        return True
    except Exception:
        return False


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def stream(self):
        return iter(self._docs)

    def order_by(self, *_args, **_kwargs):
        return self

    def document(self, doc_id):
        for d in self._docs:
            if d.id == doc_id:
                return d
        return _FakeDoc(doc_id, {})


class _FakeDoc:
    def __init__(self, doc_id, data, children=None):
        self.id = doc_id
        self._data = data
        self._children = children or {}
        self.reference = self

    def to_dict(self):
        return self._data

    def collection(self, name):
        return _FakeCollection(self._children.get(name, []))


def _build_fake_deal_doc(deal_id: str):
    chat_docs = [
        _FakeDoc("fs-msg-1", {
            "role": "user", "parts": [{"text": "salut"}], "displayText": "salut",
            "createdAt": datetime(2026, 9, 1, 10, 0, 0),
        }),
        _FakeDoc("fs-msg-2", {
            "role": "model", "parts": [{"text": "voici une proposition"}],
            "displayText": "voici une proposition",
            "createdAt": datetime(2026, 9, 1, 10, 1, 0),
            "restorationProposals": [{"label": "Refret"}],
        }),
    ]
    resto_docs = [
        _FakeDoc("fs-item-1", {
            "label": "Refret", "category": "frettes", "estimatedCost": 150.0,
            "proposedByMessageId": "fs-msg-2", "order": 0,
            "createdAt": datetime(2026, 9, 1, 10, 2, 0),
        }),
    ]
    return _FakeDoc(deal_id, {
        "title": "Parlor satinée", "price": 450,
        "aiAnalysis": {"verdict": "GOOD_DEAL", "deal_score": 8},
    }, children={"chat": chat_docs, "restorationPlan": resto_docs})


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestMigrateDealAgainstRealPostgres(unittest.TestCase):
    UID = "test-uid-export-1"
    DEAL_ID = "export-deal-1"

    def test_migrate_deal_writes_deal_chat_and_resolves_message_id(self):
        async def _run():
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2, init=_register_json_codecs)
            try:
                async with pool.acquire() as conn:
                    await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
                    await conn.execute("INSERT INTO users (uid) VALUES ($1) ON CONFLICT (uid) DO NOTHING", self.UID)

                deal_doc = _build_fake_deal_doc(self.DEAL_ID)
                user_ref = _FakeDoc("user-ref", {}, children={"guitar_deals": [deal_doc]})
                report = MigrationReport()
                await _migrate_deal(user_ref, self.UID, self.DEAL_ID, deal_doc.to_dict(), pool, report)

                async with pool.acquire() as conn:
                    deal_row = await conn.fetchrow("SELECT * FROM guitar_deals WHERE id = $1", self.DEAL_ID)
                    self.assertIsNotNone(deal_row)
                    self.assertEqual(deal_row["title"], "Parlor satinée")
                    self.assertEqual(deal_row["verdict"], "GOOD_DEAL")
                    self.assertEqual(deal_row["deal_score"], 8)

                    chat_rows = await conn.fetch(
                        "SELECT * FROM deal_chat WHERE deal_id = $1 ORDER BY created_at ASC", self.DEAL_ID
                    )
                    self.assertEqual(len(chat_rows), 2)
                    self.assertEqual(chat_rows[0]["display_text"], "salut")

                    resto_rows = await conn.fetch(
                        "SELECT * FROM restoration_plan_items WHERE deal_id = $1", self.DEAL_ID
                    )
                    self.assertEqual(len(resto_rows), 1)
                    # Le point critique : proposed_by_message_id doit être le BIGSERIAL Postgres
                    # du 2e message (fs-msg-2), PAS la chaîne Firestore d'origine.
                    second_message_pg_id = chat_rows[1]["id"]
                    self.assertEqual(resto_rows[0]["proposed_by_message_id"], second_message_pg_id)

                    await conn.execute("DELETE FROM guitar_deals WHERE id = $1", self.DEAL_ID)
                    await conn.execute("DELETE FROM users WHERE uid = $1", self.UID)
            finally:
                await pool.close()

        asyncio.run(_run())

    def test_rerunning_migrate_deal_is_idempotent(self):
        async def _run():
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2, init=_register_json_codecs)
            try:
                async with pool.acquire() as conn:
                    await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
                    await conn.execute("INSERT INTO users (uid) VALUES ($1) ON CONFLICT (uid) DO NOTHING", self.UID)

                deal_doc = _build_fake_deal_doc(self.DEAL_ID)
                user_ref = _FakeDoc("user-ref", {}, children={"guitar_deals": [deal_doc]})

                await _migrate_deal(user_ref, self.UID, self.DEAL_ID, deal_doc.to_dict(), pool, MigrationReport())
                await _migrate_deal(user_ref, self.UID, self.DEAL_ID, deal_doc.to_dict(), pool, MigrationReport())

                async with pool.acquire() as conn:
                    deal_count = await conn.fetchval("SELECT count(*) FROM guitar_deals WHERE id = $1", self.DEAL_ID)
                    self.assertEqual(deal_count, 1)
                    chat_count = await conn.fetchval("SELECT count(*) FROM deal_chat WHERE deal_id = $1", self.DEAL_ID)
                    self.assertEqual(chat_count, 2)
                    resto_count = await conn.fetchval(
                        "SELECT count(*) FROM restoration_plan_items WHERE deal_id = $1", self.DEAL_ID
                    )
                    self.assertEqual(resto_count, 1)

                    await conn.execute("DELETE FROM guitar_deals WHERE id = $1", self.DEAL_ID)
                    await conn.execute("DELETE FROM users WHERE uid = $1", self.UID)
            finally:
                await pool.close()

        asyncio.run(_run())

    def test_dangling_proposed_by_message_id_is_reported_and_left_null(self):
        async def _run():
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2, init=_register_json_codecs)
            try:
                async with pool.acquire() as conn:
                    await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
                    await conn.execute("INSERT INTO users (uid) VALUES ($1) ON CONFLICT (uid) DO NOTHING", self.UID)

                resto_docs = [_FakeDoc("fs-item-orphan", {
                    "label": "x", "proposedByMessageId": "fs-msg-does-not-exist",
                    "createdAt": datetime(2026, 9, 1),
                })]
                deal_doc = _FakeDoc(self.DEAL_ID, {"title": "x"}, children={"chat": [], "restorationPlan": resto_docs})
                user_ref = _FakeDoc("user-ref", {}, children={"guitar_deals": [deal_doc]})
                report = MigrationReport()
                await _migrate_deal(user_ref, self.UID, self.DEAL_ID, deal_doc.to_dict(), pool, report)

                self.assertEqual(report.dangling_proposed_by, [(self.DEAL_ID, "fs-msg-does-not-exist")])

                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT proposed_by_message_id FROM restoration_plan_items WHERE deal_id = $1", self.DEAL_ID
                    )
                    self.assertIsNone(row["proposed_by_message_id"])

                    await conn.execute("DELETE FROM guitar_deals WHERE id = $1", self.DEAL_ID)
                    await conn.execute("DELETE FROM users WHERE uid = $1", self.UID)
            finally:
                await pool.close()

        asyncio.run(_run())


@unittest.skipUnless(_pg_reachable(), f"Postgres non joignable via DATABASE_URL ({DATABASE_URL}) depuis cet environnement.")
class TestEnsureCityExists(unittest.TestCase):
    CITY_ID = "test-city-legacy-1"

    def test_creates_minimal_city_from_legacy_pref_doc_when_missing_from_catalog(self):
        async def _run():
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2, init=_register_json_codecs)
            try:
                async with pool.acquire() as conn:
                    await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
                    report = MigrationReport()
                    await _ensure_city_exists(conn, self.CITY_ID, {"name": "Ville Legacy", "latitude": 1.0, "longitude": 2.0}, report)
                    self.assertEqual(report.counts["legacy_cities_created"], 1)

                    row = await conn.fetchrow("SELECT * FROM cities WHERE id = $1", self.CITY_ID)
                    self.assertEqual(row["name"], "Ville Legacy")

                    await conn.execute("DELETE FROM cities WHERE id = $1", self.CITY_ID)
            finally:
                await pool.close()

        asyncio.run(_run())

    def test_does_nothing_when_city_already_in_catalog(self):
        async def _run():
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2, init=_register_json_codecs)
            try:
                async with pool.acquire() as conn:
                    await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
                    official_row = map_city(self.CITY_ID, {"name": "Officielle"})
                    await _upsert(conn, "cities", list(official_row.keys()), official_row, "id")

                    report = MigrationReport()
                    await _ensure_city_exists(conn, self.CITY_ID, {"name": "Ne devrait pas écraser"}, report)
                    self.assertEqual(report.counts["legacy_cities_created"], 0)

                    row = await conn.fetchrow("SELECT name FROM cities WHERE id = $1", self.CITY_ID)
                    self.assertEqual(row["name"], "Officielle")

                    await conn.execute("DELETE FROM cities WHERE id = $1", self.CITY_ID)
            finally:
                await pool.close()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
