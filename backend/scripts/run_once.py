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

    2026-09-13 : activation réelle de Tailscale Funnel sur le port 8000 (guitarhunter-api).
    Le diagnostic précédent (funnel status / serve status = "No serve config") était
    inconclusif — impossible de savoir si HTTPS Certificates est activé au niveau du tailnet
    sans tenter une activation réelle. `tailscale funnel --bg 8000` : le flag `--bg` évite de
    bloquer en foreground (le timeout de 15s du subprocess suffit sinon à tuer la commande
    avant confirmation). Idempotent : rejouer la commande sur un funnel déjà actif ne fait
    rien de plus. Effet, si succès : le port 8000 (127.0.0.1, guitarhunter-api, staging)
    devient accessible publiquement via une URL HTTPS générée par Tailscale — une conséquence
    réelle et volontaire de ce run, pas un simple diagnostic en lecture seule comme les
    précédents. Désarmé seulement après confirmation du résultat par l'utilisateur.
    """
    import subprocess

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    def _run(cmd, timeout=15):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            combined = "\n".join(p for p in (out, err) if p)
            return f"[exit={r.returncode}] {combined}" if combined else f"[exit={r.returncode}] (vide)"
        except Exception as e:
            return f"(échec: {e})"

    logger.info(f"AVANT — tailscale funnel status : {_run(['tailscale', 'funnel', 'status'])}")
    logger.info(f"Activation — sudo tailscale funnel --bg 8000 : {_run(['sudo', 'tailscale', 'funnel', '--bg', '8000'])}")
    logger.info(f"APRÈS — tailscale funnel status : {_run(['tailscale', 'funnel', 'status'])}")
    logger.info(f"APRÈS — tailscale serve status : {_run(['tailscale', 'serve', 'status'])}")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
