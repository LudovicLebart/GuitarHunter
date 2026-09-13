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

    2026-09-13 : Phase A.4 — lance l'export Firestore→Postgres COMPLET (sans --user, donc
    tous les utilisateurs) contre guitarhunter_pg_staging. Le dry-run précédent (2026-09-10)
    n'avait migré que 2414/5978 annonces de l'utilisateur principal (coupé par le
    command_timeout SSH de 10 min), et n'avait jamais touché les 6 autres utilisateurs.
    `export_firestore_to_postgres.py` est idempotent (voir son en-tête) — un simple
    ré-lancement sans --user couvre tout, sans script séparé pour "juste le manquant".

    Lancé en ARRIÈRE-PLAN (subprocess détaché de la session SSH, `start_new_session=True`)
    car le volume total dépasse très probablement le budget de 10 minutes du job de
    déploiement (décision actée le 2026-09-10 de ne pas augmenter ce timeout global, qui
    affecterait tous les déploiements futurs). Ce script NE ATTEND PAS la fin de l'export —
    il logue juste le PID et le chemin du fichier de log, puis retourne immédiatement. La
    progression/complétion sera vérifiée par un futur run_once.py de LECTURE SEULE (tail du
    log + `SELECT COUNT(*) ... GROUP BY user_id` sur guitar_deals), pas ici.
    """
    import subprocess

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    env_path = os.path.expanduser("~/.guitarhunter_staging_db.env")
    dsn = None
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    dsn = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except FileNotFoundError:
        logger.error(f"Fichier introuvable : {env_path}")
        return

    if not dsn:
        logger.error(f"DATABASE_URL introuvable dans {env_path} — abandon.")
        return

    log_path = os.path.expanduser("~/export_full_a4.log")
    try:
        logfile = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            ["venv/bin/python", "backend/scripts/export_firestore_to_postgres.py", "--database-url", dsn],
            stdout=logfile, stderr=subprocess.STDOUT,
            cwd=os.getcwd(), start_new_session=True,
        )
    except Exception as e:
        logger.error(f"Échec du lancement : {e}")
        return

    logger.info(f"Export complet lancé en arrière-plan — PID={proc.pid}, log={log_path}")
    logger.info("Ce script ne bloque PAS jusqu'à la fin (l'export peut prendre plusieurs "
                "minutes, au-delà du command_timeout SSH) — vérifier la progression via un "
                "futur run_once.py de diagnostic (tail du log + comptages Postgres).")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
