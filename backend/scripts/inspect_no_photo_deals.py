"""
Diagnostic ponctuel, lecture seule : le run #35 (`audit_rejected_gems.py`) a trouvé que 10/11
annonces rejetées échantillonnées n'avaient aucune photo récupérable (`storageImageUrls`/
`imageUrls` absents ou vides). Ce script récupère ces documents précis (IDs connus depuis les
logs du run #35) et affiche leur `link` (URL source Facebook/Kijiji) + l'état exact de leurs
champs image, pour que l'utilisateur puisse vérifier une annonce réelle par lui-même.

Usage : python -m backend.scripts.inspect_no_photo_deals
"""
import os
import sys

sys.path.insert(0, os.getcwd())

DEAL_IDS = [
    "1276263211277563", "1348775587078034", "1350437003571357", "1397195858836176",
    "1012854541716149", "3020510631622972", "925501427224681", "1000101772745325",
    "1002307455831799", "1006756695593203",
]


def main():
    from backend.scripts.export_neck_reset_sample import setup_firebase
    from config import APP_ID_TARGET

    db = setup_firebase()
    users_ref = db.collection("artifacts").document(APP_ID_TARGET).collection("users")
    user_ids = [doc.id for doc in users_ref.stream()]

    for deal_id in DEAL_IDS:
        found = False
        for uid in user_ids:
            doc_ref = (
                db.collection("artifacts").document(APP_ID_TARGET)
                .collection("users").document(uid).collection("guitar_deals").document(deal_id)
            )
            doc = doc_ref.get()
            if doc.exists:
                found = True
                d = doc.to_dict()
                print(f"\n--- {deal_id} (user {uid[:8]}...) ---")
                print(f"Titre           : {d.get('title')}")
                print(f"Prix            : {d.get('price')}")
                print(f"Lien source     : {d.get('link')}")
                print(f"imageUrls       : {d.get('imageUrls')}")
                print(f"imageUrl        : {d.get('imageUrl')}")
                print(f"storageImageUrls: {d.get('storageImageUrls')}")
                print(f"timestamp       : {d.get('timestamp')}")
                print(f"status/verdict  : {d.get('status')} / {(d.get('aiAnalysis') or {}).get('verdict')}")
                break
        if not found:
            print(f"\n--- {deal_id} : introuvable (supprimée depuis ?) ---")


if __name__ == "__main__":
    main()
