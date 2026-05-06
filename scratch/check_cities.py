import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

def list_cities():
    app_id = "c_5d118e719dbddbfc_index.html-217" # APP_ID_TARGET from .env
    
    # Init Firebase
    cert_path = "backend/config/serviceAccountKey.json"
    if not os.path.exists(cert_path):
        print(f"Error: {cert_path} not found")
        return

    cred = credentials.Certificate(cert_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    # Path for catalog cities: artifacts/{APP_ID}/cities
    catalog_ref = db.collection("artifacts").document(app_id).collection("cities")
    cities = catalog_ref.stream()
    
    print("--- Cities in Catalog ---")
    for city in cities:
        data = city.to_dict()
        print(f"ID: {city.id} | Name: {data.get('name')} | Coords: {data.get('latitude')}, {data.get('longitude')}")

if __name__ == "__main__":
    list_cities()
