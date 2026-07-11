"""
Calcule quotidiennement le volume, le funnel et le coût Gemini estimé par
utilisateur, et écrit un snapshot agrégé dans artifacts/{APP_ID}/admin_stats/latest.

Lu par le Dashboard Administrateur (AdminDashboard.jsx) plutôt que de faire
lire au client des milliers de documents guitar_deals par utilisateur.

Réutilise le modèle de coût de backend/scripts/analyze_funnel_by_user.py
(mêmes constantes, mêmes formules) pour rester cohérent avec l'outil
d'analyse manuel. Appelé une fois par jour depuis la boucle watchdog de
main.py (singleton global — pas via un TaskScheduler par-utilisateur).
"""
import logging
from datetime import datetime, timedelta, timezone

from backend.scripts.analyze_funnel_by_user import chain_tokens, estimate_profitability
from config import APP_ID_TARGET

logger = logging.getLogger(__name__)

STATS_WINDOW_DAYS = 1  # fenêtre glissante pour le volume "quotidien"


def _compute_user_stats(db, user_id):
    cutoff = datetime.now(timezone.utc) - timedelta(days=STATS_WINDOW_DAYS)
    deals_ref = (
        db.collection('artifacts').document(APP_ID_TARGET)
          .collection('users').document(user_id).collection('guitar_deals')
          .where('timestamp', '>=', cutoff)
    )

    total = 0
    reached_t2 = 0
    reached_t3 = 0

    for doc in deals_ref.stream():
        deal = doc.to_dict()
        total += 1
        ai_analysis = deal.get('aiAnalysis')
        ai_analysis = ai_analysis if isinstance(ai_analysis, dict) else {}
        tokens = chain_tokens(ai_analysis.get('model_used'))
        if len(tokens) >= 2:
            reached_t2 += 1
        if any('pro' in t.lower() for t in tokens):
            reached_t3 += 1

    t2_rate = (reached_t2 / total) if total > 0 else 0.0
    t3_rate = (reached_t3 / reached_t2) if reached_t2 > 0 else 0.0
    estimated_cost = 0.0
    if total > 0:
        profit = estimate_profitability(total, t2_rate, t3_rate)
        estimated_cost = round(profit["cost_no_cache_per_day"], 4)

    return {
        "dailyVolume": total,
        "reachedT2": reached_t2,
        "reachedT3": reached_t3,
        "estimatedDailyCost": estimated_cost,
    }


def run_admin_stats_job(db_service):
    """Point d'entrée appelé une fois par jour depuis la boucle watchdog de main.py."""
    db = db_service.db
    logger.info("📊 [AdminStats] Calcul du snapshot quotidien...")
    try:
        users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
        user_ids = [doc.id for doc in users_ref.stream()]

        stats_by_user = {}
        for uid in user_ids:
            try:
                stats_by_user[uid] = _compute_user_stats(db, uid)
            except Exception as e:
                logger.error(f"❌ [AdminStats] Échec calcul pour {uid}: {e}")

        db.collection('artifacts').document(APP_ID_TARGET).collection('admin_stats').document('latest').set({
            "users": stats_by_user,
            "computedAt": datetime.now(timezone.utc),
        })
        logger.info(f"✅ [AdminStats] Snapshot écrit pour {len(stats_by_user)} utilisateur(s).")
    except Exception as e:
        logger.error(f"❌ [AdminStats] Échec du job: {e}", exc_info=True)
