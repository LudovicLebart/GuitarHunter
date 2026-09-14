"""
Script de récupération (2026-08-12) — GRATUIT, AUCUN APPEL GEMINI. Pour les annonces
vendues dont `aiAnalysis` a été corrompu (bug ArrayUnion de `mark_deal_as_sold()`, corrigé
dans `repository.py` — voir JOURNAL.md) mais qui ont encore un `initialVerdict` valide
(champ figé à la création, jamais touché par ce bug), reconstruit un `aiAnalysis` minimal
`{verdict, model_used, reasoning}` à partir de ce champ.

Ne récupère QUE le verdict d'origine — pas `classification`/scores/marque/marge (perdus
pour de bon sans ré-analyse IA, voir `reanalyze_sold_deals.py` pour cette étape séparée,
plus coûteuse et lente, décidée à part). Suffisant pour les stats basées sur le verdict
seul (Géographie des opportunités, taux d'opportunités Facebook vs Kijiji), pas pour
celles qui ont besoin de la classification ou des scores (Sweet Spot, Vitesse de vente
par type, Marge par catégorie, Score IA Moyen).

Idempotent : ignore les annonces déjà correctement analysées ou sans `initialVerdict`
récupérable. Écrit uniquement `aiAnalysis` (jamais `status`/`soldAt`).

Rapide (pas d'appel réseau externe autre que Firestore) : peut tourner de façon synchrone
dans `run_once.py`, contrairement à `reanalyze_sold_deals.py`.
"""
import sys
import os
import logging

sys.path.insert(0, os.getcwd())

from google.cloud.firestore_v1.base_query import FieldFilter
from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService
from backend.repository import FirestoreRepository

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("recover_initial_verdict")


def _is_corrupted(ai_analysis):
    return not isinstance(ai_analysis, dict) or not ai_analysis.get('verdict')


def run():
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db_client = db_service.db
    if not db_client:
        logger.error("Erreur de connexion à Firebase.")
        return

    users_ref = db_client.collection('artifacts').document(APP_ID_TARGET).collection('users')
    users = list(users_ref.stream())
    logger.info(f"Récupération (verdict seul) sur {len(users)} utilisateurs.")

    grand_total_recovered = 0

    for user_doc in users:
        user_id = user_doc.id
        repo = FirestoreRepository(db_client, APP_ID_TARGET, user_id)

        sold_docs = list(repo.collection_ref.where(filter=FieldFilter('status', '==', 'sold')).stream())
        recovered = 0

        for doc in sold_docs:
            data = doc.to_dict()
            if not _is_corrupted(data.get('aiAnalysis')):
                continue
            initial_verdict = data.get('initialVerdict')
            if not initial_verdict:
                continue

            minimal_analysis = {
                'verdict': initial_verdict,
                'model_used': data.get('initialModelUsed') or 'unknown',
                'reasoning': (
                    "Verdict récupéré depuis initialVerdict — aiAnalysis original perdu "
                    "(bug ArrayUnion corrigé le 2026-08-12, voir JOURNAL.md). "
                    "Classification/scores/marge non récupérables sans ré-analyse IA."
                ),
            }
            repo.collection_ref.document(doc.id).update({'aiAnalysis': minimal_analysis})
            repo._update_deal_index(doc.id, ai_analysis=minimal_analysis)
            recovered += 1

        if recovered > 0:
            logger.info(f"Utilisateur {user_id} : {recovered} annonces récupérées (verdict seul).")
        grand_total_recovered += recovered

    logger.info(f"TERMINÉ. {grand_total_recovered} annonces récupérées au total (verdict seul, sans ré-analyse).")


if __name__ == "__main__":
    run()
