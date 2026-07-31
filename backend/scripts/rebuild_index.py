import sys
import logging
from datetime import datetime, timezone

sys.path.insert(0, '.')

from config import APP_ID_TARGET, USER_IDS_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService
from backend.repository import FirestoreRepository

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger("rebuild_index")

def rebuild():
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db_client = db_service.db
    if not db_client:
        logger.error("Erreur de connexion à Firebase.")
        return

    # Récupérer tous les utilisateurs dynamiquement
    users_ref = db_client.collection('artifacts').document(APP_ID_TARGET).collection('users')
    users = list(users_ref.stream())
    logger.info(f"Trouvé {len(users)} utilisateurs à réindexer.")

    for user_doc in users:
        user_id = user_doc.id
        logger.info(f"Reconstruction de l'index pour l'utilisateur {user_id}...")
        repo = FirestoreRepository(db_client, APP_ID_TARGET, user_id)
        
        query = repo.collection_ref.select([
            'status', 'aiAnalysis', 'isFavorite', 'title', 'price', 
            'published_at_ts', 'soldAt', 'location', 'initialModelUsed', 
            'storageImageUrls', 'imageUrls', 'timestamp'
        ]).order_by('__name__').limit(500)
        
        count = 0
        last_doc = None
        
        while True:
            current_query = query.start_after(last_doc) if last_doc else query
            docs = list(current_query.stream())
            if not docs:
                break
                
            for deal_doc in docs:
                deal_data = deal_doc.to_dict()
                deal_id = deal_doc.id
                
                status = deal_data.get('status', 'analyzed')
                ai_analysis = deal_data.get('aiAnalysis', {})
                is_favorite = deal_data.get('isFavorite', False)
                title = deal_data.get('title', '')
                price = deal_data.get('price')
                published_at = deal_data.get('published_at_ts')
                sold_at = deal_data.get('soldAt')
                location = deal_data.get('location')
                initial_model = deal_data.get('initialModelUsed')
                image_url = (deal_data.get('storageImageUrls') or [None])[0] or (deal_data.get('imageUrls') or [None])[0]
                
                ts_obj = deal_data.get('timestamp')
                
                repo._update_deal_index(
                    deal_id,
                    status=status,
                    ai_analysis=ai_analysis,
                    is_favorite=is_favorite,
                    timestamp=ts_obj,
                    title=title,
                    price=price,
                    published_at=published_at,
                    sold_at=sold_at,
                    location=location,
                    initial_model=initial_model,
                    image_url=image_url
                )
                count += 1
                if count % 50 == 0:
                    logger.info(f"  {count} annonces réindexées...")
                    
            last_doc = docs[-1]
                
        logger.info(f"Terminé pour l'utilisateur {user_id} : {count} annonces réindexées au total.")

if __name__ == '__main__':
    rebuild()
