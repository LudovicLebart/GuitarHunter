import os
import sys
import logging
import random
from pathlib import Path
import requests

# Ajouter la racine du projet pour importer les modules partagés
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(name)s | %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path('dataset_phase1')

def fetch_image_to_disk(url, filepath):
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(resp.content)
            return True
    except Exception as e:
        logger.error(f"Erreur téléchargement: {e}")
    return False

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info("Connexion Firebase...")
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    if not db_service.db:
        logger.error("Erreur de connexion Firestore.")
        return
        
    logger.info("Récupération de toutes les annonces pour construire la distribution taxonomique...")
    users_ref = db_service.db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    users = list(users_ref.stream())
    
    # Dictionnaire : taxonomy_path -> liste de (deal_id, url)
    taxonomy_buckets = {}
    
    for user_doc in users:
        deals_ref = user_doc.reference.collection('guitar_deals')
        deals = list(deals_ref.limit(5000).stream())
        
        for deal in deals:
            data = deal.to_dict()
            taxo = data.get('classification')
            if not taxo or not isinstance(taxo, str):
                taxo = "Inconnu"
                
            urls = data.get('storageImageUrls', [])
            if not urls:
                continue
                
            if taxo not in taxonomy_buckets:
                taxonomy_buckets[taxo] = []
                
            # On prend juste la première image de l'annonce pour maximiser la diversité des guitares
            taxonomy_buckets[taxo].append((deal.id, urls[0]))
            
    # Mélanger les listes pour de l'aléatoire
    for taxo in taxonomy_buckets:
        random.shuffle(taxonomy_buckets[taxo])
        
    logger.info(f"Trouvé {len(taxonomy_buckets)} catégories taxonomiques distinctes.")
    
    # Sélection Round-Robin pour maximiser la diversité
    selected_images = []
    bucket_keys = list(taxonomy_buckets.keys())
    random.shuffle(bucket_keys)
    
    target_count = 150
    while len(selected_images) < target_count and any(taxonomy_buckets.values()):
        for taxo in bucket_keys:
            if len(selected_images) >= target_count:
                break
            if taxonomy_buckets[taxo]:
                selected_images.append((taxo, taxonomy_buckets[taxo].pop()))
                
    logger.info(f"Sélection de {len(selected_images)} images terminée. Début du téléchargement...")
    
    success_count = 0
    for taxo, (deal_id, url) in selected_images:
        # Nettoyer le nom de la taxonomie pour le nom de fichier
        safe_taxo = taxo.split('.')[-1].replace('/', '_').replace(' ', '').replace('\\', '_')
        if safe_taxo == "Inconnu":
            filename = f"Inconnu_{deal_id}.jpg"
        else:
            filename = f"{safe_taxo}_{deal_id}.jpg"
            
        filepath = OUTPUT_DIR / filename
        
        if fetch_image_to_disk(url, filepath):
            success_count += 1
            if success_count % 10 == 0:
                logger.info(f"Téléchargé {success_count}/{len(selected_images)} images...")
                
    logger.info(f"Terminé ! {success_count} images téléchargées dans {OUTPUT_DIR.absolute()}")
    
if __name__ == '__main__':
    main()
