import logging
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

logger = logging.getLogger(__name__)

class FirestoreRepository:
    def __init__(self, db, app_id, user_id):
        if not db:
            raise ValueError("Database client is not initialized.")
        self.db = db
        self.app_id = app_id
        self.user_id = user_id

        # Firestore References
        self.user_ref = self.db.collection('artifacts').document(self.app_id) \
            .collection('users').document(self.user_id)
        
        self.collection_ref = self.user_ref.collection('guitar_deals')
        
        self.cities_ref = self.user_ref.collection('cities')
        
        self.commands_ref = self.user_ref.collection('commands')

    def ensure_initial_structure(self, initial_config):
        logger.info("Verifying Firestore structure...")
        try:
            app_ref = self.db.collection('artifacts').document(self.app_id)
            if not app_ref.get().exists:
                app_ref.set({'created_at': firestore.SERVER_TIMESTAMP, 'type': 'app_root'})
                logger.info(f"Created root document for app: {self.app_id}")

            if not self.user_ref.get().exists:
                logger.info(f"User document for {self.user_id} not found. Creating with initial config.")
                self.user_ref.set({
                    **initial_config,
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'type': 'user_root',
                    'botStatus': 'idle'
                })
            else:
                logger.info("User document already exists.")
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

    def update_deal_status(self, deal_id, status, error_message=None):
        """Met à jour uniquement le statut d'une annonce, avec un message d'erreur optionnel."""
        try:
            update_data = {'status': status}
            if error_message:
                update_data['aiAnalysis'] = firestore.firestore.ArrayUnion([{'error': error_message, 'timestamp': firestore.SERVER_TIMESTAMP}])
            
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
        try:
            return self.cities_ref.stream()
        except Exception as e:
            logger.error(f"Failed to get cities: {e}", exc_info=True)
            return []

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
            
    def consume_command(self, command_field):
        try:
            self.user_ref.update({command_field: firestore.DELETE_FIELD})
            logger.info(f"Consumed command '{command_field}'.")
        except Exception as e:
            logger.error(f"Failed to consume command '{command_field}': {e}", exc_info=True)

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
        docs = self.user_ref.collection('logs').limit(500).stream()
        deleted_count = 0
        
        while True:
            batch = self.db.batch()
            doc_count_in_batch = 0
            for doc in docs:
                batch.delete(doc.reference)
                doc_count_in_batch += 1
            
            if doc_count_in_batch == 0:
                break
            
            batch.commit()
            deleted_count += doc_count_in_batch
            logger.info(f"Deleted {deleted_count} logs so far...")
            
            docs = self.user_ref.collection('logs').limit(500).stream()
            
        return deleted_count
