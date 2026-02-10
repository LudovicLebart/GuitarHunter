import logging
import sys
from backend.notifications import NotificationService
from config import NTFY_TOPIC

# Configuration du logging pour voir les sorties
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_notification():
    print(f"--- Test de Notification ntfy ---")
    print(f"Topic configuré : {NTFY_TOPIC}")
    
    if not NTFY_TOPIC:
        print("❌ ERREUR : NTFY_TOPIC n'est pas défini dans le fichier .env ou config.py")
        return

    print("Envoi de la notification de test...")
    
    try:
        NotificationService.send_notification(
            title="🎸 Test Guitar Hunter",
            message="Ceci est une notification de test pour vérifier la configuration ntfy.",
            priority="high",
            tags=["test", "guitar"],
            click_url="https://www.google.com"
        )
        print("✅ Notification envoyée (vérifiez votre application ntfy ou le navigateur).")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi : {e}")

if __name__ == "__main__":
    test_notification()
