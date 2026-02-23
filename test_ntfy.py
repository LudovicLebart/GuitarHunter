import os
import sys
import firebase_admin
from firebase_admin import credentials, firestore

# Add current path to sys.path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import APP_ID_TARGET, USER_ID_TARGET, FIREBASE_KEY_PATH
from backend.notifications import NotificationService

def main():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(FIREBASE_KEY_PATH)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            print(f"Erreur d'initialisation Firebase: {e}")
            sys.exit(1)

    db = firestore.client()
    deals_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users').document(USER_ID_TARGET).collection('guitar_deals')

    deal_id_to_test = "1524240128676865"
    deal_doc = deals_ref.document(deal_id_to_test).get()

    if deal_doc.exists:
        deal_data = deal_doc.to_dict()
        deal_data['id'] = deal_doc.id
        print(f"Annonce trouvée dans FB: {deal_data.get('title')}")
    else:
        deal_data = {
            'id': 'mocked_id_12345',
            'title': 'Guitare de Test (Base Vide)',
            'price': 500,
            'link': 'https://www.facebook.com/marketplace/item/mocked_id_12345'
        }
        print("Aucune annonce trouvée, utilisation d'une annonce fictive.")
        
    # On définit un faux verdict 'PEPITE' pour forcer l'envoi
    analysis = {
        'verdict': 'PEPITE',
        'estimated_value': int(deal_data.get('price', 0)) + 300,
        'reasoning': 'Ceci est une notification de test générée par l\'IA pour vérifier la redirection vers le Frontend.'
    }
    
    NotificationService.notify_deal(deal_data, analysis)
    print(f"Notification envoyée pour l'annonce: {deal_data.get('title')} (ID: {deal_data['id']})")
    print(f"Lien cible: https://ludoviclebart.github.io/GuitarHunter/?dealId={deal_data['id']}")

if __name__ == "__main__":
    main()
