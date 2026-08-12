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

    2026-08-12 : DIAGNOSTIC EN LECTURE SEULE — aucune écriture Firestore. Quantifie
    l'ampleur de la corruption de `aiAnalysis` sur les annonces vendues, causée par un bug
    dans `mark_deal_as_sold()` (ArrayUnion appliqué à un champ objet, corrigé dans ce même
    commit — voir JOURNAL.md du 2026-08-12) : pour chaque utilisateur, compte le nombre
    d'annonces `status == 'sold'`, combien ont un `aiAnalysis` corrompu (liste au lieu
    d'objet, ou sans `verdict`), et combien ont un `initialVerdict` encore récupérable
    (champ figé à la création, jamais touché par ce bug). Sert à décider d'une stratégie
    de récupération (ré-analyse IA des annonces affectées, ou acceptation de la perte).
    """
    import logging
    from google.cloud.firestore_v1.base_query import FieldFilter
    from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
    from backend.database import DatabaseService

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once_diagnostic")

    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db_client = db_service.db
    if not db_client:
        logger.error("Erreur de connexion à Firebase.")
        return

    users_ref = db_client.collection('artifacts').document(APP_ID_TARGET).collection('users')
    users = list(users_ref.stream())
    logger.info(f"Diagnostic sur {len(users)} utilisateurs.")

    grand_total_sold = 0
    grand_total_corrupted = 0
    grand_total_recoverable_verdict = 0

    for user_doc in users:
        user_id = user_doc.id
        deals_ref = (
            db_client.collection('artifacts').document(APP_ID_TARGET)
            .collection('users').document(user_id).collection('guitar_deals')
        )
        sold_docs = deals_ref.where(filter=FieldFilter('status', '==', 'sold')).stream()

        total_sold = 0
        corrupted = 0
        recoverable_verdict = 0

        for doc in sold_docs:
            data = doc.to_dict()
            total_sold += 1
            ai = data.get('aiAnalysis')
            is_corrupted = not isinstance(ai, dict) or not ai.get('verdict')
            if is_corrupted:
                corrupted += 1
                if data.get('initialVerdict'):
                    recoverable_verdict += 1

        if total_sold > 0:
            logger.info(
                f"Utilisateur {user_id} : {total_sold} vendues, {corrupted} avec aiAnalysis "
                f"corrompu ({recoverable_verdict} avec initialVerdict récupérable)"
            )

        grand_total_sold += total_sold
        grand_total_corrupted += corrupted
        grand_total_recoverable_verdict += recoverable_verdict

    logger.info(
        f"TOTAL : {grand_total_sold} annonces vendues, {grand_total_corrupted} avec "
        f"aiAnalysis corrompu, {grand_total_recoverable_verdict} avec initialVerdict récupérable."
    )


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
