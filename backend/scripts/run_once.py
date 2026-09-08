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
import logging

# Comme rebuild_index.py : nécessaire pour que `from backend.scripts... import ...` résolve,
# `python3 backend/scripts/run_once.py` n'ajoutant que le dossier du script (pas la racine du
# repo) à sys.path. Le job `deploy` exécute toujours ce script depuis la racine (~/GuitareHunter).
sys.path.insert(0, os.getcwd())

ACTIVE = True


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-08 : correction définitive de la ville "Saint-lambert" du catalogue partagé
    (`artifacts/{APP_ID}/cities`), déjà repérée par l'audit du 2026-08-25
    (`backend/scripts/audit_city_coordinates.py`, coordonnées 48.9382/-0.5474 = homonyme en
    France, même piège que "Beloeil" Québec/Wallonie) mais jamais corrigée en base — un scan
    Kijiji en production a redonné 0 résultat le 2026-09-08 à cause de ce même point. Réécrit
    lat/lng vers le "Saint-Lambert" voulu par l'utilisateur (Montérégie, agglomération de
    Longueuil — confirmé via Nominatim, `display_name`: "Saint-Lambert, Agglomération de
    Longueuil, Montérégie, Québec, Canada") et retire `needsReview` (coordonnées maintenant
    vérifiées manuellement). Idempotent : no-op si la ville n'a plus ces coordonnées fautives.
    """
    from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
    from backend.database import DatabaseService
    from firebase_admin import firestore as fb_firestore

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    BAD_LAT, BAD_LNG = 48.9382022, -0.547455
    FIXED_LAT, FIXED_LNG = 45.5016203, -73.5102981

    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db = db_service.db
    if not db:
        logger.error("Erreur de connexion à Firebase.")
        return

    shared_cities_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('cities')
    fixed = 0
    for doc in shared_cities_ref.stream():
        data = doc.to_dict()
        if data.get('name', '').strip().lower() != 'saint-lambert':
            continue
        if abs((data.get('latitude') or 0) - BAD_LAT) > 0.01 or abs((data.get('longitude') or 0) - BAD_LNG) > 0.01:
            continue
        shared_cities_ref.document(doc.id).set(
            {'latitude': FIXED_LAT, 'longitude': FIXED_LNG, 'needsReview': fb_firestore.DELETE_FIELD},
            merge=True,
        )
        logger.info(f"Ville '{data.get('name')}' (id={doc.id}) corrigée : {FIXED_LAT}, {FIXED_LNG}.")
        fixed += 1

    logger.info(f"Terminé : {fixed} ville(s) corrigée(s).")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
