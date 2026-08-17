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

    2026-08-16 : audit + uniformisation des VILLES (`backend/scripts/audit_cities.py`).
    GRATUIT, aucun appel Gemini :

      - regroupe les valeurs `location` par clé canonique et liste les villes stockées sous
        plusieurs graphies (`Montréal, QC` / `montreal` / `St-Jean-sur-Richelieu,QC`) ;
      - réécrit `location` (document + index) vers la graphie la plus riche de chaque ville.

    EN ÉCRITURE (`dry_run=False`) : choix explicite de l'utilisateur, à qui la lecture seule
    préalable a été proposée. Le rapport reste produit dans les mêmes logs, avec le détail des
    graphies fusionnées ville par ville — il est simplement lu après coup plutôt qu'avant.

    Ne fusionne jamais deux villes homonymes de régions différentes (`Paris, IDF` vs
    `Paris, ON`) : `regions_conflict()` les écarte, une réécriture en base étant irréversible.

    Idempotent : le 2e passage (le job se déclenche sur `dev` PUIS `master`) ne réécrit rien.
    Rapide : Firestore uniquement.
    """
    from backend.scripts.audit_cities import run as audit_cities_run
    audit_cities_run(dry_run=False)


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
