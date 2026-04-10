import sys
import os
import argparse
import firebase_admin
from firebase_admin import auth, credentials, firestore

# Ajout du chemin racine pour l'import de config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from config import FIREBASE_KEY_PATH, APP_ID_TARGET

def setup_firebase():
    """Initialise Firebase Admin SDK."""
    if not firebase_admin._apps:
        if not os.path.exists(FIREBASE_KEY_PATH):
            print(f"❌ Erreur : Fichier de clé introuvable à {FIREBASE_KEY_PATH}")
            sys.exit(1)
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()

def list_users(delete_anonymous=False):
    """Liste les utilisateurs Firebase Auth et croise avec Firestore."""
    db = setup_firebase()
    
    print("\n🔍 Récupération de la liste des utilisateurs...")
    try:
        users = list(auth.list_users().iterate_all())
    except Exception as e:
        print(f"❌ Erreur lors de la lecture des utilisateurs : {e}")
        return

    print(f"\n{'#'*110}")
    print(f"{'UID':<32} | {'Email':<40} | {'Type':<10} | {'Bot Status':<12}")
    print(f"{'-'*110}")
    
    anonymous_uids = []
    total_users = len(users)
    
    for user in users:
        is_anonymous = not user.email
        uid = user.uid
        email = user.email or "[ANONYMOUS]"
        u_type = "ANONYME" if is_anonymous else "COMPTE"
        
        # Récupération du statut du bot dans Firestore
        # Chemin : artifacts/{APP_ID}/users/{UID}
        bot_status = "PAS DE DOC"
        try:
            user_doc = db.collection('artifacts').document(APP_ID_TARGET).collection('users').document(uid).get()
            if user_doc.exists:
                bot_status = user_doc.to_dict().get('botStatus', 'ACTIF')
        except Exception:
            bot_status = "ERREUR"

        print(f"{uid:<32} | {email:<40} | {u_type:<10} | {bot_status:<12}")
        
        if is_anonymous:
            anonymous_uids.append(uid)
            
    print(f"{'#'*110}")
    print(f"\n📊 Total : {total_users} utilisateurs ({len(anonymous_uids)} anonymes).")
    
    if delete_anonymous:
        if not anonymous_uids:
            print("\n✅ Aucun utilisateur anonyme à supprimer.")
            return
            
        print(f"\n⚠️  ATTENTION : {len(anonymous_uids)} utilisateurs anonymes vont être supprimés.")
        confirm = input(f"Confirmez-vous la suppression de ces {len(anonymous_uids)} comptes ? (OUI/non) : ")
        
        if confirm == 'OUI':
            print(f"🚀 Suppression de {len(anonymous_uids)} comptes...")
            # On supprime par lots de 1000 (limite Firebase)
            for i in range(0, len(anonymous_uids), 1000):
                batch = anonymous_uids[i:i + 1000]
                result = auth.delete_users(batch)
                print(f"   ✅ {result.success_count} réussis, {result.failure_count} échecs.")
            print("\n✨ Nettoyage terminé.")
        else:
            print("\n❌ Opération annulée.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Outil d'administration des utilisateurs Guitar Hunter")
    parser.add_argument("--delete-anonymous", action="store_true", help="Lance la procédure de suppression des comptes anonymes")
    args = parser.parse_args()
    
    list_users(delete_anonymous=args.delete_anonymous)
