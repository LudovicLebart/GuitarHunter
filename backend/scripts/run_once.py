"""
Script "one-shot" exécuté automatiquement à CHAQUE déploiement
(.github/workflows/deploy.yml, job `deploy`, étape "Script de maintenance ponctuel") —
ce job est le seul contexte où le serveur a déjà les credentials Firebase en place
(.env / backend/config/serviceAccountKey.json écrits juste avant dans le même job).

Sert à exécuter une action ponctuelle en production (ex: script de migration) depuis un
environnement de dev qui n'y a lui-même aucun accès à Firestore.

⚠️ NO-OP PAR DÉFAUT (ACTIVE = False). Protocole d'usage :
  1. Passer ACTIVE à True et écrire l'action dans run().
  2. Commit + push (déclenche le déploiement, qui exécute run() sur le serveur).
  3. Vérifier le résultat via les logs de l'étape dans l'onglet GitHub Actions (ou dans l'app).
  4. Repasser IMMÉDIATEMENT ACTIVE à False, dans un commit séparé — sinon l'action se
     répète à CHAQUE déploiement futur.

Le job `deploy` se déclenche sur push `master` ET `dev` — une action ici s'exécute donc
généralement deux fois de suite. Écrire uniquement des actions idempotentes (rejouables
sans effet de bord cumulatif). Un échec ici n'interrompt pas le reste du déploiement
(voir deploy.yml : l'étape est volontairement non bloquante).
"""
import sys
import os
import logging

# Comme rebuild_index.py : nécessaire pour que `from backend.scripts... import ...` résolve,
# `python3 backend/scripts/run_once.py` n'ajoutant que le dossier du script (pas la racine du
# repo) à sys.path. Le job `deploy` exécute toujours ce script depuis la racine (~/GuitareHunter).
sys.path.insert(0, os.getcwd())

ACTIVE = False


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-10 (suite) : l'utilisateur a 5978 annonces Firestore — trop pour tenir dans la fenêtre
    de 10 min du pipeline de déploiement en un seul essai (run #439, tué par mon propre timeout de
    300s). Décidé avec l'utilisateur : valider avec les 2414 déjà migrées (run #440) plutôt que
    d'augmenter le timeout CI partagé. Cette étape compare un ÉCHANTILLON de ces 2414 annonces déjà
    en Postgres, champ par champ, contre le document Firestore correspondant — PAS
    `compare_firestore_postgres.py` tel quel (il échantillonne dans les 5978, la plupart absentes
    de Postgres pour l'instant, ce qui noierait le signal utile sous des "absences" attendues).
    Réutilise `map_deal` du script d'export (même mapping, pas dupliqué) pour dériver la valeur
    ATTENDUE depuis le document Firestore, comparée à la valeur RÉELLEMENT lue en base.

    Correctif 1 (après le run #441) : la connexion `asyncpg.connect()` ci-dessous n'enregistrait
    PAS le codec JSON/JSONB (`backend.api.db._register_json_codecs`) — asyncpg renvoyait donc les
    colonnes JSONB (`image_urls`/`storage_image_urls`/`storage_image_gs_uris`) comme des CHAÎNES
    JSON brutes plutôt que des listes Python, faisant "échouer" la comparaison sur ces 3 colonnes
    pour quasiment chaque annonce (110 faux positifs sur 40) — un bug de CE script de validation,
    pas de l'export lui-même (`export_firestore_to_postgres.py` utilise bien `_register_json_codecs`
    via `db.py`, confirmé en relisant son code). Toutes les 38 autres colonnes comparées, elles,
    correspondaient déjà parfaitement au premier essai.

    Correctif 2 (après le run #442) : le correctif 1 passait `init=_register_json_codecs` à
    `asyncpg.connect()` — mais ce paramètre n'existe QUE sur `create_pool()` (voir
    `db.py::init_pool()`), pas sur `connect()` (`TypeError` immédiate). Appelé manuellement sur la
    connexion après coup à la place.
    """
    import random
    import subprocess
    import sys
    from datetime import timedelta
    from decimal import Decimal
    from pathlib import Path

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    def _run(cmd, timeout=30):
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    MIGRATION_BRANCH = "claude/firestore-postgres-migration"
    FILES_TO_EXTRACT = ["backend/api/__init__.py", "backend/api/db.py", "backend/scripts/export_firestore_to_postgres.py"]
    CREDS_PATH = Path.home() / ".guitarhunter_staging_db.env"
    SAMPLE_SIZE = 40

    logger.info("=== Validation d'un échantillon déjà migré (champ par champ) ===")

    fetch = _run(["git", "fetch", "origin", MIGRATION_BRANCH])
    if fetch.returncode != 0:
        logger.error(f"git fetch impossible : {fetch.stderr.strip()}")
        return

    extracted = []
    try:
        for rel_path in FILES_TO_EXTRACT:
            show = _run(["git", "show", f"FETCH_HEAD:{rel_path}"], timeout=15)
            if show.returncode != 0:
                logger.error(f"Impossible d'extraire '{rel_path}' : {show.stderr.strip()}")
                return
            dest = Path(rel_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(show.stdout)
            extracted.append(dest)

        if not CREDS_PATH.exists():
            logger.error(f"{CREDS_PATH} introuvable.")
            return
        database_url = None
        for line in CREDS_PATH.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                database_url = line[len("DATABASE_URL="):].strip()
        if not database_url:
            logger.error("DATABASE_URL absent du fichier de credentials.")
            return

        pip = _run([sys.executable, "-m", "pip", "install", "-q", "asyncpg"], timeout=60)
        if pip.returncode != 0:
            logger.error(f"Échec pip install asyncpg : {pip.stderr.strip()}")
            return

        sys.path.insert(0, str(Path.cwd()))
        from backend.scripts.export_firestore_to_postgres import map_deal, DEAL_COLUMNS
        from backend.api.db import _register_json_codecs
        from config import FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET, USER_ID_TARGET, APP_ID_TARGET
        from backend.database import DatabaseService
        import asyncio
        import asyncpg

        db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
        if db_service.offline_mode or not db_service.db:
            logger.error("Firebase en mode hors-ligne.")
            return
        user_ref = (
            db_service.db.collection("artifacts").document(APP_ID_TARGET)
            .collection("users").document(USER_ID_TARGET)
        )

        SKIP_COLUMNS = {"ai_analysis_raw", "user_id"}
        TOLERANCE = timedelta(seconds=1)

        def _match(expected, actual):
            if isinstance(expected, Decimal):
                expected = float(expected)
            if isinstance(actual, Decimal):
                actual = float(actual)
            if hasattr(expected, "isoformat") and hasattr(actual, "isoformat"):
                return abs(expected - actual) <= TOLERANCE
            return expected == actual

        async def _validate():
            conn = await asyncpg.connect(database_url, timeout=10)
            await _register_json_codecs(conn)  # connect() n'a pas de paramètre init= (contrairement à create_pool())
            try:
                rows = await conn.fetch("SELECT id FROM guitar_deals WHERE user_id = $1", USER_ID_TARGET)
                migrated_ids = [r["id"] for r in rows]
                sample_ids = random.sample(migrated_ids, min(SAMPLE_SIZE, len(migrated_ids)))
                logger.info(f"{len(migrated_ids)} annonce(s) déjà migrée(s) — échantillon de {len(sample_ids)}.")

                mismatches = []
                checked = 0
                for deal_id in sample_ids:
                    doc = user_ref.collection("guitar_deals").document(deal_id).get()
                    if not doc.exists:
                        mismatches.append((deal_id, "existence", "présent (Postgres)", "ABSENT de Firestore"))
                        continue
                    expected, _ = map_deal(deal_id, doc.to_dict() or {})
                    pg_row = await conn.fetchrow("SELECT * FROM guitar_deals WHERE id = $1", deal_id)
                    checked += 1
                    for col in DEAL_COLUMNS:
                        if col in SKIP_COLUMNS or col == "id":
                            continue
                        if not _match(expected.get(col), pg_row[col]):
                            mismatches.append((deal_id, col, expected.get(col), pg_row[col]))

                    chat_fs = len(list(doc.reference.collection("chat").stream()))
                    chat_pg = await conn.fetchval("SELECT count(*) FROM deal_chat WHERE deal_id = $1", deal_id)
                    if chat_fs != chat_pg:
                        mismatches.append((deal_id, "chat_count", chat_fs, chat_pg))
                    resto_fs = len(list(doc.reference.collection("restorationPlan").stream()))
                    resto_pg = await conn.fetchval("SELECT count(*) FROM restoration_plan_items WHERE deal_id = $1", deal_id)
                    if resto_fs != resto_pg:
                        mismatches.append((deal_id, "restoration_count", resto_fs, resto_pg))
                return checked, mismatches
            finally:
                await conn.close()

        checked, mismatches = asyncio.run(_validate())
        logger.info(f"{checked} annonce(s) vérifiée(s) champ par champ + comptages chat/restauration.")
        if mismatches:
            logger.warning(f"{len(mismatches)} écart(s) trouvé(s) :")
            for deal_id, field, expected, actual in mismatches:
                exp_repr, act_repr = repr(expected)[:150], repr(actual)[:150]
                logger.warning(f"  {deal_id} . {field} : Firestore={exp_repr}  Postgres={act_repr}")
        else:
            logger.info("Aucun écart détecté sur l'échantillon vérifié.")
    finally:
        for path in extracted:
            if path.exists():
                path.unlink()
        api_dir = Path("backend/api")
        if api_dir.exists() and not any(api_dir.iterdir()):
            api_dir.rmdir()
        logger.info("Fichiers temporaires supprimés.")

    logger.info("=== Fin de la validation ===")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
