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

ACTIVE = True


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-10 (suite) : le conteneur Postgres de staging est prêt (run GitHub Actions #437,
    `guitarhunter_pg_staging`, DSN dans `~/.guitarhunter_staging_db.env`). Cette étape lance enfin
    le dry-run d'export réel — Firestore -> Postgres, limité à `config.USER_ID_TARGET` (un seul
    utilisateur d'abord, décidé avec l'utilisateur) — voir FIRESTORE_MIGRATION_PLAN.md §8.

    `backend/api/db.py`, `backend/api/schema.sql` et `backend/scripts/export_firestore_to_postgres.py`
    n'existent PAS sur `dev` (Chantier A reste isolé sur `claude/firestore-postgres-migration`,
    jamais mergé — stratégie de bascule "en une seule fois" actée avec l'utilisateur). Plutôt que
    de les fusionner dans `dev`, cette action les extrait TEMPORAIREMENT via `git show` depuis
    cette branche (aucun checkout, aucun commit, aucune modification de l'historique de `dev`),
    les exécute, puis les supprime explicitement à la fin (`finally`) — le dépôt sur le serveur
    revient exactement à l'état de `dev` après coup, comme si cette étape n'avait jamais eu lieu
    (hors le conteneur/le fichier de credentials déjà en place depuis l'étape précédente).
    """
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    def _run(cmd, timeout=60):
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    MIGRATION_BRANCH = "claude/firestore-postgres-migration"
    FILES_TO_EXTRACT = [
        "backend/api/__init__.py",
        "backend/api/db.py",
        "backend/api/schema.sql",
        "backend/scripts/export_firestore_to_postgres.py",
    ]
    CREDS_PATH = Path.home() / ".guitarhunter_staging_db.env"

    logger.info("=== Dry-run d'export Firestore -> Postgres (un seul utilisateur) ===")

    fetch = _run(["git", "fetch", "origin", MIGRATION_BRANCH], timeout=30)
    if fetch.returncode != 0:
        logger.error(f"git fetch de '{MIGRATION_BRANCH}' impossible : {fetch.stderr.strip()}")
        return

    extracted_paths = []
    try:
        for rel_path in FILES_TO_EXTRACT:
            show = _run(["git", "show", f"FETCH_HEAD:{rel_path}"], timeout=15)
            if show.returncode != 0:
                logger.error(f"Impossible d'extraire '{rel_path}' : {show.stderr.strip()}")
                return
            dest = Path(rel_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(show.stdout)
            extracted_paths.append(dest)
        logger.info(f"{len(extracted_paths)} fichier(s) extrait(s) temporairement (jamais commités sur dev).")

        if not CREDS_PATH.exists():
            logger.error(f"{CREDS_PATH} introuvable — le conteneur de staging a-t-il bien été provisionné (run #437) ?")
            return
        database_url = None
        for line in CREDS_PATH.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                database_url = line[len("DATABASE_URL="):].strip()
        if not database_url:
            logger.error(f"DATABASE_URL absent de {CREDS_PATH}.")
            return

        pip = _run([sys.executable, "-m", "pip", "install", "-q", "asyncpg"], timeout=60)
        if pip.returncode != 0:
            logger.error(f"Échec de l'installation d'asyncpg : {pip.stderr.strip()}")
            return
        logger.info("asyncpg installé dans le venv du bot.")

        from config import USER_ID_TARGET
        if not USER_ID_TARGET:
            logger.error("config.USER_ID_TARGET est vide — impossible de limiter le dry-run à un seul utilisateur.")
            return
        logger.info(f"Lancement de l'export pour l'utilisateur {USER_ID_TARGET[:8]}...")

        export = _run([
            sys.executable, "backend/scripts/export_firestore_to_postgres.py",
            "--database-url", database_url, "--user", USER_ID_TARGET,
        ], timeout=300)
        logger.info(f"--- Sortie de l'export (exit={export.returncode}) ---\n{export.stdout}")
        if export.stderr:
            logger.info(f"--- stderr de l'export ---\n{export.stderr}")
    finally:
        if Path("backend/api").exists():
            shutil.rmtree("backend/api")
        script_path = Path("backend/scripts/export_firestore_to_postgres.py")
        if script_path.exists():
            script_path.unlink()
        logger.info("Fichiers temporaires supprimés — arbre de travail revenu à l'état de dev.")

    logger.info("=== Fin du dry-run ===")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
