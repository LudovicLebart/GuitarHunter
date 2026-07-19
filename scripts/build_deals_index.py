import os
import sys
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# Setup paths
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

cred_path = os.path.join(project_root, 'backend', 'config', 'serviceAccountKey.json')
if not os.path.exists(cred_path):
    print(f"Error: serviceAccountKey.json not found at {cred_path}.")
    sys.exit(1)

from config import APP_ID_TARGET, USER_ID_TARGET

sys.path.append('.')
try:
    from backend.scraping.parser import ListingParser
except ImportError:
    ListingParser = None

cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)
db = firestore.client()

def get_chunk_id(deal_id):
    import hashlib
    h = hashlib.md5(deal_id.encode('utf-8')).hexdigest()
    val = int(h[:8], 16)
    return f"chunk_{val % 20}"

def build_index():
    print(f"Building index for APP_ID='{APP_ID_TARGET}', USER_ID='{USER_ID_TARGET}'...")
    deals_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users').document(USER_ID_TARGET).collection('guitar_deals')
    
    # 1. Supprimer l'ancienne collection de deals_index pour repartir sur du propre
    print("Clearing old index documents...")
    old_index_docs = db.collection('artifacts').document(APP_ID_TARGET).collection('users').document(USER_ID_TARGET).collection('deals_index').stream()
    for doc in old_index_docs:
        doc.reference.delete()
    
    docs = deals_ref.stream()
    
    # Dictionnaires pour stocker les maps locales avant écriture
    chunks_map = {f"chunk_{i}": {} for i in range(20)}
    deals_updates = []
    count = 0
    
    for doc in docs:
        data = doc.to_dict()
        deal_id = doc.id
        
        status = data.get('status', 'analyzed')
        ai = data.get('aiAnalysis')
        if not isinstance(ai, dict):
            ai = {}
        verdict = ai.get('verdict', 'UNKNOWN')
        is_fav = data.get('isFavorite', False)
        price = data.get('price')
        classification = ai.get('classification')
        condition_score = ai.get('condition_score')
        also_pepite = ai.get('also_qualifies_pepite', False)
        title = data.get('title', '')
        
        # Note d'intérêt
        scores = [
            ai.get('deal_score'),
            ai.get('authenticity_score'),
            ai.get('condition_score'),
            ai.get('liquidity_score'),
            ai.get('restoration_interest_score')
        ]
        valid_scores = [s for s in scores if isinstance(s, (int, float))]
        interest_score = sum(valid_scores) / len(valid_scores) if valid_scores else None

        # Convert timestamp
        ts_val = data.get('timestamp')
        ts = None
        if hasattr(ts_val, 'timestamp'):
            ts = int(ts_val.timestamp())
        elif isinstance(ts_val, datetime):
            ts = int(ts_val.timestamp())
            
        pt = data.get('published_at_ts')
        if not pt and data.get('published_at_raw') and ListingParser:
            pt = ListingParser.parse_french_date(data.get('published_at_raw'))
            
        sold_val = data.get('soldAt')
        st = None
        if hasattr(sold_val, 'timestamp'):
            st = int(sold_val.timestamp())
        elif isinstance(sold_val, datetime):
            st = int(sold_val.timestamp())

        chunk_id = get_chunk_id(deal_id)
        entry = {
            "s": status,
            "v": verdict,
            "f": is_fav,
            "ap": also_pepite,
            "title": title,
            "h": chunk_id
        }
        if price is not None:
            entry["p"] = price
        if classification is not None:
            entry["c"] = classification
        if condition_score is not None:
            entry["cs"] = condition_score
        if interest_score is not None:
            entry["is"] = interest_score
        if ts is not None:
            entry["t"] = ts
        if pt is not None:
            entry["pt"] = pt
        if st is not None:
            entry["st"] = st
            
        chunks_map[chunk_id][deal_id] = entry
        
        # Enregistrer la mise à jour nécessaire pour injecter chunkId dans le document original
        if data.get('chunkId') != chunk_id:
            deals_updates.append((doc.reference, {"chunkId": chunk_id}))
            
        count += 1
        if count % 200 == 0:
            print(f"Processed {count} deals...")
            
    print(f"Total deals processed: {count}.")
    
    # 2. Écrire les 20 documents d'index
    print("Writing chunked index documents...")
    for chunk_id, deals_in_chunk in chunks_map.items():
        if deals_in_chunk:
            chunk_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users').document(USER_ID_TARGET).collection('deals_index').document(chunk_id)
            chunk_ref.set({"deals": deals_in_chunk})
            print(f"  - Written {len(deals_in_chunk)} entries to {chunk_id}")
            
    # 3. Mettre à jour chunkId sur les deals en batch (max 500 par batch)
    if deals_updates:
        print(f"Updating chunkId on {len(deals_updates)} deal documents...")
        batch = db.batch()
        batch_count = 0
        for ref, update_data in deals_updates:
            batch.update(ref, update_data)
            batch_count += 1
            if batch_count >= 400:
                batch.commit()
                print(f"  - Committed batch of {batch_count} updates")
                batch = db.batch()
                batch_count = 0
        if batch_count > 0:
            batch.commit()
            print(f"  - Committed final batch of {batch_count} updates")
            
    print("Index build and updates completed successfully!")

if __name__ == "__main__":
    build_index()
