import sys
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# Mettre le dossier backend dans le path pour trouver la config
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_dir)

# Charger les variables d'environnement (.env)
load_dotenv(os.path.join(base_dir, '..', '.env'))
APP_ID_TARGET = os.getenv('APP_ID_TARGET')
USER_ID_TARGET = os.getenv('USER_ID_TARGET')

cred_path = os.path.join(base_dir, 'config', 'serviceAccountKey.json')
if not os.path.exists(cred_path):
    print(f"Erreur: Fichier de credentials introuvable a {cred_path}")
    sys.exit(1)

try:
    cred = credentials.Certificate(cred_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Erreur d'initialisation Firebase: {e}")
    sys.exit(1)

def fetch_deal(deal_id):
    """
    Recupere une annonce specifique depuis Firestore (Architecture Reelle).
    Chemin: artifacts/{APP_ID_TARGET}/users/{USER_ID_TARGET}/guitar_deals/{deal_id}
    """
    print(f"Recherche de l'annonce ID: {deal_id}")
    
    if not APP_ID_TARGET or not USER_ID_TARGET:
        print("Erreur: APP_ID_TARGET ou USER_ID_TARGET manquants dans l'environnement (.env)")
        return None
        
    try:
        base_ref = db.collection('artifacts').document(APP_ID_TARGET) \
                     .collection('users').document(USER_ID_TARGET) \
                     .collection('guitar_deals')
                     
        # 1. Recherche par ID de document (le plus courant)
        doc_ref = base_ref.document(str(deal_id))
        doc = doc_ref.get()
        
        if doc.exists:
            print("Annonce trouvee (ID de document)")
            return doc.to_dict()
            
        # 2. Recherche par champ 'id'
        deals = base_ref.where('id', '==', str(deal_id)).limit(1).get()
        if deals:
            print("Annonce trouvee (Champ 'id' string)")
            return deals[0].to_dict()
            
        print("Annonce introuvable dans la base de donnees.")
        return None
        
    except Exception as e:
        print(f"Erreur lors de la requete: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_deal.py <deal_id>")
        sys.exit(1)
        
    deal_id = sys.argv[1]
    data = fetch_deal(deal_id)
    
    if data:
        print("\n--- RESULTAT ---")
        print(f"Titre : {data.get('title')}")
        print(f"Prix  : {data.get('price')}")
        print(f"Lieu  : {data.get('location')}")
        print(f"URL   : {data.get('url')}")
        print("Desc  :", str(data.get('description'))[:150] + "...")
        print("\n--- ANALYSE IA ACTUELLE ---")
        print(json.dumps(data.get('aiAnalysis', {}), indent=2, ensure_ascii=False))
