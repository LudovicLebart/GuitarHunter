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
                    'type': 'user_root'
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

    def save_deal(self, deal_id, deal_data, analysis_data):
        try:
            status = "analyzed"
            if analysis_data.get('verdict') == 'REJECTED':
                status = "rejected"

            data = {**deal_data, "aiAnalysis": analysis_data, "timestamp": firestore.SERVER_TIMESTAMP, "status": status}
            self.collection_ref.document(deal_id).set(data, merge=True)
            logger.info(f"Saved deal '{deal_data.get('title', deal_id)}' with status '{status}'.")
        except Exception as e:
            logger.error(f"Firestore save failed for deal '{deal_id}': {e}", exc_info=True)

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
        """Atomically removes a command field from the user document."""
        try:
            self.user_ref.update({command_field: firestore.DELETE_FIELD})
            logger.info(f"Consumed command '{command_field}'.")
        except Exception as e:
            logger.error(f"Failed to consume command '{command_field}': {e}", exc_info=True)
