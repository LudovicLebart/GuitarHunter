import firebase_admin
from firebase_admin import credentials, firestore
import sys

# Configuration
KEY_PATH = "serviceAccountKey.json"
# DB_NAME = "guitarhunterdb" # SUPPRIMÉ pour utiliser la base par défaut

# --- CONSTANTES CIBLES (DOIVENT MATCHER MAIN.PY et APP.JSX) ---
TARGET_APP_ID = "c_5d118e719dbddbfc_index.html-217"
TARGET_USER_ID = "00737242777130596039"

def check_database():
    print(f"--- DIAGNOSTIC FIREBASE: DEFAULT DATABASE ---")
    
    # 1. Vérification du fichier de clé
    try:
        cred = credentials.Certificate(KEY_PATH)
        print(f"✅ Clé de service chargée: {cred.project_id}")
    except Exception as e:
        print(f"❌ Erreur chargement clé: {e}")
        return

    # 2. Connexion à la base spécifique
    try:
        if firebase_admin._apps:
            for app_name in list(firebase_admin._apps):
                firebase_admin.delete_app(firebase_admin.get_app(app_name))

        firebase_admin.initialize_app(cred)
        
        print(f"🔄 Connexion à la base par défaut...")
        db = firestore.client() # Plus de database_id='guitarhunterdb'
        
        # Test simple de connexion
        list(db.collections()) 
        print(f"✅ Connexion établie !")

        # ---------------------------------------------------------
        # DIAGNOSTIC CIBLÉ (Même logique que le React)
        # ---------------------------------------------------------
        print(f"\n🔍 ANALYSE DU CHEMIN CIBLE :")
        print(f"   Path: artifacts/{TARGET_APP_ID}/users/{TARGET_USER_ID}/guitar_deals")

        # A. Vérification App Root
        app_ref = db.collection('artifacts').document(TARGET_APP_ID)
        app_snap = app_ref.get()
        
        if app_snap.exists:
            print(f"   ✅ [1/3] Dossier App Root ({TARGET_APP_ID}) : TROUVÉ")
        else:
            print(f"   ❌ [1/3] Dossier App Root ({TARGET_APP_ID}) : INEXISTANT")
            print("      -> Le script main.py n'a probablement pas créé ce dossier parent.")

        # B. Vérification User Root
        user_ref = app_ref.collection('users').document(TARGET_USER_ID)
        user_snap = user_ref.get()

        if user_snap.exists:
            print(f"   ✅ [2/3] Dossier User Root ({TARGET_USER_ID}) : TROUVÉ")
        else:
            print(f"   ❌ [2/3] Dossier User Root ({TARGET_USER_ID}) : INEXISTANT")
            print("      -> Le dossier utilisateur parent manque (c'est souvent la cause des problèmes d'affichage).")

        # C. Vérification Collection Deals
        deals_ref = user_ref.collection('guitar_deals')
        deals_docs = list(deals_ref.stream())

        if deals_docs:
            print(f"   ✅ [3/3] Collection Deals : {len(deals_docs)} documents trouvés")
            print("\n   📋 Détail des documents :")
            for doc in deals_docs:
                data = doc.to_dict()
                title = data.get('title', 'Sans titre')
                price = data.get('price', 'N/A')
                print(f"      - ID: {doc.id} | {title} ({price} $)")
        else:
            print(f"   ⚠️ [3/3] Collection Deals : VIDE")
            print("      -> Le chemin existe peut-être, mais aucune annonce n'a été enregistrée.")

    except Exception as e:
        print(f"❌ ERREUR CRITIQUE : {e}")

if __name__ == "__main__":
    check_database()