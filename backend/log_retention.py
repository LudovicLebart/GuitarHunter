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
