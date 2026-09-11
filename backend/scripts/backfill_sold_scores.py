"""
Script de récupération léger (2026-08-17) : variante moins coûteuse de
`reanalyze_sold_deals.py` pour les mêmes annonces vendues dont `aiAnalysis` a été corrompu
par le bug ArrayUnion de `mark_deal_as_sold()` (corrigé le 2026-08-12 — voir JOURNAL.md).

Différence avec `reanalyze_sold_deals.py` (qui reste disponible pour une vraie ré-triage
complète si besoin) : appelle `analyzer.analyze_deal_light()` au lieu de `analyze_deal()` —
un seul appel au modèle Analyste T2, sans Portier T1 (inutile, l'annonce est déjà vendue) ni
risque de déclencher l'Expert Pro T3 (coûteux, inutile pour de l'historique), avec un JSON de
sortie réduit aux champs structurés (scores/classification/marge/verdict, pas de texte libre).

Utilise `storageImageUrls` (Firebase Storage, permanentes) en priorité sur `imageUrls`
(URLs Facebook/Kijiji d'origine, expirées depuis longtemps pour de l'historique).

Écrit UNIQUEMENT le champ `aiAnalysis` (document + index) — jamais `status`/`soldAt`/
`timestamp` : `repository.update_deal_analysis()` n'est volontairement PAS utilisé ici, il
écraserait `status` selon le nouveau verdict, et `_update_deal_index()` est appelé sans
`timestamp=` pour ne pas faire apparaître ces annonces dans "Volume de Scraping Quotidien"
(`StatsView.jsx::dailyVolumeData`, basé sur ce champ) comme si elles avaient été scrapées/
analysées aujourd'hui — demande explicite de l'utilisateur.

Idempotent : ignore les annonces dont `aiAnalysis` a déjà un `verdict` valide (déjà
ré-analysées, par ce script ou par `reanalyze_sold_deals.py`) — rejouable sans risque si
interrompu, et sûr à relancer.

Lancé en arrière-plan détaché depuis `run_once.py` (job potentiellement long, largement
au-delà du timeout de 10 min du step SSH de `deploy.yml`) : survit à la fin du job de
déploiement et à un redémarrage du service `guitare-hunter` (processus indépendant).
Log de progression : `backfill_sold_scores.log` à la racine du repo.
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
logger = logging.getLogger("backfill_sold_scores")

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


PID_FILE = os.path.join(os.getcwd(), 'backfill_sold_scores.pid')


def run():
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db_client = db_service.db
    if not db_client:
        logger.error("Erreur de connexion à Firebase.")
        return

    analyzer = DealAnalyzer(logger=logger)

    users_ref = db_client.collection('artifacts').document(APP_ID_TARGET).collection('users')
    users = list(users_ref.stream())
    logger.info(f"Backfill léger sur {len(users)} utilisateurs.")

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

        logger.info(f"Utilisateur {user_id} : {len(to_process)} annonces à backfiller.")
        processed = 0
        failed = 0

        for deal_id, data in to_process:
            listing_data = _build_listing_data(deal_id, data)
            try:
                analysis = analyzer.analyze_deal_light(listing_data, firestore_config=current_config)
                # Écrit UNIQUEMENT aiAnalysis (doc + index), sans timestamp= — voir docstring.
                repo.collection_ref.document(deal_id).update({'aiAnalysis': analysis})
                repo._update_deal_index(deal_id, ai_analysis=analysis)
                processed += 1
            except Exception as e:
                logger.error(f"Échec backfill {deal_id} (utilisateur {user_id}) : {e}")
                failed += 1

            if (processed + failed) % 50 == 0:
                logger.info(f"  Utilisateur {user_id} : {processed + failed}/{len(to_process)} traitées...")

            time.sleep(DELAY_BETWEEN_CALLS_SECONDS)

        logger.info(f"Utilisateur {user_id} terminé : {processed} backfillées, {failed} échecs.")
        grand_total_processed += processed
        grand_total_failed += failed

    logger.info(f"TERMINÉ. Total : {grand_total_processed} backfillées, {grand_total_failed} échecs.")


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
            logger.warning(f"Backfill déjà en cours (PID {existing_pid}), on ne relance pas.")
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
