import numpy as np
import cv2
import requests
import logging

logger = logging.getLogger(__name__)

def fetch_image(url):
    """Télécharge l'image depuis l'URL Firebase Storage et la décode avec OpenCV."""
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"Impossible de récupérer l'image à l'URL {url}")
            return None
            
        nparr = np.frombuffer(resp.content, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
    except Exception as e:
        logger.error(f"Erreur de téléchargement: {e}")
        return None

def get_deal_images(db_client, app_id, limit=None):
    """
    Générateur itératif des URLs d'images depuis Firestore.
    Parcourt tous les utilisateurs de l'application et yield les URLs.
    """
    users_ref = db_client.collection('artifacts').document(app_id).collection('users')
    users = list(users_ref.stream())
    
    yielded_count = 0
    
    for user_doc in users:
        deals_ref = user_doc.reference.collection('guitar_deals')
        # Limite haute pour éviter les requêtes trop lourdes d'un coup
        deals = list(deals_ref.limit(5000).stream()) 
        
        for deal in deals:
            data = deal.to_dict()
            urls = data.get('storageImageUrls', [])
            
            for idx, url in enumerate(urls):
                if limit and yielded_count >= limit:
                    return
                
                yield f"{deal.id}_{idx}", url
                yielded_count += 1
