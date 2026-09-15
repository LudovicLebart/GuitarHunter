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

    2026-09-15 : diagnostic Chantier G (run #497) — CONFIRMÉ. `analysisConfig.activeSearchFamilies`
    contenait 'guitare' et 'guitare.electrique' en plus des familles fines voulues. Le matching
    `classification == family or classification.startswith(f"{family}.")` (analyzer.py) fait que
    'guitare' seul préfixe-matche TOUTE classification "guitare.*" — d'où la promotion de tous
    les types malgré la config. Preuve logs (18h) : 52 verdicts Portier, seulement 7 non promues
    (toutes "Parlor", probablement un mismatch de casse indépendant). Cause racine : le
    TaxonomyTreePicker (Chantier G, commit 9e1614c) laisse cocher un nœud ancêtre ET ses
    descendants indépendamment, sans avertir qu'un ancêtre coché élargit silencieusement le
    filtre à toute sa branche. Correctif proposé (à valider) : ne pas cocher automatiquement les
    ancêtres, et/ou faire du matching le plus spécifique sélectionné plutôt qu'une union de
    préfixes. Désarmé ci-dessous — lecture seule, rien à rejouer.
    """
    pass


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
