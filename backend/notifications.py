"""
Notifications multi-canal pour Guitar Hunter.
- Canal 1 : ntfy.sh (push mobile, optionnel via NTFY_TOPIC)
- Canal 2 : Email Gmail SMTP (universel, via SMTP_USER + SMTP_PASSWORD)

L'email de destination est l'email Firebase Auth de l'utilisateur,
récupéré dynamiquement par le bot. Aucune configuration manuelle requise.
"""

import smtplib
import logging
from email.message import EmailMessage
from email.header import Header
from email.utils import formataddr
from typing import Optional

import requests
from config import NTFY_TOPIC, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

logger = logging.getLogger(__name__)

# Verdicts qui déclenchent une notification
NOTIFY_VERDICTS = {'PEPITE'}
# Note : LUTHIER_PROJ, CASE_WIN, COLLECTION désactivés par défaut (trop de volume)
# Ajouter à NOTIFY_VERDICTS si souhaité.

# Verdicts à haute priorité (ntfy urgent + email avec sujet distinctif)
HIGH_PRIORITY_VERDICTS = {'PEPITE'}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers communs
# ─────────────────────────────────────────────────────────────────────────────

def _is_price_drop_notifiable(deal_data: dict) -> bool:
    """Filtre anti-spam : baisse de prix < 5% ET < 50$ ignorée."""
    price_drop = deal_data.get('price_drop_amount')
    old_price_raw = deal_data.get('original_price')
    if not price_drop or not old_price_raw:
        return False
    try:
        old_p = float(''.join(c for c in str(old_price_raw).replace(',', '.') if c.isdigit() or c == '.'))
        if old_p > 0:
            drop_percent = (price_drop / old_p) * 100
            return drop_percent >= 5.0 or price_drop >= 50
    except Exception:
        pass
    return False


def _build_subject(verdict: str, deal_data: dict, is_update: bool, also_pepite: bool = False) -> str:
    """Construit le sujet de l'email."""
    emoji_map = {
        'PEPITE': '⭐', 'GOLD': '🏆', 'FAST_FLIP': '⚡',
        'LUTHIER_PROJ': '🔧', 'CASE_WIN': '💼', 'COLLECTION': '🎸',
        'BONNE_AFFAIRE': '✅',
    }
    emoji = emoji_map.get(verdict, '🎸')
    title = deal_data.get('title', 'Annonce')[:50]
    price = deal_data.get('price', 0)
    suffix = " (Aussi Pépite ⭐)" if also_pepite and verdict != 'PEPITE' else ""

    if is_update:
        drop = deal_data.get('price_drop_amount', 0)
        return f"[GuitarHunter] {emoji} BAISSE DE PRIX ({verdict}) : {title} — {price}$ (-{drop}$){suffix}"
    return f"[GuitarHunter] {emoji} {verdict} : {title} — {price}${suffix}"


def _build_body(verdict: str, deal_data: dict, analysis: dict, is_update: bool, deal_link: str, also_pepite: bool = False) -> str:
    """Construit le corps texte de l'email (compatible avec tous les clients mail)."""
    price = deal_data.get('price', 0)
    est_val = analysis.get('estimated_value', 0)
    profit = (est_val or 0) - (price or 0)
    reasoning = (analysis.get('reasoning') or '')[:300]
    title = deal_data.get('title', 'N/A')
    location = deal_data.get('location', 'N/A')
    brand = analysis.get('brand') or ''
    model = analysis.get('model_name') or ''
    verdict_line = f"{verdict} (Aussi Pépite ⭐)" if also_pepite and verdict != 'PEPITE' else verdict

    lines = [
        f"{'📉 BAISSE DE PRIX' if is_update else '🎸 NOUVELLE PÉPITE'} — {verdict_line}",
        "=" * 50,
        f"Titre    : {title}",
        f"Marque   : {brand} {model}".strip(),
        f"Lieu     : {location}",
        "",
    ]

    if is_update:
        drop = deal_data.get('price_drop_amount', 0)
        old_price = deal_data.get('original_price', 'N/A')
        lines += [
            f"Ancien prix  : {old_price}$",
            f"Nouveau prix : {price}$  (-{drop}$)",
        ]
    else:
        lines.append(f"Prix demandé : {price}$")

    lines += [
        f"Valeur estimée    : {est_val}$",
        f"Profit potentiel  : {'+' if profit >= 0 else ''}{profit}$",
        "",
        "ANALYSE IA",
        "-" * 30,
        reasoning,
        "",
        f"👉 Voir l'annonce : {deal_link}" if deal_link else "",
        "",
        "—",
        "Guitar Hunter Bot",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Canal 1 : ntfy.sh
# ─────────────────────────────────────────────────────────────────────────────

class NtfyNotifier:
    """Envoie des notifications push via ntfy.sh (canal optionnel)."""

    @staticmethod
    def send(title: str, message: str, priority: str = 'default',
             tags: list = None, click_url: str = None) -> None:
        if not NTFY_TOPIC:
            return
        url = f"https://ntfy.sh/{NTFY_TOPIC}"
        safe_title = title.replace('\n', ' ').replace('\r', ' ')
        # ntfy.sh (et `requests`) exigent des headers HTTP en Latin-1 : les émojis/accents
        # doivent être encodés en RFC 2047 (cf. docs.ntfy.sh/publish), sinon `requests`
        # lève une UnicodeEncodeError silencieusement catchée plus bas (notif jamais envoyée).
        # maxlinelen élevé pour éviter le repliement multi-ligne (RFC 2822) : invalide
        # pour un header HTTP brut, qui doit tenir sur une seule ligne.
        encoded_title = Header(safe_title, 'utf-8', maxlinelen=998).encode()
        headers = {
            "Title": encoded_title,
            "Priority": priority,
        }
        if tags:
            headers["Tags"] = ",".join(tags)
        if click_url:
            headers["Click"] = click_url
        try:
            resp = requests.post(url, data=message.encode('utf-8'), headers=headers, timeout=10)
            if resp.status_code == 200:
                logger.info(f"[ntfy] Notification envoyée : {title}")
            else:
                logger.error(f"[ntfy] Erreur {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"[ntfy] Connexion impossible : {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Canal 2 : Email SMTP
# ─────────────────────────────────────────────────────────────────────────────

class EmailNotifier:
    """Envoie des emails via SMTP (Gmail TLS port 587 par défaut)."""

    def __init__(self):
        self._enabled = bool(SMTP_USER and SMTP_PASSWORD)
        if not self._enabled:
            logger.warning(
                "[Email] SMTP_USER / SMTP_PASSWORD non définis dans .env — "
                "notifications email désactivées."
            )

    def send(self, to_email: str, subject: str, body: str) -> None:
        if not self._enabled:
            return
        if not to_email:
            logger.warning("[Email] Aucun email destinataire fourni. Notification ignorée.")
            return
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"]    = formataddr(("Guitar Hunter Bot", SMTP_USER))
            msg["To"]      = to_email
            msg.set_content(body)

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(msg)
            logger.info(f"[Email] Envoyé → {to_email} | {subject[:60]}")
        except Exception as e:
            logger.warning(f"[Email] Échec envoi vers {to_email} : {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée centralisé
# ─────────────────────────────────────────────────────────────────────────────

# Instances partagées (stateless, thread-safe)
_ntfy = NtfyNotifier()
_email_notifier = EmailNotifier()


class NotificationService:
    """Point d'entrée unique pour toutes les notifications GuitarHunter."""

    @staticmethod
    def notify_deal(deal_id: str, deal_data: dict, analysis: dict,
                    is_update: bool = False, user_email: Optional[str] = None) -> None:
        """
        Évalue si l'annonce mérite une notification et l'envoie sur tous les canaux actifs.

        Args:
            deal_id      : ID Firestore de l'annonce.
            deal_data    : Dict complet de l'annonce (title, price, location…).
            analysis     : Dict du résultat d'analyse IA (verdict, reasoning…).
            is_update    : True si c'est une mise à jour de prix.
            user_email   : Email Firebase Auth de l'utilisateur destinataire.
        """
        verdict = analysis.get('verdict', 'UNKNOWN')
        also_pepite = bool(analysis.get('also_qualifies_pepite')) and verdict != 'PEPITE'

        # ── Filtre : verdicts non-notifiables ──────────────────────────────
        if verdict not in NOTIFY_VERDICTS and not also_pepite:
            return

        # ── Filtre : mises à jour sans baisse de prix significative ────────
        if is_update and not _is_price_drop_notifiable(deal_data):
            logger.info(f"[Notif] Ignoré (baisse mineure) pour {deal_id}.")
            return

        # ── Construction du contenu ────────────────────────────────────────
        deal_link = (
            f"https://ludoviclebart.github.io/GuitarHunter/?dealId={deal_id}"
            if deal_id else None
        )

        subject = _build_subject(verdict, deal_data, is_update, also_pepite)
        body    = _build_body(verdict, deal_data, analysis, is_update, deal_link, also_pepite)

        # ── Canal 1 : ntfy.sh ─────────────────────────────────────────────
        is_high_priority = verdict in HIGH_PRIORITY_VERDICTS or also_pepite
        priority = 'high' if is_high_priority else 'default'
        tags = ['guitar', 'moneybag']
        if is_high_priority:
            tags.append('star')

        price = deal_data.get('price', 0) or 0
        profit = (analysis.get('estimated_value', 0) or 0) - price

        ntfy_title = subject.replace("[GuitarHunter] ", "")
        ntfy_msg = (
            f"Prix: {price}$"
            + (f" (-{deal_data.get('price_drop_amount')}$)" if is_update and deal_data.get('price_drop_amount') else "")
            + f"\nProfit: {'+' if profit >= 0 else ''}{profit}$"
            + f"\n{(analysis.get('reasoning') or '')[:120]}..."
        )
        _ntfy.send(ntfy_title, ntfy_msg, priority=priority, tags=tags, click_url=deal_link)

        # ── Canal 2 : Email ───────────────────────────────────────────────
        _email_notifier.send(to_email=user_email, subject=subject, body=body)

    @staticmethod
    def notify_model_error(model_name: str, error: str, user_email: Optional[str] = None) -> None:
        """
        Alerte (email + ntfy) quand un modèle Gemini configuré semble indisponible/retiré
        (ex: modèle Preview déprécié). Throttlée en amont par l'appelant (1x/24h/modèle).

        Args:
            model_name : Nom du modèle Gemini en échec (ex: 'gemini-3.1-pro-preview').
            error      : Message d'erreur brut retourné par l'API.
            user_email : Email Firebase Auth de l'utilisateur destinataire.
        """
        subject = f"[GuitarHunter] ⚠️ Modèle Gemini indisponible : {model_name}"
        body = (
            f"⚠️ MODÈLE GEMINI INDISPONIBLE\n"
            f"{'=' * 50}\n"
            f"Modèle    : {model_name}\n"
            f"Erreur    : {error}\n\n"
            f"Ce modèle semble avoir été retiré ou n'est plus supporté par l'API Gemini "
            f"(ex: fin de vie d'un modèle Preview). Va dans le panneau de configuration de "
            f"Guitar Hunter et choisis un autre modèle pour le(s) étage(s) concerné(s) "
            f"(Portier / Analyste / Expert Pro).\n\n"
            f"—\nGuitar Hunter Bot"
        )
        _ntfy.send(
            f"⚠️ Modèle indisponible : {model_name}",
            f"{error[:200]}",
            priority='high',
            tags=['warning']
        )
        _email_notifier.send(to_email=user_email, subject=subject, body=body)
