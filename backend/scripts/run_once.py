"""
Script "one-shot" exécuté automatiquement à CHAQUE déploiement
(.github/workflows/deploy.yml, job `deploy`, étape "Script de maintenance ponctuel") —
ce job est le seul contexte où le serveur a déjà les credentials Firebase en place
(.env / backend/config/serviceAccountKey.json écrits juste avant dans le même job).

Sert à exécuter une action ponctuelle en production (ex: script de migration) depuis un
environnement de dev qui n'a lui-même aucun accès à Firestore.

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

# Comme rebuild_index.py : nécessaire pour que `from backend.scripts... import ...` résolve,
# `python3 backend/scripts/run_once.py` n'ajoutant que le dossier du script (pas la racine du
# repo) à sys.path. Le job `deploy` exécute toujours ce script depuis la racine (~/GuitareHunter).
sys.path.insert(0, os.getcwd())

ACTIVE = True


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-08-12 : lance `backend/scripts/reanalyze_sold_deals.py` (ré-analyse IA des
    annonces vendues dont `aiAnalysis` a été corrompu, voir ce script pour le détail) en
    **arrière-plan détaché** (`subprocess.Popen(..., start_new_session=True)`) plutôt
    qu'en l'attendant ici : le job dure potentiellement plusieurs heures (~3500+ annonces,
    1-2 appels Gemini chacune), largement au-delà du timeout de 10 min du step SSH de
    `deploy.yml`. Détaché, il survit à la fin de ce step ET à un redémarrage du service
    `guitare-hunter` juste après (processus indépendant, pas un enfant de systemd).
    Progression consultable dans `reanalyze_sold_deals.log` à la racine du repo, ou en
    relançant plus tard le diagnostic en lecture seule (précédent usage de ce fichier,
    voir JOURNAL.md du 2026-08-12) pour voir le nombre d'annonces encore corrompues.
    Le script cible gère lui-même un verrou (`reanalyze_sold_deals.pid`) pour éviter une
    double exécution concurrente (déploiement sur dev ET master à chaque push) — ce
    `run()` peut donc être appelé sans précaution particulière à ce sujet.
    """
    import subprocess

    log_path = os.path.join(os.getcwd(), 'reanalyze_sold_deals.log')
    log_file = open(log_path, 'a')
    subprocess.Popen(
        [sys.executable, 'backend/scripts/reanalyze_sold_deals.py'],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=os.getcwd(),
        start_new_session=True,
    )
    print(f"[run_once] Ré-analyse des annonces vendues lancée en arrière-plan (log: {log_path}).")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
