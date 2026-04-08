import uuid
import logging
import requests
from datetime import datetime, timezone, timedelta
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

logger = logging.getLogger(__name__)

class FirestoreRepository:
    def __init__(self, db, app_id, user_id, bucket=None):
        if not db:
            raise ValueError("Database client is not initialized.")
        self.db = db
        self.app_id = app_id
        self.user_id = user_id
        self._bucket = bucket

        # Firestore References
        self.user_ref = self.db.collection('artifacts').document(self.app_id) \
            .collection('users').document(self.user_id)

        self.collection_ref = self.user_ref.collection('guitar_deals')

        # Catalogue de villes partagé entre tous les utilisateurs.
        # DocId = Facebook city ID (unique). Contient: name, id, latitude, longitude.
        self.shared_cities_ref = self.db.collection('artifacts').document(self.app_id) \
            .collection('cities')

        # Préférences de villes par utilisateur.
        # DocId = Facebook city ID (même que dans shared_cities_ref).
        # Contient uniquement: isScannable (bool).
        self.user_cities_prefs_ref = self.user_ref.collection('cities')

        self.commands_ref = self.user_ref.collection('commands')

        self.logs_ref = self.user_ref.collection('logs')

    def ensure_initial_structure(self, initial_config):
        logger.info("Verifying Firestore structure...")
        try:
            app_ref = self.db.collection('artifacts').document(self.app_id)
            if not app_ref.get().exists:
                app_ref.set({'created_at': firestore.SERVER_TIMESTAMP, 'type': 'app_root'})
                logger.info(f"Created root document for app: {self.app_id}")

            user_doc = self.user_ref.get()
            if not user_doc.exists:
                logger.info(f"User document for {self.user_id} not found. Creating with initial config.")
                self.user_ref.set({
                    **initial_config,
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'type': 'user_root',
                    'botStatus': 'idle'
                })
            else:
                logger.info("User document already exists. Config preserved.")
                # DEBUG: Afficher la config actuelle pour vérifier si elle est écrasée
                current_data = user_doc.to_dict()
                analysis_config = current_data.get('analysisConfig', {})
                prompt_len = len(analysis_config.get('mainAnalysisPrompt', []))
                logger.info(f"DEBUG: Current config in Firestore - Prompt length: {prompt_len}")

        except Exception as e:
            logger.error(f"Failed to ensure Firestore structure: {e}", exc_info=True)

    def get_deal_by_id(self, deal_id):
        try:
            doc_snap = self.collection_ref.document(deal_id).get()
            return doc_snap.to_dict() if doc_snap.exists else None
        except Exception as e:
            logger.error(f"Failed to get deal by ID '{deal_id}': {e}", exc_info=True)
            return None

    def create_new_deal(self, deal_id, deal_data, analysis_data):
        """Crée un nouveau document pour une annonce."""
        try:
            status = "analyzed"
            if analysis_data.get('verdict') == 'REJECTED':
                status = "rejected"

            data = {**deal_data, "aiAnalysis": analysis_data, "timestamp": firestore.SERVER_TIMESTAMP, "status": status}
            self.collection_ref.document(deal_id).set(data)
            logger.info(f"Created new deal '{deal_data.get('title', deal_id)}' with status '{status}'.")
        except Exception as e:
            logger.error(f"Firestore create failed for deal '{deal_id}': {e}", exc_info=True)

    def update_deal_analysis(self, deal_id, analysis_data):
        """Met à jour l'analyse d'une annonce existante."""
        try:
            status = "analyzed"
            if analysis_data.get('verdict') == 'REJECTED':
                status = "rejected"
            
            update_data = {
                "aiAnalysis": analysis_data,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "status": status
            }
            self.collection_ref.document(deal_id).update(update_data)
            logger.info(f"Updated analysis for deal '{deal_id}' with status '{status}'.")
        except Exception as e:
            logger.error(f"Firestore update failed for deal '{deal_id}': {e}", exc_info=True)

    def update_deal_data_and_analysis(self, deal_id, deal_data, analysis_data):
        """Met à jour les données complètes de l'annonce (ex: baisse de prix) et son analyse."""
        try:
            status = "analyzed"
            if analysis_data.get('verdict') == 'REJECTED':
                status = "rejected"
                
            # Fusionner les nouvelles métadonnées de l'annonce (y compris le nouveau prix)
            update_data = {
                **deal_data,
                "aiAnalysis": analysis_data,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "status": status
            }
            
            self.collection_ref.document(deal_id).update(update_data)
            logger.info(f"Updated full data and analysis for deal '{deal_id}' (e.g. Price drop). Status: '{status}'.")
        except Exception as e:
            logger.error(f"Firestore full update failed for deal '{deal_id}': {e}", exc_info=True)

    def update_deal_status(self, deal_id, status, error_message=None):
        """Met à jour uniquement le statut d'une annonce, avec un message d'erreur optionnel."""
        try:
            update_data = {'status': status}
            if error_message:
                # Utilisation de datetime.now() au lieu de SERVER_TIMESTAMP pour ArrayUnion
                update_data['aiAnalysis'] = firestore.firestore.ArrayUnion([{'error': error_message, 'timestamp': datetime.now()}])
            
            self.collection_ref.document(deal_id).update(update_data)
            logger.info(f"Updated status for deal '{deal_id}' to '{status}'.")
        except Exception as e:
            logger.error(f"Failed to update status for deal '{deal_id}': {e}", exc_info=True)

    def get_user_config(self):
        try:
            doc = self.user_ref.get()
            return doc.to_dict() if doc.exists else None
        except Exception as e:
            logger.error(f"Failed to get user config: {e}", exc_info=True)
            return None
            
    def get_cities(self):
        """Retourne les villes activées (isScannable=True) pour cet utilisateur.
        Fusionne le catalogue partagé avec les préférences user.
        Retourne une liste de dicts (name, id, latitude, longitude, isScannable).
        """
        try:
            catalog = {doc.id: doc.to_dict() for doc in self.shared_cities_ref.stream()}
            user_prefs = {doc.id: doc.to_dict() for doc in self.user_cities_prefs_ref.stream()}

            result = []
            for city_id, city_data in catalog.items():
                pref = user_prefs.get(city_id, {})
                if pref.get('isScannable', False):
                    result.append({**city_data, 'isScannable': True})

            return result
        except Exception as e:
            logger.error(f"Failed to get cities: {e}", exc_info=True)
            return []

    def get_all_catalog_cities(self):
        """Retourne toutes les villes du catalogue partagé (dict city_id → data)."""
        try:
            return {doc.id: doc.to_dict() for doc in self.shared_cities_ref.stream()}
        except Exception as e:
            logger.error(f"Failed to get catalog cities: {e}", exc_info=True)
            return {}

    def add_city_to_catalog(self, city_id, city_data):
        """Écrit une ville dans le catalogue partagé (upsert sur le Facebook city ID)."""
        try:
            self.shared_cities_ref.document(str(city_id)).set(city_data, merge=True)
            logger.info(f"Ville '{city_data.get('name')}' (id={city_id}) ajoutée au catalogue partagé.")
        except Exception as e:
            logger.error(f"Failed to add city {city_id} to shared catalog: {e}", exc_info=True)
            raise

    def set_city_user_pref(self, city_id, is_scannable):
        """Crée ou met à jour la préférence isScannable d'une ville pour cet utilisateur."""
        try:
            self.user_cities_prefs_ref.document(str(city_id)).set(
                {'isScannable': is_scannable}, merge=True
            )
            logger.info(f"Préférence ville {city_id} pour user {self.user_id[:8]}: isScannable={is_scannable}")
        except Exception as e:
            logger.error(f"Failed to set city pref for {city_id}: {e}", exc_info=True)
            raise

    def get_active_listings(self):
        try:
            return self.collection_ref.where(filter=FieldFilter('status', '!=', 'rejected')).stream()
        except Exception as e:
            logger.error(f"Failed to get active listings: {e}", exc_info=True)
            return []
            
    def delete_listing(self, listing_id):
        try:
            self.collection_ref.document(listing_id).delete()
            logger.info(f"Deleted listing '{listing_id}'.")
        except Exception as e:
            logger.error(f"Failed to delete listing '{listing_id}': {e}", exc_info=True)

    def get_retry_queue_listings(self):
        try:
            return self.collection_ref.where(filter=FieldFilter('status', '==', 'retry_analysis')).stream()
        except Exception as e:
            logger.error(f"Failed to get retry queue: {e}", exc_info=True)
            return []

    def mark_all_for_reanalysis(self):
        logger.info("Marking all active listings for re-analysis.")
        try:
            docs = self.get_active_listings()
            batch = self.db.batch()
            count = 0
            for doc in docs:
                batch.update(doc.reference, {'status': 'retry_analysis'})
                count += 1
            if count > 0:
                batch.commit()
                logger.info(f"Marked {count} listings for re-analysis.")
            return count
        except Exception as e:
            logger.error(f"Failed to mark listings for re-analysis: {e}", exc_info=True)
            return 0
            
    def update_bot_status(self, status):
        try:
            self.user_ref.update({'botStatus': status})
            logger.info(f"Updated bot status to '{status}'.")
        except Exception as e:
            logger.error(f"Failed to update bot status to '{status}': {e}", exc_info=True)

    def get_pending_commands(self):
        try:
            return self.commands_ref.where(filter=FieldFilter('status', '==', 'pending')).stream()
        except Exception as e:
            logger.error(f"Failed to get pending commands: {e}", exc_info=True)
            return []

    def mark_command_completed(self, command_id):
        try:
            self.commands_ref.document(command_id).update({
                'status': 'completed',
                'completedAt': firestore.SERVER_TIMESTAMP
            })
            logger.info(f"Command '{command_id}' marked as completed.")
        except Exception as e:
            logger.error(f"Failed to mark command '{command_id}' as completed: {e}", exc_info=True)

    def mark_command_failed(self, command_id, error_message):
        try:
            self.commands_ref.document(command_id).update({
                'status': 'failed',
                'error': error_message,
                'completedAt': firestore.SERVER_TIMESTAMP
            })
            logger.info(f"Command '{command_id}' marked as failed: {error_message}")
        except Exception as e:
            logger.error(f"Failed to mark command '{command_id}' as failed: {e}", exc_info=True)

    def delete_all_logs(self):
        deleted_count = 0
        max_iterations = 100  # Sécurité : max 100 * 500 = 50,000 logs
        iterations = 0

        logger.info("Démarrage de la suppression de tous les logs...")

        while iterations < max_iterations:
            iterations += 1
            # On force la consommation du stream dans une liste avant de traiter
            docs = list(self.logs_ref.limit(500).stream())

            if not docs:
                logger.info(f"Aucun log supplémentaire trouvé. Arrêt de la boucle (itération {iterations}).")
                break

            batch = self.db.batch()
            for doc in docs:
                batch.delete(doc.reference)

            try:
                batch.commit()
                deleted_count += len(docs)
                logger.info(f"Batch supprimé : {len(docs)} logs. Total supprimé : {deleted_count}")
            except Exception as e:
                logger.error(f"Erreur lors du commit du batch de suppression des logs : {e}", exc_info=True)
                raise
        return deleted_count

    def upload_images_to_storage(self, image_urls, deal_id):
        """
        Télécharge les images depuis leurs URLs d'origine et les stocke
        de manière pérenne dans Firebase Storage.
        Retourne la liste des URLs Firebase stables.
        """
        if not self._bucket:
            return []
        
        stable_urls = []
        for i, url in enumerate(image_urls):
            if not url:
                continue
            try:
                response = requests.get(url, timeout=10)
                if response.status_code != 200:
                    logger.warning(f"Image {i+1}/{len(image_urls)} non téléchargeable (HTTP {response.status_code}) pour deal {deal_id}.")
                    continue
                
                blob_path = f"deals/{deal_id}/{i}_{uuid.uuid4().hex[:8]}.jpg"
                blob = self._bucket.blob(blob_path)
                blob.upload_from_string(response.content, content_type='image/jpeg')
                blob.make_public()
                stable_urls.append(blob.public_url)
                logger.info(f"   ☁️ Image {i+1} uploadée pour deal {deal_id}: {blob_path}")
            except Exception as e:
                logger.warning(f"Erreur upload image {i+1} pour deal {deal_id}: {e}")
        
        return stable_urls

    def delete_deal_images(self, deal_id):
        """
        Supprime toutes les images d'un deal dans Firebase Storage et
        efface le champ storageImageUrls dans Firestore.
        """
        if not self._bucket:
            logger.warning(f"delete_deal_images: Pas de bucket Storage configuré pour deal {deal_id}.")
            return 0

        deleted_count = 0
        try:
            # 1. Supprimer les fichiers dans Storage
            prefix = f"deals/{deal_id}/"
            blobs = list(self._bucket.list_blobs(prefix=prefix))
            if blobs:
                for blob in blobs:
                    blob.delete()
                deleted_count = len(blobs)
                logger.info(f"🗑️ {deleted_count} image(s) supprimée(s) du Storage pour deal {deal_id}.")

            # 2. Effacer le champ dans Firestore
            self.collection_ref.document(deal_id).update({'storageImageUrls': firestore.DELETE_FIELD})
            return deleted_count
        except Exception as e:
            logger.error(f"Erreur lors de la suppression des images pour deal {deal_id}: {e}", exc_info=True)
            return 0

    def purge_rejected_images(self, retention_days=30, rejection_verdicts=None):
        """
        Politique de cycle de vie : supprime les images Firebase Storage
        des deals dont le verdict est un rejet et dont le timestamp est
        plus ancien que `retention_days` jours.
        
        Cible les verdicts de rejet (ex: BAD_DEAL, REJECTED_ITEM, REJECTED_SERVICE)
        qui ont status `analyzed` (rejets modernes) ET le legacy status `rejected`.
        """
        if not self._bucket:
            logger.warning("purge_rejected_images: Pas de bucket Storage configuré.")
            return 0

        # Verdicts de rejet par défaut si aucun fourni
        if rejection_verdicts is None:
            rejection_verdicts = ["BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE", "INCOMPLETE_DATA", "REJECTED"]

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        purged_count = 0

        try:
            # Requête sur le champ imbriqué aiAnalysis.verdict
            # Firestore supporte les champs imbriqués avec FieldFilter
            docs = self.collection_ref.where(
                filter=FieldFilter('aiAnalysis.verdict', 'in', rejection_verdicts)
            ).stream()

            for doc in docs:
                data = doc.to_dict()
                # Utilisation du timestamp Firestore
                ts = data.get('timestamp')
                if not ts:
                    continue
                
                # Convertir le timestamp Firestore (aware) pour pouvoir comparer
                if hasattr(ts, 'tzinfo') and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)

                if ts <= cutoff:
                    # Suppression de tous les blobs pour ce deal
                    prefix = f"deals/{doc.id}/"
                    blobs = list(self._bucket.list_blobs(prefix=prefix))
                    if blobs:
                        for blob in blobs:
                            blob.delete()
                        # Nettoyage du champ dans Firestore
                        doc.reference.update({'storageImageUrls': firestore.DELETE_FIELD})
                        purged_count += len(blobs)
                        logger.info(f"🗑️ {len(blobs)} image(s) purgée(s) pour deal rejeté {doc.id} (ancien de {retention_days}j+).")
        except Exception as e:
            logger.error(f"Erreur lors de la purge des images: {e}", exc_info=True)

        logger.info(f"Purge lifecycle terminée. {purged_count} image(s) supprimée(s).")
        return purged_count
