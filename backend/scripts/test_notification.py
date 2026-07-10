"""
Script de test manuel du pipeline de notifications (ntfy + email).

Déclenche une notification factice (verdict PEPITE) sans passer par un scan
réel, en utilisant le vrai logger par-utilisateur (raccordé au LogViewer de
l'app) — permet de voir la cause exacte d'un échec d'envoi (SMTP mal
configuré, identifiants Gmail révoqués, etc.) sans attendre une vraie Pépite.

Usage :
    python3 backend/scripts/test_notification.py [--user-id UID] [--email destinataire@exemple.com]

Par défaut, utilise USER_ID_TARGET (.env) et l'email Firebase Auth associé.
"""
import sys
import os
import time
import argparse
import firebase_admin
from firebase_admin import auth, credentials, firestore

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from config import FIREBASE_KEY_PATH, APP_ID_TARGET, USER_ID_TARGET
from backend.logging_config import setup_logging
from backend.notifications import NotificationService


def setup_firebase():
    if not firebase_admin._apps:
        if not os.path.exists(FIREBASE_KEY_PATH):
            print(f"❌ Erreur : Fichier de clé introuvable à {FIREBASE_KEY_PATH}")
            sys.exit(1)
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def main():
    parser = argparse.ArgumentParser(description="Teste l'envoi d'une notification (ntfy + email).")
    parser.add_argument("--user-id", default=USER_ID_TARGET, help="UID Firebase (défaut: USER_ID_TARGET du .env)")
    parser.add_argument("--email", default=None, help="Email destinataire (défaut: email Firebase Auth de l'utilisateur)")
    args = parser.parse_args()

    if not args.user_id:
        print("❌ Aucun user-id fourni ni USER_ID_TARGET dans .env.")
        sys.exit(1)

    db = setup_firebase()

    user_email = args.email
    if not user_email:
        try:
            user_email = auth.get_user(args.user_id).email or ''
        except Exception as e:
            print(f"⚠️ Impossible de résoudre l'email Firebase Auth : {e}")
            user_email = ''

    print(f"App ID       : {APP_ID_TARGET}")
    print(f"User ID      : {args.user_id}")
    print(f"Email cible  : {user_email or '(vide — l’email sera ignoré, seul ntfy sera tenté)'}")

    # Raccorde le vrai logger par-utilisateur (Firestore/LogViewer), comme le fait bot.py.
    firestore_handler = setup_logging(db, APP_ID_TARGET, args.user_id, is_offline=False)
    import logging
    logger = logging.getLogger(f"bot.{args.user_id[:8]}")

    fake_deal_data = {
        "title": "[TEST] Guitare Fender Stratocaster",
        "price": 250,
        "location": "Montréal, QC",
    }
    fake_analysis = {
        "verdict": "PEPITE",
        "reasoning": "Ceci est un test manuel du pipeline de notifications (test_notification.py).",
        "estimated_value": 900,
        "brand": "Fender",
        "model_name": "Stratocaster (test)",
    }

    print("\n📨 Envoi de la notification de test...")
    NotificationService.notify_deal(
        deal_id="test-notification-script",
        deal_data=fake_deal_data,
        analysis=fake_analysis,
        is_update=False,
        user_email=user_email,
        logger=logger,
    )

    # Le FirestoreHandler bufferise et flush toutes les 3s dans un thread séparé —
    # on laisse le temps au batch de partir avant de fermer/quitter.
    time.sleep(4)
    if firestore_handler:
        firestore_handler.close()

    print("✅ Terminé. Vérifie le LogViewer de l'app (lignes [ntfy]/[Email]) et ta boîte mail.")


if __name__ == "__main__":
    main()
