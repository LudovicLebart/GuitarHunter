"""Tarifs LLM pour le coût du chat (Dashboard Administrateur) — module autonome : l'API de production ne recopie qu'une
liste de modules de `backend/`, donc ce fichier (dans `backend/api/`) ne doit importer rien d'autre du dépôt.

$ par million de tokens ; `cached` = facteur appliqué aux tokens lus depuis le cache (INCLUS dans `in`). Sources : page
de tarifs Anthropic relue le 2026-11-01 (Opus 5.5 : 4 $ / 20 $, lecture de cache 0,20 $ ; Sonnet 5.5 : 2 $ / 10 $, lecture
0,10 $), mêmes valeurs que `backend/scripts/cost_dashboard.py` (à garder synchronisées). Les écritures de cache (1,25 × ou
2 × l'entrée) ne sont pas distinguées dans `llm_usage` : elles sont comptées au prix d'entrée normal, ce qui sous-estime
légèrement les premiers tours d'une conversation Claude.
"""

DAILY_ALERT_USD = 2.0  # seuil d'alerte (jamais de blocage), tous modèles confondus — décision de l'utilisateur 2026-11-01

PRICING = {
    "gemini-3.1-pro-preview": {"in": 2.00, "out": 12.00, "cached": 0.25},
    "gemini-3.5-flash": {"in": 1.50, "out": 7.50, "cached": 0.10},
    "gemini-3.5-flash-lite": {"in": 0.30, "out": 2.50, "cached": 0.10},
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, "cached": 0.05},
    "claude-opus-5-5": {"in": 4.00, "out": 20.00, "cached": 0.05},
}


def cost_usd(model: str, input_tokens: int, cached_tokens: int, output_tokens: int):
    """Coût d'un lot d'appels en dollars ; None si le modèle n'a pas de tarif connu."""
    tier = PRICING.get(model)
    if tier is None:
        return None
    uncached = max(0, input_tokens - cached_tokens)
    return (uncached * tier["in"] + cached_tokens * tier["in"] * tier["cached"] + output_tokens * tier["out"]) / 1e6
