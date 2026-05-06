import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

def list_logs():
    app_id = "c_5d118e719dbddbfc_index.html-217"
    user_id = "wbPlgZgkW2VcAl0a2l44UMSDTaG2"
    
    # Init Firebase
    cert_path = "backend/config/serviceAccountKey.json"
    if not os.path.exists(cert_path):
        print(f"Error: {cert_path} not found")
        return

    cred = credentials.Certificate(cert_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    # Path for logs: artifacts/{APP_ID}/users/{USER_ID}/logs
    logs_ref = db.collection("artifacts").document(app_id).collection("users").document(user_id).collection("logs")
    logs = logs_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(50).stream()
    
    print(f"--- Last 50 Logs for {user_id[:8]} ---")
    for log in reversed(list(logs)): # Show in chronological order
        data = log.to_dict()
        print(f"[{data.get('level')}] {data.get('message')}")

if __name__ == "__main__":
    list_logs()
