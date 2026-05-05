import os
import firebase_admin
from firebase_admin import credentials, firestore

# Configuration
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIREBASE_KEY_PATH = os.path.join(ROOT_DIR, "backend", "config", "serviceAccountKey.json")

APP_ID = "c_5d118e719dbddbfc_index.html-217"


cred = credentials.Certificate(FIREBASE_KEY_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()

def list_users():
    print(f"Scanning artifacts/{APP_ID}/users...")
    users_ref = db.collection('artifacts').document(APP_ID).collection('users')
    docs = users_ref.stream()
    count = 0
    for doc in docs:
        print(f"- User Found: {doc.id}")
        count += 1
    print(f"Total: {count} users in Firestore.")

if __name__ == "__main__":
    list_users()
