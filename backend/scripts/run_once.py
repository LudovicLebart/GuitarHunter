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

sys.path.insert(0, os.getcwd())

ACTIVE = False


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-18 : Chantier G — diagnostic lecture seule de l'efficacité du filtre
    "Recherche Active" (voir backend/scripts/check_active_search_filter_logs.py) — CONFIRMÉ,
    résultat lu dans les logs GitHub Actions (runs #507/#508, dev + master). Fichier de log
    serveur du jour vide (0 activité depuis minuit UTC) ; côté Firestore, 36 NOT_PROMOTED
    historiques cohérents avec le filtre (Dreadnought/Stratocaster/Classique écartés), mais
    l'échantillon "60 dernières annonces" mélange des analyses d'AVANT la configuration du
    filtre (35/55 "promues" sans classification ou hors-filtre, ex: Dreadnought, amplis,
    étuis) — pas concluant tel quel, à rejouer après une vraie fenêtre d'activité récente si
    le sujet redevient prioritaire. Désarmé ci-dessous — rien à rejouer.
    """
    pass


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
