import os
import firebase_admin
from firebase_admin import credentials, firestore

class DatabaseService:
    def __init__(self, firebase_key_path):
        self.db = None
        self.offline_mode = False
        self._initialize_firebase(firebase_key_path)

    def _initialize_firebase(self, key_path):
        """Initialise la connexion à Firestore."""
        if firebase_admin._apps:
            print("✅ Firebase déjà initialisé.")
            self.db = firestore.client()
            return

        try:
            if os.path.exists(key_path):
                cred = credentials.Certificate(key_path)
                print(f"🔑 Projet ID détecté : {cred.project_id}")
                firebase_admin.initialize_app(cred)
                self.db = firestore.client()
                print("✅ Firebase connecté avec succès (Database: Default).")
                
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
