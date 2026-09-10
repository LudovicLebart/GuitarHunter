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

    2026-09-10 (suite) : le diagnostic précédent (run GitHub Actions #436) a montré que le port
    5432 est déjà occupé par un conteneur Docker SANS RAPPORT avec ce projet
    (`moneybot_optuna_db`, `postgres:15-alpine`, projet distinct sur ce même serveur) — décision
    prise avec l'utilisateur : provisionner un conteneur Postgres DÉDIÉ à Guitar Hunter, isolé de
    celui-là, sur un port différent (5433), pour le dry-run de migration (Chantier A, voir
    FIRESTORE_MIGRATION_PLAN.md §8). Idempotent : si le conteneur existe déjà (ex: second
    déclenchement dev+master du même push), ne le recrée pas.

    Le mot de passe généré n'est JAMAIS écrit dans les logs GitHub Actions (visibles dans
    l'historique CI) — uniquement dans un fichier local au serveur (permissions 600), relu par un
    futur run_once.py pour lancer le dry-run lui-même sans jamais transiter par ces logs.
    """
    import secrets
    import subprocess
    import time
    from pathlib import Path

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    CONTAINER_NAME = "guitarhunter_pg_staging"
    HOST_PORT = "5433"
    DB_NAME = "guitarhunter_staging"
    DB_USER = "guitarhunter"
    CREDS_PATH = Path.home() / ".guitarhunter_staging_db.env"

    def _run(cmd, timeout=30):
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    logger.info(f"=== Provisioning du conteneur Postgres de staging '{CONTAINER_NAME}' ===")

    existing = _run(["docker", "ps", "-a", "--filter", f"name=^{CONTAINER_NAME}$", "--format", "{{.Names}}"])
    if CONTAINER_NAME in existing.stdout:
        logger.info(f"Conteneur '{CONTAINER_NAME}' déjà présent — rien recréé (idempotent).")
        status = _run(["docker", "ps", "--filter", f"name=^{CONTAINER_NAME}$", "--format", "{{.Status}}"])
        logger.info(f"Statut : {status.stdout.strip() or 'ARRÊTÉ (docker start requis manuellement)'}")
        logger.info(f"Fichier de credentials : {'présent' if CREDS_PATH.exists() else 'ABSENT (voir avertissement plus bas si besoin)'} ({CREDS_PATH}).")
        return

    password = secrets.token_urlsafe(24)
    logger.info(f"Création de '{CONTAINER_NAME}' (postgres:16-alpine, 127.0.0.1:{HOST_PORT}, volume dédié)...")

    result = _run([
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "--restart", "unless-stopped",
        "-e", f"POSTGRES_USER={DB_USER}",
        "-e", f"POSTGRES_PASSWORD={password}",
        "-e", f"POSTGRES_DB={DB_NAME}",
        "-p", f"127.0.0.1:{HOST_PORT}:5432",
        "-v", f"{CONTAINER_NAME}_data:/var/lib/postgresql/data",
        "postgres:16-alpine",
    ], timeout=180)  # premier pull de l'image possible ici
    if result.returncode != 0:
        logger.error(f"Échec de la création du conteneur : {result.stderr.strip()}")
        return
    logger.info(f"Conteneur créé : {result.stdout.strip()}")

    database_url = f"postgresql://{DB_USER}:{password}@127.0.0.1:{HOST_PORT}/{DB_NAME}"
    CREDS_PATH.write_text(f"DATABASE_URL={database_url}\n")
    CREDS_PATH.chmod(0o600)
    logger.info(f"DSN écrit dans {CREDS_PATH} (permissions 600) — volontairement pas affiché ici.")

    for attempt in range(10):
        check = _run(["docker", "exec", CONTAINER_NAME, "pg_isready", "-U", DB_USER])
        if check.returncode == 0:
            logger.info(f"Postgres prêt après {attempt + 1} tentative(s) : {check.stdout.strip()}")
            break
        time.sleep(2)
    else:
        logger.warning("Postgres ne répond pas encore à pg_isready après ~20s — à vérifier manuellement.")

    logger.info("=== Fin du provisioning ===")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
