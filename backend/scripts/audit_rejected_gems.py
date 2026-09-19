"""
Diagnostic one-off (Chantier G, validation avant tout code de routage) — script B du plan
approuvé le 2026-09-12 : le Tier 1 (Portier) ne calcule jamais de `deal_score` (score
d'attractivité/pépite, calculé uniquement au Tier 2) — une annonce qu'il rejette n'a donc AUCUN
signal permettant de savoir, a posteriori, si elle aurait été une pépite. Cette question n'est
pas mesurable "gratuitement" depuis les logs existants (contrairement à la précision de
classification T1, voir `analyzer.py::gatekeeperBrand`/`gatekeeperClassification`, commit du
même jour) : il faut réellement relancer le Tier 2 sur un échantillon d'annonces déjà rejetées
par T1 pour savoir si certaines auraient obtenu un score élevé.

**Correction 2026-09-14 (population)** : la version initiale (run #35, n=11, 1 seul exploitable)
interrogeait `status == "rejected"` — ce champ ne correspond QU'aux rejets par mot-clé
(`bot.py::_create_rejection_analysis`, blocklist de marques type "First Act"/"Rogue", verdict
littéral `"REJECTED"`), jamais aux vrais rejets IA du Portier (`BAD_DEAL`/`REJECTED_ITEM`/
`REJECTED_SERVICE`), qui reçoivent `status: "analyzed"` (voir `repository.py::create_new_deal` —
seul `verdict == "REJECTED"` produit `status: "rejected"`). Le chemin mot-clé retourne AVANT
l'upload Storage (`handle_deal_found`), d'où le 91% de photos manquantes : ce n'était pas un
problème d'échantillon, mais la mauvaise population — augmenter `--limit` n'y aurait rien changé.
Requête corrigée : `aiAnalysis.gatekeeperVerdict` dans `DEFAULT_REJECTION_VERDICTS` (les vrais
verdicts de rejet de production), qui elle est bien passée par l'upload Storage.

**Priorisation Qwen (2026-09-14)** : les annonces déjà signalées par l'observation Qwen
(Chantier H) comme désaccord pépite-tier (`qwenGatekeeperVerdict` dans `T1_PEPITE_TIER_VERDICTS`)
passent toujours en premier dans l'échantillon retourné — jamais tronquées par `--limit`, même si
la population totale dépasse la limite. Le reste complète par ordre de récence, pour garder une
mesure représentative du taux global de rejets manqués (restreindre l'échantillon aux seuls
candidats déjà signalés par Qwen biaiserait ce taux à la hausse). Chaque résultat indique aussi
si Qwen l'avait signalé, pour valider après coup si son signal (gratuit) est un bon prédicteur du
vrai jugement Tier 2 (payant).

Lecture seule côté Firestore (aucune écriture — les annonces rejetées restent rejetées), mais
CONSOMME de vrais appels Gemini (Tier 2 uniquement, le moins cher après T1) sur l'échantillon —
~0,008$/annonce réellement ré-analysée (mesuré 2026-09-14).

Réutilise directement les méthodes privées de `DealAnalyzer` (`_download_and_optimize_image`,
`_construct_base_user_prompt`, `_call_gemini_json`) pour appeler EXACTEMENT le même prompt T2
que la cascade de production, sans dupliquer sa construction — même pattern que
`analyze_deal_light()` (`backend/analyzer.py`).

**Correction 2026-09-19 (run #47)** : `_prepare_visual_parts` (méthode utilisée sur la branche de
benchmark d'origine) n'existe plus sur `dev` — `analyzer.py` a divergé depuis. Remplacé par la
construction inline utilisée par la production (`analyze_deal_light`), cap à 8 photos.

Usage : python -m backend.scripts.audit_rejected_gems [--limit N]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "benchmark", "results")
DEFAULT_LIMIT = 300


def _rebuild_listing_data(deal_id, deal):
    """Reconstruit un `listing_data` minimal exploitable pour la ré-analyse T2 — préfère
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


def _is_qwen_flagged(deal):
    """True si l'observation Qwen (Chantier H) penchait vers un verdict pépite-tier, en
    désaccord avec le rejet réel de Gemini -- le signal gratuit qui priorise l'échantillon."""
    from backend.analyzer import T1_PEPITE_TIER_VERDICTS
    qv = (deal.get("aiAnalysis") or {}).get("qwenGatekeeperVerdict")
    return qv in T1_PEPITE_TIER_VERDICTS


def sample_rejected_deals(db, app_id, limit):
    """Échantillonne les VRAIS rejets IA du Portier (`aiAnalysis.gatekeeperVerdict` dans les
    verdicts de rejet de production), triés candidats Qwen-signalés d'abord puis par récence.
    Retourne (échantillon tronqué à `limit`, nombre total de candidats Qwen-signalés trouvés)."""
    from google.cloud.firestore_v1.base_query import FieldFilter
    from config import DEFAULT_REJECTION_VERDICTS

    users_ref = db.collection("artifacts").document(app_id).collection("users")
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"🔍 {len(user_ids)} utilisateur(s) trouvé(s).")

    candidates = []
    for uid in user_ids:
        deals_ref = (
            db.collection("artifacts").document(app_id)
            .collection("users").document(uid).collection("guitar_deals")
        )
        query = deals_ref.where(filter=FieldFilter("aiAnalysis.gatekeeperVerdict", "in", DEFAULT_REJECTION_VERDICTS))
        for doc in query.stream():
            candidates.append((doc.id, doc.to_dict()))

    n_qwen_flagged_total = sum(1 for _, d in candidates if _is_qwen_flagged(d))

    # Tri stable en deux passes : d'abord par récence (comportement déjà utilisé ailleurs dans
    # le projet), puis les candidats Qwen-signalés remontent en tête SANS perturber l'ordre de
    # récence à l'intérieur de chaque groupe (tri stable) -- jamais tronqués par --limit.
    candidates.sort(key=lambda c: (c[1].get('timestamp') is None, c[1].get('timestamp')), reverse=True)
    candidates.sort(key=lambda c: not _is_qwen_flagged(c[1]))

    return candidates[:limit], n_qwen_flagged_total


def main():
    parser = argparse.ArgumentParser(description="Audit des rejets T1 potentiellement ratés (Chantier G)")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Nombre d'annonces rejetées à ré-analyser")
    args = parser.parse_args()

    from backend.analyzer import DealAnalyzer, DEFAULT_MAIN_PROMPT, DEFAULT_TAXONOMY, DEFAULT_FEW_SHOT_EXAMPLES, DEFAULT_ANALYST_INSTRUCTION
    from backend.scripts.export_neck_reset_sample import setup_firebase
    from config import APP_ID_TARGET, GEMINI_MODELS
    import config as config_module

    db = setup_firebase()
    samples, n_qwen_flagged_total = sample_rejected_deals(db, APP_ID_TARGET, args.limit)
    print(f"📦 {len(samples)} annonce(s) rejetée(s) par le Portier échantillonnée(s) pour ré-analyse Tier 2 "
          f"({n_qwen_flagged_total} déjà signalée(s) par Qwen, toutes incluses en priorité).\n")

    analyzer = DealAnalyzer()
    analyst_model_name = GEMINI_MODELS.get("default_analyst", "gemini-3.7-flash")

    deal_score_threshold = getattr(config_module, "DEFAULT_PRO_DEAL_SCORE_THRESHOLD", 8)
    combined_deal_score = getattr(config_module, "DEFAULT_PRO_COMBINED_DEAL_SCORE", 6)
    resto_threshold = getattr(config_module, "DEFAULT_PRO_RESTO_SCORE_THRESHOLD", 7)

    results = []
    missed_count = 0
    # Cross-référence : le signal Qwen (gratuit) prédit-il bien le vrai jugement T2 (payant) ?
    n_qwen_flagged_confirmed = 0  # Qwen signalait ET T2 confirme (vrai positif du signal Qwen)
    n_qwen_flagged_not_confirmed = 0  # Qwen signalait MAIS T2 ne confirme pas (faux positif Qwen)
    n_missed_not_qwen_flagged = 0  # T2 trouve une pépite que Qwen n'avait PAS signalée

    for deal_id, deal in samples:
        listing_data = _rebuild_listing_data(deal_id, deal)
        ai = deal.get("aiAnalysis") or {}
        original_verdict = ai.get("gatekeeperVerdict", "")
        original_reason = ai.get("reasoning", "")
        was_qwen_flagged = _is_qwen_flagged(deal)

        image_urls = (listing_data.get('imageUrls') or [listing_data.get('imageUrl')])[:8]
        images = [img for url in image_urls if (img := analyzer._download_and_optimize_image(url))]
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
            if was_qwen_flagged:
                n_qwen_flagged_confirmed += 1
            else:
                n_missed_not_qwen_flagged += 1
        elif was_qwen_flagged:
            n_qwen_flagged_not_confirmed += 1

        flag = "🚨 AURAIT DÉCLENCHÉ T3 (pépite potentiellement ratée)" if would_trigger_t3 else "  ok, rejet confirmé"
        qwen_note = " [Qwen l'avait déjà signalée]" if was_qwen_flagged else ""
        print(f"{flag}{qwen_note} — {deal_id} : '{deal.get('title', '')[:60]}' — deal_score={deal_score} resto={resto_score}")
        print(f"    Rejet T1 original : {original_verdict} — {original_reason[:150]}")

        results.append({
            "id": deal_id,
            "title": deal.get("title"),
            "price": deal.get("price"),
            "original_verdict": original_verdict,
            "original_reason": original_reason,
            "qwen_flagged": was_qwen_flagged,
            "qwen_verdict": ai.get("qwenGatekeeperVerdict"),
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
    print(f"{n} annonce(s) rejetée(s) par le Portier (vrai jugement IA) effectivement ré-analysée(s) (Tier 2 seul).")
    print(f"{missed_count} ({pct}%) auraient déclenché le Tier 3 sous les seuils de production par défaut —")
    print("pépites potentiellement perdues par le rejet du Portier.")
    print(f"\nValidation du signal Qwen (gratuit) contre le vrai jugement T2 (payant) :")
    print(f"  Qwen signalait + T2 confirme  : {n_qwen_flagged_confirmed} (vrai positif du signal Qwen)")
    print(f"  Qwen signalait + T2 infirme   : {n_qwen_flagged_not_confirmed} (faux positif du signal Qwen)")
    print(f"  T2 trouve, Qwen n'avait PAS signalé : {n_missed_not_qwen_flagged} (angle mort du signal Qwen)")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(
        RESULTS_DIR, f"audit_rejected_gems_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "n_sampled": n,
            "missed_count": missed_count,
            "missed_pct": pct,
            "n_qwen_flagged_total": n_qwen_flagged_total,
            "n_qwen_flagged_confirmed": n_qwen_flagged_confirmed,
            "n_qwen_flagged_not_confirmed": n_qwen_flagged_not_confirmed,
            "n_missed_not_qwen_flagged": n_missed_not_qwen_flagged,
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nRésultats détaillés sauvegardés dans : {out_path}")


if __name__ == "__main__":
    main()
