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

    2026-09-13 : diagnostic Tailscale Funnel (lecture seule, aucune exposition) — avant
    d'exposer publiquement guitarhunter-api (Phase A.3, Chantier A), on vérifie l'état actuel
    de Funnel/Serve sur ce nœud pour savoir si l'activation peut se faire entièrement depuis
    deploy.yml, ou si une action manuelle côté console admin Tailscale (HTTPS Certificates,
    ACL) est requise en amont — comme ça a été le cas pour la règle sudoers.

    Résultat (run #462, voir JOURNAL.md) : "tailscale funnel status" et "tailscale serve
    status" renvoient tous les deux "No serve config" (exit 0) — ni erreur explicite, ni
    confirmation que la fonctionnalité HTTPS Certificates/Funnel est activée au niveau du
    tailnet. INCONCLUSIF : ce statut est celui d'un nœud où rien n'est configuré, que Funnel
    soit disponible ou non. Seule une tentative d'activation réelle (`tailscale funnel ... on`)
    lèvera l'ambiguïté — désarmé ci-dessous en attendant la décision de l'utilisateur.
    """
    import subprocess

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    def _run(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            combined = out if out else err
            return f"[exit={r.returncode}] {combined}" if combined else f"[exit={r.returncode}] (vide)"
        except Exception as e:
            return f"(échec: {e})"

    logger.info(f"tailscale version : {_run(['tailscale', 'version'])}")
    logger.info(f"tailscale status --self : {_run(['tailscale', 'status', '--self'])}")
    logger.info(f"tailscale funnel status : {_run(['tailscale', 'funnel', 'status'])}")
    logger.info(f"tailscale serve status : {_run(['tailscale', 'serve', 'status'])}")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
