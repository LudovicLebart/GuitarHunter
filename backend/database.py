import os
import firebase_admin
from firebase_admin import credentials, storage


class DatabaseService:
    """Connexion Firebase du bot : uniquement Firebase Storage (photos des annonces).

    Depuis la bascule vers Postgres (septembre 2026) les données ne sont plus dans Firestore ; ce service
    n'ouvre donc plus de client Firestore ni ne teste ses permissions — avant, un refus de permissions
    Firestore faisait passer TOUT le bot en mode hors-ligne au démarrage. Le bail de haute disponibilité
    (`backend/ha/`) ouvre lui-même son client Firestore.
    """

    def __init__(self, firebase_key_path, storage_bucket=None):
        self.bucket = None
        self.offline_mode = False
        self._initialize_firebase(firebase_key_path, storage_bucket)

    @property
    def db(self):
        """Client Firestore OUVERT À LA DEMANDE, pour les seuls scripts de migration/diagnostic
        historiques (`backend/scripts/`). Le bot et l'API ne l'utilisent plus : rien ne touche
        Firestore au démarrage."""
        from firebase_admin import firestore
        return None if self.offline_mode else firestore.client()

    def _initialize_firebase(self, key_path, storage_bucket):
        """Initialise la connexion à Firebase Storage."""
        if firebase_admin._apps:
            print("✅ Firebase déjà initialisé.")
            self.bucket = storage.bucket() if storage_bucket else None
            return

        try:
            if os.path.exists(key_path):
                cred = credentials.Certificate(key_path)
                print(f"[KEY] Projet ID detecte : {cred.project_id}")
                options = {'storageBucket': storage_bucket} if storage_bucket else {}
                firebase_admin.initialize_app(cred, options)
                self.bucket = storage.bucket() if storage_bucket else None
                print("[OK] Firebase connecte avec succes (Storage).")
            else:
                print(f"[WARN] Fichier {key_path} introuvable. Passage en MODE HORS-LIGNE.")
                self.offline_mode = True

        except Exception as e:
            print(f"[ERR] Erreur critique Firebase: {e}")
            self.offline_mode = True
