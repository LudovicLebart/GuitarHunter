import sys
import time
import threading
import logging
from firebase_admin import firestore

class FirestoreHandler(logging.Handler):
    def __init__(self, db_client, app_id, user_id):
        super().__init__()
        self.internal_logger = logging.getLogger('FirestoreHandlerInternal')
        self.internal_logger.propagate = False
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - [FirestoreHandler] - %(levelname)s - %(message)s'))
        self.internal_logger.addHandler(console_handler)
        self.internal_logger.setLevel(logging.INFO)

        if not db_client:
            self.db = None
            self.internal_logger.warning("Database client is not initialized. Handler will be disabled.")
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
        self.internal_logger.info("Handler initialized and flush thread started.")

    def emit(self, record):
        if not self.db:
            return
        try:
            log_entry = self.format(record)
            data = {
                'message': log_entry,
                'level': record.levelname,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'createdAt': time.time()
            }
            with self.buffer_lock:
                self.buffer.append(data)
        except Exception:
            self.handleError(record)

    def _flush_loop(self):
        while not self.stop_event.is_set():
            try:
                time.sleep(self.flush_interval)
                self.flush()
            except Exception as e:
                self.internal_logger.critical(f"Unhandled exception in flush loop: {e}", exc_info=True)

    def flush(self):
        if not self.db: return
        
        with self.buffer_lock:
            if not self.buffer:
                return
            logs_to_send = self.buffer[:]
            self.buffer = []
        
        if logs_to_send:
            self.internal_logger.info(f"Flushing {len(logs_to_send)} log(s) to Firestore.")
            batch_size = 450 
            for i in range(0, len(logs_to_send), batch_size):
                batch = self.db.batch()
                chunk = logs_to_send[i:i + batch_size]
                for log_data in chunk:
                    doc_ref = self.logs_ref.document()
                    batch.set(doc_ref, log_data)
                
                try:
                    batch.commit()
                except Exception as e:
                    self.internal_logger.error(f"Failed to flush logs to Firestore: {e}")

    def close(self):
        self.internal_logger.info("Close called. Stopping flush thread and performing final flush.")
        self.stop_event.set()
        if self.flush_thread.is_alive():
            self.flush_thread.join(timeout=1.0)
        self.flush()
        super().close()

def setup_logging(db_client, app_id, user_id, is_offline):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers = [] 

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(console_handler)

    if not is_offline:
        firestore_handler = FirestoreHandler(db_client, app_id, user_id)
        firestore_handler.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(firestore_handler)
        return firestore_handler
    else:
        logging.warning("Mode hors ligne, le logger Firestore n'est pas activé.")
        return None
