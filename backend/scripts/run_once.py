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

ACTIVE = True


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-15 : diagnostic Chantier G — l'utilisateur rapporte que le filtre
    `activeSearchFamilies` (configuré cette nuit pour ne promouvoir que
    "Guitare > Electrique > Semi Hollow 1&2 Caisse" vers T2/T3) n'a apparemment filtré
    aucune annonce (tous types de guitares promus). Lecture en lecture seule (aucune
    écriture) : valeur brute de `analysisConfig.activeSearchFamilies` en Firestore pour
    l'utilisateur principal + comptage, sur les logs Firestore des dernières 18h, des
    lignes "Verdict Portier" (total décisions T1) vs "Hors recherche active" (annonces
    effectivement non promues par Chantier G).
    """
    import datetime
    import firebase_admin
    from firebase_admin import credentials, firestore

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    from config import APP_ID_TARGET, USER_ID_TARGET, FIREBASE_KEY_PATH

    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    db = firestore.client()

    user_id = USER_ID_TARGET
    logger.info(f"Utilisateur cible : {user_id[:12]}...")

    user_doc = db.collection('artifacts').document(APP_ID_TARGET) \
        .collection('users').document(user_id).get()
    analysis_config = (user_doc.to_dict() or {}).get('analysisConfig', {})
    active_search_families = analysis_config.get('activeSearchFamilies')
    logger.info(f"analysisConfig.activeSearchFamilies (valeur brute Firestore) = {active_search_families!r}")

    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=18)
    logs_ref = db.collection('artifacts').document(APP_ID_TARGET) \
        .collection('users').document(user_id).collection('logs') \
        .where('timestamp', '>=', since).order_by('timestamp')

    total_verdicts = 0
    total_not_promoted = 0
    sample_not_promoted = []

    for doc in logs_ref.stream():
        msg = (doc.to_dict() or {}).get('message', '')
        if 'Verdict Portier' in msg:
            total_verdicts += 1
        if 'Hors recherche active' in msg:
            total_not_promoted += 1
            if len(sample_not_promoted) < 5:
                sample_not_promoted.append(msg)

    logger.info(f"--- Fenêtre analysée : depuis {since.isoformat()} ---")
    logger.info(f"Total 'Verdict Portier' (décisions T1) : {total_verdicts}")
    logger.info(f"Total 'Hors recherche active' (non promues par Chantier G) : {total_not_promoted}")
    for s in sample_not_promoted:
        logger.info(f"  ex: {s}")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
