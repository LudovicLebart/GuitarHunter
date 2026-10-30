"""Modèle de coût Gemini et lecture du funnel (T1 -> T2 -> T3), SANS dépendance Firestore/Firebase.

Extrait de `backend/scripts/analyze_funnel_by_user.py` (2026-10-11) pour que l'API (Dashboard
Administrateur, `backend/api/admin_repo.py`) puisse l'importer : le script, lui, ouvre une connexion
Firestore à l'import et ne peut donc pas être chargé côté serveur d'API.
"""


def chain_tokens(model_used):
    if not model_used or not isinstance(model_used, str):
        return []
    return [t.strip() for t in model_used.split('->') if t.strip()]


# --- Modèle de coût Gemini (constantes mesurées, cf. GEMINI_PROMPT_CACHING_PLAN.md §7) ---
STATIC_COMMON_TOKENS = 3205  # taxonomie + few-shot + prompt principal (prompts.json)
TIER_INSTR_TOKENS = {"t1": 192, "t2": 109, "t3": 140}
LISTING_DETAILS_TOKENS = 75
TOKENS_PER_IMAGE = 700
IMAGES_PER_DEAL = 4
OUTPUT_TOKENS = {"t1": 130, "t2": 350, "t3": 900}
# Bascule 2026-09-20 (Chantier H, T1_GATEKEEPER_PROVIDER=qwen, voir config.py) : le tarif "t1"
# ci-dessous reste celui de Gemini Flash-Lite, mais ce modèle n'est plus le DÉCIDEUR réel du
# Portier — il ne tourne plus qu'en observation miroir (best-effort, `T1_OBSERVATION_ENABLED`),
# au même volume d'appels qu'avant la bascule. La décision réelle passe désormais par Qwen/
# TokenRouter, dont le coût n'est PAS modélisé ici (tarif TokenRouter non disponible côté
# repo) : `cost_no_cache_per_day`/`cost_with_cache_per_day` sous-estiment donc le coût de
# production réel du volume "t1" de cette valeur manquante. Le calcul de rentabilité du cache
# explicite Gemini reste valide tel quel (il ne s'applique qu'à l'observation miroir, toujours
# sur Gemini), mais ne plus lire "t1" comme "coût du filtrage réel des annonces".
PRICE = {
    "t1": {"in": 0.30, "out": 2.50},    # gemini-3.5-flash-lite (config.py, MAJ 2026-07-31 ; était gemini-2.5-flash-lite, retiré par Google en octobre 2026)
    "t2": {"in": 0.75, "out": 3.75},    # gemini-3.7-flash (config.py, MAJ 2026-09-06 ; était gemini-3.6-flash). Tarif de lancement jusqu'au 31/12/2026, repasse ensuite à 1.50/7.50 (identique au tarif standard déjà payé pour 3.6-flash)
    "t3": {"in": 2.00, "out": 12.00},   # gemini-3.1-pro-preview (config.py, MAJ 2026-07-08 ; était gemini-2.5-pro à 1.25/10.00)
}
CACHE_DISCOUNT = 0.10
STORAGE_PRICE_PER_M_TOKENS_PER_HOUR = 2.00  # estimation moyenne (fourchette publique 1-4.50$)


def _call_cost(tier, cached):
    images_tokens = TOKENS_PER_IMAGE * IMAGES_PER_DEAL
    static_tokens = STATIC_COMMON_TOKENS + TIER_INSTR_TOKENS[tier]
    variable_tokens = LISTING_DETAILS_TOKENS + images_tokens
    p = PRICE[tier]
    if cached:
        cost_in = variable_tokens / 1e6 * p["in"] + static_tokens / 1e6 * p["in"] * CACHE_DISCOUNT
    else:
        cost_in = (static_tokens + variable_tokens) / 1e6 * p["in"]
    cost_out = OUTPUT_TOKENS[tier] / 1e6 * p["out"]
    return cost_in + cost_out


def estimate_profitability(daily_volume, t2_rate, t3_rate):
    """Estime le gain net/jour du caching explicite au volume et taux de funnel donnés."""
    n_t1 = daily_volume
    n_t2 = daily_volume * t2_rate
    n_t3 = n_t2 * t3_rate

    cost_nc = n_t1 * _call_cost("t1", False) + n_t2 * _call_cost("t2", False) + n_t3 * _call_cost("t3", False)
    cost_c = n_t1 * _call_cost("t1", True) + n_t2 * _call_cost("t2", True) + n_t3 * _call_cost("t3", True)

    cached_tokens_total = sum(STATIC_COMMON_TOKENS + TIER_INSTR_TOKENS[t] for t in ("t1", "t2", "t3"))
    storage_cost_per_day = cached_tokens_total / 1e6 * STORAGE_PRICE_PER_M_TOKENS_PER_HOUR * 24

    daily_savings = cost_nc - cost_c
    ratio = (daily_savings / storage_cost_per_day) if storage_cost_per_day > 0 else float('inf')

    return {
        "cost_no_cache_per_day": cost_nc,
        "cost_with_cache_per_day": cost_c,
        "storage_cost_per_day": storage_cost_per_day,
        "daily_savings": daily_savings,
        "net_gain_per_day": daily_savings - storage_cost_per_day,
        "profitability_ratio": ratio,  # > 1 => le cache explicite est rentable à ce volume
    }
