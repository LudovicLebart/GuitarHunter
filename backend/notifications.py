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
        safe_title = title.replace('\n', ' ').replace('\r', ' ')
        headers = {
            "Title": safe_title.encode('utf-8'),
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
    def notify_deal(deal_id, deal_data, analysis, is_update=False):
        """Formate et envoie une notification pour une annonce intéressante."""
        verdict = analysis.get('verdict', 'UNKNOWN')
        
        # On ne notifie que pour les verdicts positifs majeurs
        if verdict not in ['PEPITE', 'BONNE_AFFAIRE', 'GOLD']:
            return

        price = deal_data.get('price', 0)
        title_prefix = f"🎸 {verdict}"
        
        # --- Filtrage intelligent des mises à jour ---
        if is_update:
            price_drop = deal_data.get('price_drop_amount')
            old_price_raw = deal_data.get('original_price')
            
            # Si aucune baisse de prix n'est enregistrée, on ignore la notification
            if not price_drop or not old_price_raw:
                logger.info(f"ntfy ignoré : simple mise à jour de l'annonce sans baisse de prix ({deal_id}).")
                return
                
            try:
                old_p = float(''.join(c for c in str(old_price_raw).replace(',', '.') if c.isdigit() or c == '.'))
                if old_p > 0:
                    drop_percent = (price_drop / old_p) * 100
                    # Filtre anti-spam : ignore les baisses de moins de 5% ET moins de 50$
                    if drop_percent < 5.0 and price_drop < 50:
                        logger.info(f"ntfy ignoré : baisse de prix trop mineure ({drop_percent:.1f}%, -{price_drop}$) pour {deal_id}")
                        return
                    title_prefix = f"📉 BAISSE DE PRIX ({verdict})"
            except Exception:
                pass

        title = f"{title_prefix} : {deal_data.get('title')}"
        est_val = analysis.get('estimated_value', 0)
        profit = est_val - price
        
        message = (
            f"Nouveau Prix: {price}$" if is_update else f"Prix: {price}$"
        )
        if is_update and deal_data.get('price_drop_amount'):
            message += f" (Baisse de {deal_data.get('price_drop_amount')}$)\n"
        else:
            message += "\n"
            
        message += (
            f"Estimé: {est_val}$\n"
            f"Profit potentiel: {profit}$\n\n"
            f"Raison: {analysis.get('reasoning', '')[:100]}..."
        )
        
        priority = 'high' if verdict == 'PEPITE' else 'default'
        tags = ['guitar', 'moneybag']
        if verdict == 'PEPITE': tags.append('star')
        
        click_url = None
        if deal_id:
            click_url = f"https://ludoviclebart.github.io/GuitarHunter/?dealId={deal_id}"
        else:
            logger.warning(f"Aucun deal_id fourni pour la notification '{title}'. Le lien sera absent.")

        NotificationService.send_notification(
            title=title,
            message=message,
            priority=priority,
            tags=tags,
            click_url=click_url
        )
