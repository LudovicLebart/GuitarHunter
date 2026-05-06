import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

def check_commands():
    app_id = "c_5d118e719dbddbfc_index.html-217"
    user_id = "wbPlgZgkW2VcAl0a2l44UMSDTaG2"
    
    cert_path = "backend/config/serviceAccountKey.json"
    cred = credentials.Certificate(cert_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    
    # Path for commands: artifacts/{APP_ID}/users/{USER_ID}/commands
    commands_ref = db.collection("artifacts").document(app_id).collection("users").document(user_id).collection("commands")
    commands = commands_ref.order_by("createdAt", direction=firestore.Query.DESCENDING).limit(10).stream()
    
    print(f"--- Last 10 Commands for {user_id[:8]} ---")
    for cmd in commands:
        data = cmd.to_dict()
        print(f"ID: {cmd.id} | Type: {data.get('type')} | Status: {data.get('status')} | Error: {data.get('error')}")

if __name__ == "__main__":
    check_commands()
