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

    2026-08-12 : récupération GRATUITE (aucun appel Gemini) des annonces vendues à
    `aiAnalysis` corrompu — reconstruit un verdict minimal depuis `initialVerdict` (champ
    figé à la création, jamais touché par le bug ArrayUnion de `mark_deal_as_sold()`, voir
    JOURNAL.md). Ne récupère que le verdict, pas classification/scores/marge — voir
    `backend/scripts/recover_initial_verdict.py` pour le détail. Rapide (pas d'appel
    réseau externe autre que Firestore), tourne en synchrone ici sans souci de timeout.

    La ré-analyse IA complète (plus lente, ~20-25$, plusieurs heures) via
    `backend/scripts/reanalyze_sold_deals.py` reste disponible mais n'est PAS déclenchée
    par ce `run()` — décision séparée, à activer explicitement plus tard si besoin.
    """
    from backend.scripts.recover_initial_verdict import run as recover_run
    recover_run()


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
