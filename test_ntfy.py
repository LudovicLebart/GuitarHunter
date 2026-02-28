import logging
import os
import sys

# --- Configuration minimale pour exécuter le script ---
# Ajoute la racine du projet au path pour que les imports fonctionnent
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
# Configure un logger basique pour voir les messages du service
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

try:
    from backend.notifications import NotificationService
except ImportError:
    print("ERREUR: Impossible d'importer NotificationService.")
    print("Assurez-vous que ce script est bien à la racine de votre projet 'GuitarHunter'.")
    sys.exit(1)


def send_test_notification():
    """
    Envoie une notification de test avec des données prédéfinies pour valider le lien.
    """
    # L'ID de l'annonce que tu as fourni
    test_deal_id = "1024831570706623"

    # Données de l'annonce (simulées pour le test)
    test_deal_data = {
        'title': "Guitare de Test (PEPITE)",
        'price': 750
    }

    # Données de l'analyse IA (simulées pour le test)
    test_analysis = {
        'verdict': 'PEPITE', # Pour s'assurer que la notification est envoyée avec une priorité haute
        'estimated_value': 1200,
        'reasoning': "Ceci est une notification de test pour valider le lien de redirection."
    }

    print(f"Envoi d'une notification de test pour l'ID : {test_deal_id}...")

    # Appel de la fonction de notification avec les données de test
    NotificationService.notify_deal(
        deal_id=test_deal_id,
        deal_data=test_deal_data,
        analysis=test_analysis
    )

    print("\nDemande de notification envoyée.")
    print("Vérifiez votre client ntfy.sh.")
    print(f"Le lien généré devrait être : https://ludoviclebart.github.io/GuitarHunter/?dealId={test_deal_id}")


if __name__ == "__main__":
    send_test_notification()
