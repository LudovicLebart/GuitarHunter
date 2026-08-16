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

    2026-08-16 : audit + normalisation des classifications taxonomiques
    (`backend/scripts/audit_classifications.py`). GRATUIT, aucun appel Gemini :

      - compte les annonces par type de résolution (chemin complet / feuille / AMBIGU /
        INCONNU / vide) et liste les valeurs non résolvables avec des exemples de titres —
        c'est ce comptage qui doit décider de la suite (correction manuelle ou ré-analyse
        payante des annonces restantes) ;
      - peut aussi réécrire en chemin canonique les valeurs qui se résolvent déjà sans
        ambiguïté (document + index) — mais **PAS dans cette exécution**.

    `dry_run=True` : lecture seule, AUCUNE écriture en base. Choix explicite de l'utilisateur —
    on regarde les chiffres avant d'autoriser la moindre réécriture des données de production.
    La normalisation se fera lors d'un déploiement ultérieur, en repassant ce flag à False.

    Idempotent (a fortiori en lecture seule). Rapide : Firestore uniquement, aucun appel Gemini.
    """
    from backend.scripts.audit_classifications import run as audit_run
    audit_run(dry_run=True)


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
