"""Tarifs LLM, source UNIQUE pour le coût du chat (Dashboard Administrateur) et pour les modèles Claude / Gemini Pro de
`backend/scripts/cost_dashboard.py` (qui les importe). Module autonome : l'API de production ne recopie qu'une liste de
modules de `backend/`, donc ce fichier (dans `backend/api/`) ne doit rien importer d'autre du dépôt.

$ par million de tokens ; `cached` = facteur appliqué aux tokens lus depuis le cache (INCLUS dans `in`). Sources : page
de tarifs Anthropic relue le 2026-11-01 (Opus 5.5 : 4 $ / 20 $, lecture de cache 0,20 $ ; Sonnet 5.5 : 2 $ / 10 $, lecture
0,10 $ ; écriture de cache 1,25 × l'entrée en TTL 5 min, 2 × en TTL 1 h) ; Gemini 3.1 Pro : journal du 2026-07-08.
"""

DAILY_ALERT_USD = 2.0  # seuil d'alerte (jamais de blocage), tous modèles confondus — décision de l'utilisateur 2026-11-01

PRICING = {
    "gemini-3.1-pro-preview": {"in": 2.00, "out": 12.00, "cached": 0.25},
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, "cached": 0.05},
    "claude-opus-5-5": {"in": 4.00, "out": 20.00, "cached": 0.05},
}

# Modèle sans tarif connu (ex. `gemini-2.5-pro` encore configuré pour 3 comptes) : on compte au tarif le PLUS HAUT connu
# plutôt qu'à 0 $, pour que l'alerte ne soit jamais sous-estimée en silence ; ces appels sont signalés comme estimés.
FALLBACK_TIER = max(PRICING.values(), key=lambda t: t["out"])

CACHE_WRITE_FACTOR = {"5m": 1.25, "1h": 2.0}


def is_priced(model: str) -> bool:
    return model in PRICING


def cost_usd(model: str, input_tokens: int, cached_tokens: int, output_tokens: int,
             cache_write_tokens: int = 0, cache_ttl: str = "5m", fallback: bool = False):
    """Coût d'un lot d'appels en dollars. `input_tokens` INCLUT les lus (`cached_tokens`) et les écrits
    (`cache_write_tokens`, facturés plus cher que l'entrée). Modèle inconnu : None, ou `FALLBACK_TIER` si `fallback`."""
    tier = PRICING.get(model) or (FALLBACK_TIER if fallback else None)
    if tier is None:
        return None
    write = min(cache_write_tokens, max(0, input_tokens - cached_tokens))
    uncached = max(0, input_tokens - cached_tokens - write)
    return (uncached * tier["in"] + cached_tokens * tier["in"] * tier["cached"]
            + write * tier["in"] * CACHE_WRITE_FACTOR.get(cache_ttl, 1.25) + output_tokens * tier["out"]) / 1e6
