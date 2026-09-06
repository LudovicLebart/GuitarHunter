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

ACTIVE = False


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-06 : avant de s'engager sur le chantier "pool d'annonces partagé entre
    utilisateurs" (TODO.md), l'utilisateur doute être le seul utilisateur réellement actif —
    si c'est le cas, la déduplication cross-utilisateur n'a presque aucun gain (rien à
    dédupliquer). Lance `analyze_funnel_by_user.py` (lecture seule, aucune écriture Firestore,
    voir en-tête du script) avec ses valeurs par défaut (30 jours, tous utilisateurs) pour
    obtenir le volume quotidien réel par utilisateur.

    Exécuté le 2026-09-06 (run GitHub Actions #408) : confirmé — 7 utilisateurs enregistrés,
    volume total 95.03/jour, dont 89.43/jour (94.1%) pour un seul utilisateur, 5.53/jour pour
    un second, le reste quasi nul ou inexistant (2 UID visiblement placeholder). Voir
    JOURNAL.md et TODO.md pour la conclusion sur le pool partagé. ACTIVE repassé à False.
    """
    from backend.scripts.analyze_funnel_by_user import main as analyze_funnel_main
    analyze_funnel_main()


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
