"""
Analyse retroactive du funnel IA (Portier -> Analyste -> Expert Pro) a partir
du champ aiAnalysis.model_used deja stocke sur chaque annonce existante.

Sert a calibrer les hypotheses de funnel de
docs/management/plans/GEMINI_PROMPT_CACHING_PLAN.md (section 7.5) avec des
donnees reelles plutot que des estimations, et a suivre dans le temps :
- le volume quotidien reel d'annonces analysees (moteur du cout Gemini),
- le ratio de rentabilite du cache explicite (economie de tokens / cout de
  stockage) a ce volume,
- un echantillon d'annonces rejetees au Portier, pour verifier a la main si
  le taux de rejet eleve reflete du bruit legitime ou des faux positifs dus
  a la faiblesse du modele flash-lite.

Usage :
    python backend/scripts/analyze_funnel_by_user.py                     # tous les utilisateurs
    python backend/scripts/analyze_funnel_by_user.py --user-id UID
    python backend/scripts/analyze_funnel_by_user.py --days 14 --sample-size 5
"""
import sys
import os
import argparse
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import credentials, firestore

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from config import FIREBASE_KEY_PATH, APP_ID_TARGET


def setup_firebase():
    if not firebase_admin._apps:
        if not os.path.exists(FIREBASE_KEY_PATH):
            print(f"❌ Erreur : Fichier de clé introuvable à {FIREBASE_KEY_PATH}")
            sys.exit(1)
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


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
PRICE = {
    "t1": {"in": 0.10, "out": 0.40},    # gemini-2.5-flash-lite
    "t2": {"in": 0.30, "out": 2.50},    # gemini-2.5-flash
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


def analyze_user_deals(db, user_id, days_window=30, sample_size=3):
    """Retourne les compteurs de funnel + volume + échantillon de rejets pour un utilisateur."""
    deals_ref = db.collection('artifacts').document(APP_ID_TARGET) \
                  .collection('users').document(user_id).collection('guitar_deals')

    total = 0
    reached_t2 = 0
    reached_t3 = 0
    no_model_used = 0  # annonces legacy sans ce champ
    recent_count = 0   # annonces créées dans la fenêtre days_window
    rejected_samples = []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_window)

    for doc in deals_ref.stream():
        deal = doc.to_dict()
        total += 1

        ts = deal.get('timestamp')
        if ts is not None:
            try:
                if ts >= cutoff:
                    recent_count += 1
            except TypeError:
                pass  # timestamp mal formé sur une annonce ancienne

        ai_analysis = deal.get('aiAnalysis')
        ai_analysis = ai_analysis if isinstance(ai_analysis, dict) else {}
        model_used = ai_analysis.get('model_used')
        tokens = chain_tokens(model_used)

        if not tokens:
            no_model_used += 1
            continue

        if len(tokens) == 1 and len(rejected_samples) < sample_size:
            rejected_samples.append({
                "title": deal.get('title', 'N/A'),
                "verdict": ai_analysis.get('verdict', 'N/A'),
                "reasoning": str(ai_analysis.get('reasoning', ''))[:200],
            })

        if len(tokens) >= 2:
            reached_t2 += 1
        if any('pro' in t.lower() for t in tokens):
            reached_t3 += 1

    return {
        "total": total,
        "reached_t2": reached_t2,
        "reached_t3": reached_t3,
        "no_model_used": no_model_used,
        "recent_count": recent_count,
        "rejected_samples": rejected_samples,
    }


def print_report(user_label, stats, days_window):
    total = stats["total"]
    print(f"\n{'='*70}")
    print(f"Utilisateur : {user_label}")
    print(f"{'='*70}")
    if total == 0:
        print("Aucune annonce trouvée.")
        return

    # Dénominateur = annonces post-funnel-3-tiers uniquement (les legacy n'ont jamais pu atteindre T2/T3)
    tracked_total = total - stats["no_model_used"]
    t2_rate = (stats["reached_t2"] / tracked_total) if tracked_total > 0 else 0.0
    t3_rate = (stats["reached_t3"] / stats["reached_t2"]) if stats["reached_t2"] > 0 else 0.0

    print(f"Total annonces analysées (T1 - Portier) : {total}")
    print(f"Qualifiées Analyste (T2)                : {stats['reached_t2']} ({t2_rate*100:.1f}% des {tracked_total} annonces suivies)")
    print(f"Certifiées Expert Pro (T3)               : {stats['reached_t3']} ({t3_rate*100:.1f}% du T2)")
    if stats["no_model_used"] > 0:
        print(f"⚠️  Annonces legacy sans 'model_used'    : {stats['no_model_used']} (exclues du calcul %)")

    daily_volume = stats["recent_count"] / days_window
    print(f"\n📅 Volume réel (derniers {days_window}j) : {stats['recent_count']} annonces → {daily_volume:.2f}/jour")

    if daily_volume > 0:
        profit = estimate_profitability(daily_volume, t2_rate, t3_rate)
        verdict = "✅ RENTABLE" if profit["profitability_ratio"] >= 1 else "❌ PERTE NETTE"
        print(f"💰 Cache explicite à ce volume : {verdict} (ratio économie/stockage = {profit['profitability_ratio']:.2f})")
        print(f"   Économie brute/jour : ${profit['daily_savings']:.3f} | Stockage/jour : ${profit['storage_cost_per_day']:.3f} | Net : ${profit['net_gain_per_day']:.3f}")


def print_rejected_samples(all_samples, limit=15):
    if not all_samples:
        return
    print(f"\n{'='*70}")
    print(f"🔍 ÉCHANTILLON D'ANNONCES REJETÉES AU PORTIER (à examiner pour détecter des faux positifs)")
    print(f"{'='*70}")
    for i, s in enumerate(all_samples[:limit], 1):
        print(f"\n{i}. [{s['verdict']}] {s['title']}")
        print(f"   Raison : {s['reasoning']}")


def main():
    parser = argparse.ArgumentParser(description="Analyse du funnel IA réel, du volume quotidien et de la rentabilité du cache")
    parser.add_argument("--user-id", help="Limiter l'analyse à un seul UID Firebase")
    parser.add_argument("--days", type=int, default=30, help="Fenêtre (jours) pour le calcul du volume quotidien (défaut: 30)")
    parser.add_argument("--sample-size", type=int, default=3, help="Nombre d'annonces rejetées à échantillonner par utilisateur (défaut: 3)")
    args = parser.parse_args()

    db = setup_firebase()

    if args.user_id:
        user_ids = [args.user_id]
    else:
        print("🔍 Récupération de la liste des utilisateurs enregistrés...")
        users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
        user_ids = [doc.id for doc in users_ref.stream()]
        print(f"   {len(user_ids)} utilisateur(s) trouvé(s).")

    grand_total = {"total": 0, "reached_t2": 0, "reached_t3": 0, "no_model_used": 0, "recent_count": 0}
    all_samples = []

    for uid in user_ids:
        stats = analyze_user_deals(db, uid, days_window=args.days, sample_size=args.sample_size)
        print_report(uid, stats, args.days)
        for key in grand_total:
            grand_total[key] += stats[key]
        all_samples.extend(stats["rejected_samples"])

    print(f"\n{'#'*70}")
    print_report("TOUS UTILISATEURS CONFONDUS", grand_total, args.days)
    print(f"{'#'*70}")

    print_rejected_samples(all_samples)


if __name__ == "__main__":
    main()
