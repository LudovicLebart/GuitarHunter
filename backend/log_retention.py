"""
Maintenance quotidienne de l'archive de logs locale (backend/logging_config.py,
dossier `logs/`, un fichier par utilisateur, rotation quotidienne UTC) :
compresse en .gz les fichiers de plus de 30 jours, supprime ceux de plus d'un an.

Job global (singleton, main.py, boucle watchdog) — indépendant des logs
par-utilisateur, pas besoin du logger `bot.{user_id[:8]}` (voir piège logger,
CLAUDE.md) puisqu'il ne s'agit pas d'une action attribuable à un utilisateur.
"""
import os
import re
import gzip
import shutil
import logging
from datetime import datetime, timedelta, timezone

from backend.logging_config import LOG_DIR

logger = logging.getLogger(__name__)

COMPRESS_AFTER_DAYS = 30
DELETE_AFTER_DAYS = 365

# TimedRotatingFileHandler(when='midnight') suffixe les fichiers tournés en
# <basename>.YYYY-MM-DD — seul ce suffixe identifie un fichier "clos" (le fichier
# actif du jour n'en a pas et n'est donc jamais touché ici).
ROTATED_SUFFIX_RE = re.compile(r'\.(\d{4}-\d{2}-\d{2})$')


def _file_date(filename):
    """Date du suffixe de rotation, ou None si le fichier n'en a pas (fichier
    actif du jour, ou nom inattendu)."""
    name = filename[:-3] if filename.endswith('.gz') else filename
    m = ROTATED_SUFFIX_RE.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def run_log_retention_job():
    """Lecture seule sur le reste du système — ne touche qu'à backend/logging_config.LOG_DIR."""
    if not os.path.isdir(LOG_DIR):
        return

    now = datetime.now(timezone.utc)
    compress_cutoff = now - timedelta(days=COMPRESS_AFTER_DAYS)
    delete_cutoff = now - timedelta(days=DELETE_AFTER_DAYS)

    compressed = 0
    deleted = 0
    for filename in os.listdir(LOG_DIR):
        path = os.path.join(LOG_DIR, filename)
        if not os.path.isfile(path):
            continue
        file_date = _file_date(filename)
        if file_date is None:
            continue  # fichier actif du jour, ou nom inattendu — on n'y touche pas

        if file_date < delete_cutoff:
            try:
                os.remove(path)
                deleted += 1
            except OSError as e:
                logger.error(f"[log_retention] Suppression échouée pour {filename} : {e}")
            continue

        if file_date < compress_cutoff and not filename.endswith('.gz'):
            gz_path = path + '.gz'
            try:
                with open(path, 'rb') as f_in, gzip.open(gz_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
                os.remove(path)
                compressed += 1
            except OSError as e:
                logger.error(f"[log_retention] Compression échouée pour {filename} : {e}")

    if compressed or deleted:
        logger.info(f"[log_retention] {compressed} fichier(s) compressé(s), {deleted} supprimé(s).")


# --- Table Postgres `logs` : fenêtre glissante + archive interrogeable (2026-10-02) ---------
# `logs` garde PG_LOGS_LIVE_DAYS jours (ce que lit le LogViewer) ; le reste est déplacé dans
# `logs_archive`, elle-même purgée après PG_LOGS_ARCHIVE_MONTHS mois (alignée sur la rétention
# d'un an des fichiers disque ci-dessus).
PG_LOGS_LIVE_DAYS = 30
PG_LOGS_ARCHIVE_MONTHS = 12
PG_LOGS_BATCH_SIZE = 10_000

_ARCHIVE_BATCH_SQL = """
    WITH moved AS (
        DELETE FROM logs WHERE id IN (
            SELECT id FROM logs WHERE created_at < now() - make_interval(days => %s)
            ORDER BY id LIMIT %s)
        RETURNING id, user_id, message, level, created_at)
    INSERT INTO logs_archive (id, user_id, message, level, created_at)
    SELECT id, user_id, message, level, created_at FROM moved
    ON CONFLICT (id) DO NOTHING
"""

_PURGE_BATCH_SQL = """
    DELETE FROM logs_archive WHERE id IN (
        SELECT id FROM logs_archive WHERE created_at < now() - make_interval(months => %s)
        ORDER BY id LIMIT %s)
"""


def run_pg_log_archive_job(pg_pool, batch_size=PG_LOGS_BATCH_SIZE):
    """Déplace les logs de plus de PG_LOGS_LIVE_DAYS jours de `logs` vers `logs_archive`, puis
    purge l'archive au-delà de PG_LOGS_ARCHIVE_MONTHS mois. Retourne (déplacés, purgés).

    Par lots : le premier passage absorbe l'arriéré accumulé depuis la migration sans long
    verrou. Le déplacement est UNE seule instruction (DELETE ... RETURNING alimentant l'INSERT) —
    si elle échoue, rien n'est retiré de `logs`, aucune perte possible. Ne lève jamais : un
    échec est loggué et retenté au prochain passage, sans bloquer le watchdog de main.py."""
    moved = purged = 0
    try:
        while True:
            with pg_pool.connection() as conn:
                n = conn.execute(_ARCHIVE_BATCH_SQL, (PG_LOGS_LIVE_DAYS, batch_size)).rowcount
            moved += n
            if n < batch_size:
                break
        while True:
            with pg_pool.connection() as conn:
                n = conn.execute(_PURGE_BATCH_SQL, (PG_LOGS_ARCHIVE_MONTHS, batch_size)).rowcount
            purged += n
            if n < batch_size:
                break
    except Exception as e:
        logger.error(f"[log_retention] Archivage des logs Postgres échoué : {e}", exc_info=True)
    if moved or purged:
        logger.info(f"[log_retention] Logs Postgres : {moved} ligne(s) archivée(s), {purged} purgée(s) de l'archive.")
    return moved, purged
