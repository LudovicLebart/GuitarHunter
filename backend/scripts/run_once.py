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

    2026-09-10 (suite) : le premier diagnostic PostgreSQL (run GitHub Actions #434) a montré
    `psql` client présent (16.13) mais AUCUN service `postgresql.service` ni utilisateur OS
    `postgres` — donc pas de paquet serveur natif installé. Pourtant une connexion TCP à
    `localhost:5432` a renvoyé "fe_sendauth: no password supplied" (PAS "connection refused")
    — quelque chose répond déjà sur ce port. Ce deuxième passage identifie QUOI (le plus
    probable : un Postgres via Docker), toujours en LECTURE SEULE, avant de décider comment
    provisionner une base de dry-run (voir FIRESTORE_MIGRATION_PLAN.md §8).
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

    logger.info("=== Diagnostic : qu'est-ce qui écoute sur le port 5432 ? ===")
    _try(["id"])
    _try(["docker", "--version"])
    _try(["docker", "ps"])
    _try(["docker", "ps", "-a"])
    _try(["ss", "-tlnp"])
    _try(["lsof", "-i", ":5432"])
    logger.info("=== Fin du diagnostic ===")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
