import json
import firebase_admin
from firebase_admin import credentials, firestore
import os
import sys

KEY_PATH = "serviceAccountKey.json"
EXPECTED_PROJECT_ID = "guitarehunter-d6e35"

def verify():
    print("🔍 VÉRIFICATION DE LA CONFIGURATION FIREBASE")
    print("===========================================")
    
    # 1. Vérification de l'existence du fichier
    if not os.path.exists(KEY_PATH):
        print(f"❌ Fichier '{KEY_PATH}' introuvable à la racine !")
        print("👉 Veuillez télécharger la clé privée depuis la console Firebase > Paramètres du projet > Comptes de service.")
        return

    # 2. Vérification du contenu de la clé (Project ID)
    client_email = "Inconnu"
    try:
        with open(KEY_PATH, 'r') as f:
            key_data = json.load(f)
            project_id = key_data.get('project_id')
            client_email = key_data.get('client_email')
            
            print(f"📂 Analyse du fichier '{KEY_PATH}' :")
            print(f"   🔹 Project ID trouvé : {project_id}")
            print(f"   🔹 Compte de service : {client_email}")
            
            if project_id != EXPECTED_PROJECT_ID:
                print(f"\n❌ ERREUR CRITIQUE : Mismatch de Projet !")
                print(f"   Le fichier clé appartient au projet '{project_id}'")
                print(f"   Mais l'application React est configurée pour '{EXPECTED_PROJECT_ID}'")
                print("👉 SOLUTION : Téléchargez la clé JSON du BON projet (guitarehunter-d6e35).")
                return
            else:
                print(f"   ✅ Le Project ID correspond bien.")

    except Exception as e:
        print(f"❌ Erreur lors de la lecture du fichier JSON : {e}")
        return

    # 3. Test de connexion Firestore
    print("\n🔄 Test de connexion Firestore (Admin SDK)...")
    try:
        # Reset si déjà initialisé
        if firebase_admin._apps:
            for app_name in list(firebase_admin._apps):
                firebase_admin.delete_app(firebase_admin.get_app(app_name))

        cred = credentials.Certificate(KEY_PATH)
        firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        
        print("   ⏳ Tentative de lecture de la liste des collections...")
        # Cette opération nécessite les droits de lecture
        collections = list(db.collections())
        
        print(f"   ✅ SUCCÈS ! Connexion établie.")
        print(f"   📚 Collections trouvées : {[c.id for c in collections]}")
        
    except Exception as e:
        print(f"\n❌ ÉCHEC DE LA CONNEXION : {e}")
        print("\n💡 DIAGNOSTIC & SOLUTIONS :")
        print("1. Permissions IAM manquantes :")
        print(f"   Le compte de service '{client_email}' n'a pas les droits.")
        print("   👉 Allez dans la console Google Cloud > IAM et administration > IAM.")
        print(f"   👉 Cherchez '{client_email}' et ajoutez le rôle 'Firebase Admin' ou 'Cloud Datastore User'.")
        print("\n2. API désactivée :")
        print("   👉 Vérifiez que l'API 'Cloud Firestore API' est activée dans la console Google Cloud.")
        print("\n3. Horloge système :")
        print("   👉 Vérifiez que l'heure de votre PC est synchronisée (une erreur de temps invalide le token).")

if __name__ == "__main__":
    verify()
