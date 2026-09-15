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

    2026-09-15 : correctif Chantier G — nettoie `analysisConfig.activeSearchFamilies` en
    Firestore pour l'utilisateur principal, déjà corrompu par des ancêtres cochés en plus de
    leurs descendants ('guitare', 'guitare.electrique' en plus de
    'guitare.electrique.semi_hollow_1_2_caisse', etc. — voir run #497 / JOURNAL.md). Le code
    frontend (FilterDrawer.jsx) empêche désormais ce cas à la source via pruneToDeepestPaths,
    mais la valeur déjà en base doit être nettoyée une fois manuellement — idempotent (ne garde
    que les chemins les plus spécifiques, sans effet si déjà propre).
    """
    import firebase_admin
    from firebase_admin import credentials, firestore

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    from config import APP_ID_TARGET, USER_ID_TARGET, FIREBASE_KEY_PATH

    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    db = firestore.client()

    def prune_to_deepest(paths):
        return [p for p in paths if not any(other != p and other.startswith(f"{p}.") for other in paths)]

    user_id = USER_ID_TARGET
    user_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users').document(user_id)
    doc = user_ref.get()
    analysis_config = (doc.to_dict() or {}).get('analysisConfig', {})
    current = analysis_config.get('activeSearchFamilies') or []
    cleaned = prune_to_deepest(current)

    logger.info(f"Utilisateur cible : {user_id[:12]}...")
    logger.info(f"Avant  : {current!r}")
    logger.info(f"Après  : {cleaned!r}")

    if sorted(cleaned) != sorted(current):
        user_ref.update({'analysisConfig.activeSearchFamilies': cleaned})
        logger.info("Firestore mis à jour.")
    else:
        logger.info("Déjà propre — rien à changer.")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
