"""
Analyse retroactive du funnel IA (Portier -> Analyste -> Expert Pro) a partir
du champ aiAnalysis.model_used deja stocke sur chaque annonce existante.

Sert a calibrer les hypotheses de funnel de
docs/management/plans/GEMINI_PROMPT_CACHING_PLAN.md (section 7.4) avec des
donnees reelles plutot que des estimations.

Usage :
    python backend/scripts/analyze_funnel_by_user.py            # tous les utilisateurs
    python backend/scripts/analyze_funnel_by_user.py --user-id UID
"""
import sys
import os
import argparse
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


def analyze_user_deals(db, user_id):
    """Retourne les compteurs de funnel pour un utilisateur donné."""
    deals_ref = db.collection('artifacts').document(APP_ID_TARGET) \
                  .collection('users').document(user_id).collection('guitar_deals')

    total = 0
    reached_t2 = 0
    reached_t3 = 0
    no_model_used = 0  # annonces legacy sans ce champ

    for doc in deals_ref.stream():
        deal = doc.to_dict()
        total += 1
        ai_analysis = deal.get('aiAnalysis')
        model_used = ai_analysis.get('model_used') if isinstance(ai_analysis, dict) else None
        tokens = chain_tokens(model_used)
        if not tokens:
            no_model_used += 1
            continue
        if len(tokens) >= 2:
            reached_t2 += 1
        if any('pro' in t.lower() for t in tokens):
            reached_t3 += 1

    return {
        "total": total,
        "reached_t2": reached_t2,
        "reached_t3": reached_t3,
        "no_model_used": no_model_used,
    }


def print_report(user_label, stats):
    total = stats["total"]
    print(f"\n{'='*70}")
    print(f"Utilisateur : {user_label}")
    print(f"{'='*70}")
    if total == 0:
        print("Aucune annonce trouvée.")
        return
    # Denominateur = annonces post-funnel-3-tiers uniquement (les legacy n'ont jamais pu atteindre T2/T3)
    tracked_total = total - stats["no_model_used"]
    t2_pct = round(stats["reached_t2"] / tracked_total * 100, 1) if tracked_total > 0 else 0.0
    t3_pct = round(stats["reached_t3"] / stats["reached_t2"] * 100, 1) if stats["reached_t2"] > 0 else 0.0
    print(f"Total annonces analysées (T1 - Portier) : {total}")
    print(f"Qualifiées Analyste (T2)                : {stats['reached_t2']} ({t2_pct}% des {tracked_total} annonces suivies)")
    print(f"Certifiées Expert Pro (T3)               : {stats['reached_t3']} ({t3_pct}% du T2)")
    if stats["no_model_used"] > 0:
        print(f"⚠️  Annonces legacy sans 'model_used'    : {stats['no_model_used']} (exclues du calcul %)")


def main():
    parser = argparse.ArgumentParser(description="Analyse du funnel IA réel par utilisateur (via aiAnalysis.model_used)")
    parser.add_argument("--user-id", help="Limiter l'analyse à un seul UID Firebase")
    args = parser.parse_args()

    db = setup_firebase()

    if args.user_id:
        user_ids = [args.user_id]
    else:
        print("🔍 Récupération de la liste des utilisateurs enregistrés...")
        users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
        user_ids = [doc.id for doc in users_ref.stream()]
        print(f"   {len(user_ids)} utilisateur(s) trouvé(s).")

    grand_total = {"total": 0, "reached_t2": 0, "reached_t3": 0, "no_model_used": 0}

    for uid in user_ids:
        stats = analyze_user_deals(db, uid)
        print_report(uid, stats)
        for key in grand_total:
            grand_total[key] += stats[key]

    print(f"\n{'#'*70}")
    print_report("TOUS UTILISATEURS CONFONDUS", grand_total)
    print(f"{'#'*70}")


if __name__ == "__main__":
    main()
