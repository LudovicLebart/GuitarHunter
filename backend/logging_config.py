import sys
import time
import threading
import logging
import datetime
from firebase_admin import firestore

class FirestoreHandler(logging.Handler):
    def __init__(self, db_client, app_id, user_id):
        super().__init__()
        # On garde le logger interne mais on ajoute des prints de secours
        self.internal_logger = logging.getLogger('FirestoreHandlerInternal')
        self.internal_logger.propagate = False
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - [FirestoreHandler] - %(levelname)s - %(message)s'))
        self.internal_logger.addHandler(console_handler)
        self.internal_logger.setLevel(logging.INFO)

        if not db_client:
            self.db = None
            print("DEBUG: FirestoreHandler - DB Client is None!", flush=True)
            return
        self.db = db_client
        self.logs_ref = self.db.collection('artifacts').document(app_id) \
            .collection('users').document(user_id).collection('logs')
        
        self.buffer = []
        self.buffer_lock = threading.Lock()
        self.flush_interval = 3.0
        self.stop_event = threading.Event()
        self.flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self.flush_thread.start()
        print("DEBUG: FirestoreHandler initialized and thread started.", flush=True)

    def emit(self, record):
        if not self.db:
            return
        try:
            log_entry = self.format(record)
            
            # Calcul de la date d'expiration (TTL) : 3 jours par défaut
            expire_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3)
            
            data = {
                'message': log_entry,
                'level': record.levelname,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'createdAt': time.time(),
                'expireAt': expire_at  # Champ pour le TTL Firestore
            }
            with self.buffer_lock:
                self.buffer.append(data)
            # print(f"DEBUG: Log buffered: {record.levelname}", flush=True) # Trop verbeux, décommenter si nécessaire
        except Exception as e:
            print(f"ERROR: FirestoreHandler emit failed: {e}", flush=True)
            self.handleError(record)

    def _flush_loop(self):
        print("DEBUG: Flush loop started.", flush=True)
        while not self.stop_event.is_set():
            try:
                time.sleep(self.flush_interval)
                self.flush()
            except Exception as e:
                print(f"CRITICAL: Exception in flush loop: {e}", flush=True)
                self.internal_logger.critical(f"Unhandled exception in flush loop: {e}", exc_info=True)

    def flush(self):
        if not self.db: return
        
        with self.buffer_lock:
            if not self.buffer:
                return
            logs_to_send = self.buffer[:]
            self.buffer = []
        
        if logs_to_send:
            print(f"DEBUG: Flushing {len(logs_to_send)} logs to Firestore...", flush=True)
            batch_size = 450 
            for i in range(0, len(logs_to_send), batch_size):
                batch = self.db.batch()
                chunk = logs_to_send[i:i + batch_size]
                for log_data in chunk:
                    doc_ref = self.logs_ref.document()
                    batch.set(doc_ref, log_data)
                
                try:
                    batch.commit()
                    print("DEBUG: Batch commit successful.", flush=True)
                except Exception as e:
                    print(f"ERROR: Batch commit failed: {e}", flush=True)
                    self.internal_logger.error(f"Failed to flush logs to Firestore: {e}")

    def close(self):
        print("DEBUG: Closing FirestoreHandler...", flush=True)
        self.stop_event.set()
        if self.flush_thread.is_alive():
            self.flush_thread.join(timeout=1.0)
        self.flush()
        super().close()

def setup_logging(db_client, app_id, user_id, is_offline):
    print("DEBUG: Initialisation du logging...", flush=True)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(console_handler)

    firestore_handler = None
    if not is_offline:
        try:
            firestore_handler = FirestoreHandler(db_client, app_id, user_id)
            firestore_handler.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(firestore_handler)
            print("DEBUG: Firestore logger ajouté au root logger.", flush=True)
        except Exception as e:
            print(f"ERROR: Echec de l'initialisation du FirestoreHandler: {e}", flush=True)
            logging.error(f"Echec de l'initialisation du FirestoreHandler: {e}", exc_info=True)
    else:
        logging.warning("Mode hors ligne, le logger Firestore n'est pas activé.")
        print("DEBUG: Mode hors ligne.", flush=True)

    return firestore_handler
