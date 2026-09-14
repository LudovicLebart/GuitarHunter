"""
Script de récupération (2026-08-12) : ré-analyse via Gemini les annonces vendues dont
`aiAnalysis` a été corrompu par le bug ArrayUnion de `mark_deal_as_sold()` (corrigé dans
le même commit — voir JOURNAL.md et `repository.py`). Le pipeline normal 3-Tiers est
utilisé tel quel (pas de `force_expert` — ce flag force aussi le Tier 3 pour CHAQUE
annonce, inutilement coûteux ici ; le Portier/Analyste/Expert décident naturellement
comme pour une annonce fraîchement scrapée).

Utilise `storageImageUrls` (Firebase Storage, permanentes) en priorité sur `imageUrls`
(URLs Facebook/Kijiji d'origine, expirées depuis longtemps pour de l'historique).

Écrit UNIQUEMENT le champ `aiAnalysis` (document + index) — jamais `status`/`soldAt` :
`repository.update_deal_analysis()` n'est volontairement PAS utilisé ici, il écraserait
`status` (`sold` → `analyzed`/`rejected`) selon le nouveau verdict, ce qu'on ne veut
surtout pas pour de l'historique déjà vendu.

Idempotent : ignore les annonces dont `aiAnalysis` a déjà un `verdict` valide (déjà
ré-analysées) — rejouable sans risque si interrompu, et sûr à relancer.

Lancé en arrière-plan détaché depuis `run_once.py` (job de plusieurs heures, largement
au-delà du timeout de 10 min du step SSH de `deploy.yml`) : survit à la fin du job de
déploiement et à un redémarrage du service `guitare-hunter` (processus indépendant).
Log de progression : `reanalyze_sold_deals.log` à la racine du repo.
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.getcwd())

from google.cloud.firestore_v1.base_query import FieldFilter
from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService
from backend.repository import FirestoreRepository
from backend.analyzer import DealAnalyzer
from backend.services import ConfigManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("reanalyze_sold_deals")

# Pause défensive entre appels Gemini (limites de débit) — le job est déjà lent (réseau +
# inférence), cette pause ajoute peu par rapport au temps total.
DELAY_BETWEEN_CALLS_SECONDS = 0.5


def _is_corrupted(ai_analysis):
    return not isinstance(ai_analysis, dict) or not ai_analysis.get('verdict')


def _build_listing_data(deal_id, data):
    image_urls = data.get('storageImageUrls') or data.get('imageUrls') or []
    return {
        "title": data.get('title'),
        "price": data.get('price'),
        "description": data.get('description', ''),
        "location": data.get('location', 'Inconnue'),
        "imageUrls": image_urls,
        "imageUrl": (image_urls[0] if image_urls else None),
        "link": data.get('link'),
        "id": deal_id,
        **({'latitude': data['latitude'], 'longitude': data['longitude']} if 'latitude' in data else {}),
    }


PID_FILE = os.path.join(os.getcwd(), 'reanalyze_sold_deals.pid')


def run():
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db_client = db_service.db
    if not db_client:
        logger.error("Erreur de connexion à Firebase.")
        return

    analyzer = DealAnalyzer(logger=logger)

    users_ref = db_client.collection('artifacts').document(APP_ID_TARGET).collection('users')
    users = list(users_ref.stream())
    logger.info(f"Ré-analyse sur {len(users)} utilisateurs.")

    grand_total_processed = 0
    grand_total_failed = 0

    for user_doc in users:
        user_id = user_doc.id
        repo = FirestoreRepository(db_client, APP_ID_TARGET, user_id)

        config_manager = ConfigManager(repo, {})
        config_manager.sync_with_firestore(initial=True)
        current_config = config_manager.current_config_snapshot
        if not current_config:
            continue

        sold_docs = list(repo.collection_ref.where(filter=FieldFilter('status', '==', 'sold')).stream())
        to_process = [(doc.id, doc.to_dict()) for doc in sold_docs if _is_corrupted(doc.to_dict().get('aiAnalysis'))]

        if not to_process:
            continue

        logger.info(f"Utilisateur {user_id} : {len(to_process)} annonces à ré-analyser.")
        processed = 0
        failed = 0

        for deal_id, data in to_process:
            listing_data = _build_listing_data(deal_id, data)
            try:
                analysis = analyzer.analyze_deal(listing_data, firestore_config=current_config)
                # Écrit UNIQUEMENT aiAnalysis (doc + index) — jamais status/soldAt, voir docstring.
                repo.collection_ref.document(deal_id).update({'aiAnalysis': analysis})
                repo._update_deal_index(deal_id, ai_analysis=analysis)
                processed += 1
            except Exception as e:
                logger.error(f"Échec ré-analyse {deal_id} (utilisateur {user_id}) : {e}")
                failed += 1

            if (processed + failed) % 50 == 0:
                logger.info(f"  Utilisateur {user_id} : {processed + failed}/{len(to_process)} traitées...")

            time.sleep(DELAY_BETWEEN_CALLS_SECONDS)

        logger.info(f"Utilisateur {user_id} terminé : {processed} ré-analysées, {failed} échecs.")
        grand_total_processed += processed
        grand_total_failed += failed

    logger.info(f"TERMINÉ. Total : {grand_total_processed} ré-analysées, {grand_total_failed} échecs.")


if __name__ == "__main__":
    # Verrou best-effort (déploiement se déclenche sur dev ET master, généralement coup sur
    # coup — évite deux passes concurrentes sur les mêmes annonces, doublant inutilement le
    # coût Gemini). Pas de garantie d'atomicité stricte, mais fenêtre de course minime en
    # pratique et sans risque de corruption (écritures idempotentes de toute façon).
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                existing_pid = int(f.read().strip())
            os.kill(existing_pid, 0)
            logger.warning(f"Ré-analyse déjà en cours (PID {existing_pid}), on ne relance pas.")
            sys.exit(0)
        except (OSError, ValueError):
            pass  # PID mort ou fichier invalide, on continue.

    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    try:
        run()
    finally:
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
