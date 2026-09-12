"""
Diagnostic one-off (Chantier G, validation avant tout code de routage) — script B du plan
approuvé le 2026-09-12 : le Tier 1 (Portier) ne calcule jamais de `deal_score` (score
d'attractivité/pépite, calculé uniquement au Tier 2) — une annonce qu'il rejette n'a donc AUCUN
signal permettant de savoir, a posteriori, si elle aurait été une pépite. Cette question n'est
pas mesurable "gratuitement" depuis les logs existants (contrairement à la précision de
classification T1, voir `analyzer.py::gatekeeperBrand`/`gatekeeperClassification`, commit du
même jour) : il faut réellement relancer le Tier 2 sur un échantillon d'annonces déjà rejetées
par T1 pour savoir si certaines auraient obtenu un score élevé.

Lecture seule côté Firestore (aucune écriture — les annonces rejetées restent rejetées), mais
CONSOMME de vrais appels Gemini (Tier 2 uniquement, le moins cher après T1) sur l'échantillon.

Réutilise directement les méthodes privées de `DealAnalyzer` (`_prepare_visual_parts`,
`_construct_base_user_prompt`, `_call_gemini_json`) pour appeler EXACTEMENT le même prompt T2
que la cascade de production, sans dupliquer sa construction — même pattern déjà utilisé pour
`_PerceptionSubstitutedAnalyzer` (Chantier B, `backend/benchmark/candidates.py`).

Usage : python -m backend.scripts.audit_rejected_gems [--limit N]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "benchmark", "results")
DEFAULT_LIMIT = 30


def _rebuild_listing_data(deal_id, deal):
    """Reconstruit un `listing_data` minimal utilisable par `_prepare_visual_parts` — préfère
    les URLs durables Firebase Storage (les URLs Facebook/Kijiji d'origine expirent)."""
    image_urls = deal.get("storageImageUrls") or deal.get("imageUrls") or []
    return {
        "id": deal_id,
        "title": deal.get("title", ""),
        "price": deal.get("price"),
        "description": deal.get("description", ""),
        "location": deal.get("location", ""),
        "imageUrls": image_urls,
    }


def sample_rejected_deals(db, app_id, limit):
    from google.cloud.firestore_v1.base_query import FieldFilter

    users_ref = db.collection("artifacts").document(app_id).collection("users")
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"🔍 {len(user_ids)} utilisateur(s) trouvé(s).")

    samples = []
    per_user_limit = max(1, limit // max(1, len(user_ids)))
    for uid in user_ids:
        deals_ref = (
            db.collection("artifacts").document(app_id)
            .collection("users").document(uid).collection("guitar_deals")
        )
        query = deals_ref.where(filter=FieldFilter("status", "==", "rejected")).limit(per_user_limit)
        for doc in query.stream():
            samples.append((doc.id, doc.to_dict()))
            if len(samples) >= limit:
                return samples
    return samples


def main():
    parser = argparse.ArgumentParser(description="Audit des rejets T1 potentiellement ratés (Chantier G)")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Nombre d'annonces rejetées à ré-analyser")
    args = parser.parse_args()

    from backend.analyzer import DealAnalyzer, DEFAULT_MAIN_PROMPT, DEFAULT_TAXONOMY, DEFAULT_FEW_SHOT_EXAMPLES, DEFAULT_ANALYST_INSTRUCTION
    from backend.scripts.export_neck_reset_sample import setup_firebase
    from config import APP_ID_TARGET, GEMINI_MODELS
    import config as config_module

    db = setup_firebase()
    samples = sample_rejected_deals(db, APP_ID_TARGET, args.limit)
    print(f"📦 {len(samples)} annonce(s) rejetée(s) échantillonnée(s) pour ré-analyse Tier 2.\n")

    analyzer = DealAnalyzer()
    analyst_model_name = GEMINI_MODELS.get("default_analyst", "gemini-3.7-flash")

    deal_score_threshold = getattr(config_module, "DEFAULT_PRO_DEAL_SCORE_THRESHOLD", 8)
    combined_deal_score = getattr(config_module, "DEFAULT_PRO_COMBINED_DEAL_SCORE", 6)
    resto_threshold = getattr(config_module, "DEFAULT_PRO_RESTO_SCORE_THRESHOLD", 7)

    results = []
    missed_count = 0

    for deal_id, deal in samples:
        listing_data = _rebuild_listing_data(deal_id, deal)
        original_reason = (deal.get("aiAnalysis") or {}).get("reasoning", "")
        original_verdict = (deal.get("aiAnalysis") or {}).get("verdict", "")

        images = analyzer._prepare_visual_parts(listing_data)
        if not images:
            print(f"⚠️  {deal_id} : aucune photo récupérable (URLs expirées/manquantes) — ignorée.")
            continue

        base_prompt = analyzer._construct_base_user_prompt(
            listing_data, DEFAULT_MAIN_PROMPT, DEFAULT_TAXONOMY, DEFAULT_FEW_SHOT_EXAMPLES
        )
        full_prompt_t2 = f"{base_prompt}\n\n--- INSTRUCTION SPÉCIALE ANALYSTE ---\n{DEFAULT_ANALYST_INSTRUCTION}"

        result_t2, err = analyzer._call_gemini_json(analyst_model_name, [full_prompt_t2] + images)
        if err or not result_t2:
            print(f"❌ {deal_id} : échec de la ré-analyse T2 ({err}) — ignorée.")
            continue

        deal_score = result_t2.get("deal_score", 0)
        resto_score = result_t2.get("restoration_interest_score", 0)
        would_trigger_t3 = (
            deal_score >= deal_score_threshold
            or (deal_score >= combined_deal_score and resto_score >= resto_threshold)
        )
        if would_trigger_t3:
            missed_count += 1

        flag = "🚨 AURAIT DÉCLENCHÉ T3 (pépite potentiellement ratée)" if would_trigger_t3 else "  ok, rejet confirmé"
        print(f"{flag} — {deal_id} : '{deal.get('title', '')[:60]}' — deal_score={deal_score} resto={resto_score}")
        print(f"    Rejet T1 original : {original_verdict} — {original_reason[:150]}")

        results.append({
            "id": deal_id,
            "title": deal.get("title"),
            "price": deal.get("price"),
            "original_verdict": original_verdict,
            "original_reason": original_reason,
            "t2_rerun": {
                "deal_score": deal_score,
                "authenticity_score": result_t2.get("authenticity_score"),
                "restoration_interest_score": resto_score,
                "confidence": result_t2.get("confidence"),
                "verdict": result_t2.get("verdict"),
                "summary": result_t2.get("summary"),
            },
            "would_trigger_t3": would_trigger_t3,
        })

    n = len(results)
    pct = round(100 * missed_count / n, 1) if n else None
    print(f"\n{'=' * 60}\nRÉSUMÉ\n{'=' * 60}")
    print(f"{n} annonce(s) rejetée(s) effectivement ré-analysées (Tier 2 seul).")
    print(f"{missed_count} ({pct}%) auraient déclenché le Tier 3 sous les seuils de production par défaut —")
    print("pépites potentiellement perdues par le rejet du Portier.")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(
        RESULTS_DIR, f"audit_rejected_gems_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "n_sampled": n,
            "missed_count": missed_count,
            "missed_pct": pct,
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nRésultats détaillés sauvegardés dans : {out_path}")


if __name__ == "__main__":
    main()
