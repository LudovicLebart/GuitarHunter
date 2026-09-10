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

    2026-09-10 : diagnostic PostgreSQL en préparation du dry-run de migration Firestore ->
    Postgres (Chantier A, voir docs/management/plans/FIRESTORE_MIGRATION_PLAN.md §8).
    AUCUNE trace dans JOURNAL.md d'une installation de Postgres sur CE serveur — tout ce qui a
    été construit/testé jusqu'ici (schema.sql, backend/api/*) l'a été uniquement dans un
    environnement de dev isolé, jamais déployé. Avant de lancer
    `backend/scripts/export_firestore_to_postgres.py` pour de vrai ici, on vérifie l'état réel
    plutôt que de le supposer : binaire `psql` présent, service actif, rôles/bases existants.

    Purement en LECTURE : aucune commande d'installation ou d'écriture ici, uniquement des
    commandes de diagnostic (which/--version/systemctl status/liste des rôles et bases).
    Chaque commande est protégée individuellement (binaire absent, permission refusée, timeout)
    pour que l'absence de Postgres/sudo ne fasse pas planter tout le diagnostic — le but est
    justement de découvrir cet état, pas de le présupposer.
    """
    import subprocess

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    def _try(cmd, timeout=15):
        label = " ".join(cmd)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            logger.info(
                f"$ {label}\n  [exit={result.returncode}]\n"
                f"  STDOUT: {result.stdout.strip() or '(vide)'}\n"
                f"  STDERR: {result.stderr.strip() or '(vide)'}"
            )
        except FileNotFoundError:
            logger.info(f"$ {label}\n  -> binaire introuvable.")
        except subprocess.TimeoutExpired:
            logger.info(f"$ {label}\n  -> timeout après {timeout}s.")
        except Exception as e:
            logger.info(f"$ {label}\n  -> erreur : {e}")

    logger.info("=== Diagnostic PostgreSQL (avant dry-run de migration, Chantier A) ===")
    _try(["which", "psql"])
    _try(["psql", "--version"])
    _try(["pg_lsclusters"])
    _try(["systemctl", "status", "postgresql", "--no-pager"])
    # sudo -n : échoue proprement (pas de blocage sur un prompt) si le compte de déploiement
    # n'a pas ce droit précis — deploy.yml n'accorde explicitement sudo -n que pour le restart
    # du service `guitare-hunter`, rien ne garantit qu'il couvre aussi `postgres`.
    _try(["sudo", "-n", "-u", "postgres", "psql", "-c", "\\du"])
    _try(["sudo", "-n", "-u", "postgres", "psql", "-c", "\\l"])
    # Sans sudo : si le rôle applicatif `guitarhunter` existe déjà avec un accès local
    # configuré (voir backend/api/db.py::DATABASE_URL), cette commande seule suffit à le confirmer.
    _try(["psql", "-U", "guitarhunter", "-h", "localhost", "-d", "guitarhunter", "-c", "SELECT 1;", "-w"])
    logger.info("=== Fin du diagnostic ===")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
