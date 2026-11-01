"""Alerte de coût du chat (2026-11-01) : une notification ntfy quand le coût du JOUR dépasse `DAILY_ALERT_USD`.

Jamais bloquante : le chat continue, on prévient seulement. Vérifiée après chaque tour enregistré (`POST /usage`), au plus
une notification par jour et par processus (le jour courant est mémorisé en mémoire : un redémarrage de l'API peut en
renvoyer une seconde le même jour, ce qui est préférable à un oubli). Sans `NTFY_TOPIC` dans l'environnement, aucune
notification n'est envoyée (l'alerte reste visible dans le Dashboard Administrateur).

Module autonome (n'importe que `llm_pricing`) : l'API de production ne recopie qu'une liste de modules de `backend/`.
"""
import asyncio
import logging
import os

from backend.api import llm_pricing, model_alerts

log = logging.getLogger("cost_alert")

_TODAY_SQL = """
SELECT model, SUM(input_tokens) AS input_tokens, SUM(cached_tokens) AS cached_tokens,
       SUM(cache_write_tokens) AS cache_write_tokens, SUM(output_tokens + thoughts_tokens) AS output_tokens
FROM llm_usage
WHERE source = 'chat' AND ok
  AND (created_at AT TIME ZONE 'America/Toronto')::date = (now() AT TIME ZONE 'America/Toronto')::date
GROUP BY model
"""

_alerted_on = None  # date (str) de la dernière alerte envoyée par ce processus


_send_ntfy = model_alerts.send_ntfy  # même envoi que les alertes de modèle injoignable


async def today_chat_cost(pool) -> float:
    rows = await pool.fetch(_TODAY_SQL)
    return sum(llm_pricing.cost_usd(r["model"], int(r["input_tokens"] or 0), int(r["cached_tokens"] or 0),
                                    int(r["output_tokens"] or 0), int(r["cache_write_tokens"] or 0), fallback=True)
               for r in rows)


async def maybe_alert(pool, today: str) -> bool:
    """Envoie l'alerte si le seuil du jour est dépassé et qu'elle n'a pas déjà été envoyée aujourd'hui. Ne lève jamais."""
    global _alerted_on
    try:
        if _alerted_on == today:
            return False
        total = await today_chat_cost(pool)
        if total < llm_pricing.DAILY_ALERT_USD:
            return False
        _alerted_on = today
        topic = os.getenv("NTFY_TOPIC", "").strip()
        if not topic:
            log.warning("[cost_alert] seuil dépassé (%.2f $) mais NTFY_TOPIC est absent : aucune notification envoyée.", total)
            return False
        await asyncio.to_thread(_send_ntfy, topic, "Cout du chat au-dessus du seuil",
                                f"Le chat a coûté {total:.2f} $ aujourd'hui (seuil {llm_pricing.DAILY_ALERT_USD:.2f} $).")
        return True
    except Exception as e:  # une alerte ne doit jamais faire échouer l'enregistrement d'un tour
        log.warning("[cost_alert] vérification impossible (ignorée) : %s", e)
        return False
