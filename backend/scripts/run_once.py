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

    2026-09-12 : diagnostic réseau pur (lecture seule, aucune écriture) — l'utilisateur n'a pas
    accès aux secrets GitHub (SERVER_IP) et voulait confirmer si la machine réellement ciblée
    par deploy.yml correspond à l'IP Tailscale 100.104.124.11 qu'il pense être le serveur.
    Logue hostname/whoami/IP Tailscale de la machine où CE script tourne réellement (donc la
    vraie cible SSH de deploy.yml) — jamais la valeur du secret SERVER_IP lui-même.
    """
    import subprocess

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    def _run(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return (r.stdout or r.stderr).strip()
        except Exception as e:
            return f"(échec: {e})"

    logger.info(f"hostname : {_run(['hostname'])}")
    logger.info(f"whoami : {_run(['whoami'])}")
    logger.info(f"pwd : {_run(['pwd'])}")
    logger.info(f"IP Tailscale (tailscale ip -4) : {_run(['tailscale', 'ip', '-4'])}")
    logger.info(f"tailscale status --self : {_run(['tailscale', 'status', '--self'])}")
    logger.info(f"Toutes les IP locales (hostname -I) : {_run(['hostname', '-I'])}")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
