import os
import firebase_admin
from firebase_admin import credentials, firestore, storage

class DatabaseService:
    def __init__(self, firebase_key_path, storage_bucket=None):
        self.db = None
        self.bucket = None
        self.offline_mode = False
        self._initialize_firebase(firebase_key_path, storage_bucket)

    def _initialize_firebase(self, key_path, storage_bucket):
        """Initialise la connexion à Firestore et Firebase Storage."""
        if firebase_admin._apps:
            print("✅ Firebase déjà initialisé.")
            self.db = firestore.client()
            self.bucket = storage.bucket() if storage_bucket else None
            return

        try:
            if os.path.exists(key_path):
                cred = credentials.Certificate(key_path)
                print(f"🔑 Projet ID détecté : {cred.project_id}")
                options = {'storageBucket': storage_bucket} if storage_bucket else {}
                firebase_admin.initialize_app(cred, options)
                self.db = firestore.client()
                self.bucket = storage.bucket() if storage_bucket else None
                print("✅ Firebase connecté avec succès (Database + Storage).")
                
                # Test de permissions
                self._check_permissions()
            else:
                print(f"⚠️ Fichier {key_path} introuvable. Passage en MODE HORS-LIGNE.")
                self.offline_mode = True

        except Exception as e:
            print(f"❌ Erreur critique Firebase: {e}")
            self.offline_mode = True

    def _check_permissions(self):
        """Vérifie les permissions de lecture sur la base de données."""
        try:
            list(self.db.collections())
            print("✅ Permissions de lecture confirmées sur la base.")
        except Exception as e:
            print(f"❌ ERREUR PERMISSIONS : {e}")
            print("👉 Le compte de service n'a pas les droits. Passage en MODE HORS-LIGNE (Simulation).")
            self.offline_mode = True
