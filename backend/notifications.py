import requests
import logging
from config import NTFY_TOPIC

logger = logging.getLogger(__name__)

class NotificationService:
    @staticmethod
    def send_notification(title, message, priority='default', tags=None, click_url=None):
        """Envoie une notification via ntfy.sh."""
        if not NTFY_TOPIC:
            logger.warning("NTFY_TOPIC non configuré. Notification ignorée.")
            return

        url = f"https://ntfy.sh/{NTFY_TOPIC}"
        headers = {
            "Title": title.encode('utf-8'),
            "Priority": priority,
        }
        
        if tags:
            headers["Tags"] = ",".join(tags)
        
        if click_url:
            headers["Click"] = click_url

        try:
            response = requests.post(
                url,
                data=message.encode('utf-8'),
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                logger.info(f"Notification envoyée : {title}")
            else:
                logger.error(f"Erreur envoi ntfy ({response.status_code}): {response.text}")
        except Exception as e:
            logger.error(f"Erreur connexion ntfy: {e}")

    @staticmethod
    def notify_deal(deal_data, analysis):
        """Formate et envoie une notification pour une annonce intéressante."""
        verdict = analysis.get('verdict', 'UNKNOWN')
        
        # On ne notifie que pour les verdicts positifs majeurs
        if verdict not in ['PEPITE', 'BONNE_AFFAIRE', 'GOLD']:
            return

        title = f"🎸 {verdict} : {deal_data.get('title')}"
        price = deal_data.get('price', 0)
        est_val = analysis.get('estimated_value', 0)
        profit = est_val - price
        
        message = (
            f"Prix: {price}$\n"
            f"Estimé: {est_val}$\n"
            f"Profit potentiel: {profit}$\n\n"
            f"Raison: {analysis.get('reasoning', '')[:100]}..."
        )
        
        priority = 'high' if verdict == 'PEPITE' else 'default'
        tags = ['guitar', 'moneybag']
        if verdict == 'PEPITE': tags.append('star')
        
        NotificationService.send_notification(
            title=title,
            message=message,
            priority=priority,
            tags=tags,
            click_url=deal_data.get('link')
        )
