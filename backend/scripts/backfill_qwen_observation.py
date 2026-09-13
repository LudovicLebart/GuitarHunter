"""Chantier H (validation) : accélère l'accumulation de données de comparaison Qwen vs Gemini
au rôle de Portier, en rejouant l'observation Qwen SEULE (pas Gemini, déjà connu) sur des
annonces déjà analysées en production.

Contexte : `gatekeeperVerdict` (verdict brut de Gemini T1) est déployé depuis le 2026-09-12
(commit `892263f`/`daef248`), avant l'observation Qwen elle-même (Chantier H, 2026-09-13). Les
annonces analysées dans cette fenêtre ont donc un `gatekeeperVerdict` mais jamais de
`qwenGatekeeperVerdict` — ce script comble cet écart pour ces annonces précises, sans attendre
l'accumulation naturelle du trafic futur.

Coût : UNIQUEMENT l'appel Qwen (~0,0011$/annonce, TokenRouter) — le verdict Gemini existant est
réutilisé tel quel, aucun second appel Gemini (pas la peine de repayer une décision déjà prise
réellement en production).

Sélection : annonces avec `aiAnalysis.gatekeeperVerdict` présent ET `aiAnalysis.qwenGatekeeperVerdict`
absent, triées par `timestamp` décroissant (les plus récentes d'abord — photos encore valides côté
Storage), limitées à `--limit` (200 par défaut).

Parallélisé (`--workers`, 10 par défaut) : chaque annonce ne dépend d'aucune autre (lecture d'un
doc distinct, un appel Qwen indépendant, une écriture ciblée sur ce même doc) — un
`ThreadPoolExecutor` évite d'attendre ~22s (latence Qwen, run #38) par annonce en série, ce qui
aurait pris plus d'une heure pour 200 annonces.

Usage : python -m backend.scripts.backfill_qwen_observation [--limit 200] [--workers 10]
"""
import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.getcwd())


def _process_one(db, app_id, analyzer, gatekeeper_instruction, main_prompt, taxonomy, few_shot, uid, deal_id, deal):
    """Traite une annonce : télécharge ses photos déjà stockées, reconstruit le prompt EXACT
    du Portier de production, appelle Qwen (observation seule), écrit le résultat. Retourne
    une chaîne de statut ('ok'/'no_image'/'error') — jamais d'exception (capturée ici)."""
    try:
        image_urls = deal.get('storageImageUrls') or deal.get('imageUrls') or []
        images = [img for url in image_urls[:8] if (img := analyzer._download_and_optimize_image(url))]
        if not images:
            return "no_image", deal_id, None

        listing_data = {
            "title": deal.get("title"),
            "price": deal.get("price"),
            "description": deal.get("description"),
            "location": deal.get("location"),
        }
        base_prompt = analyzer._construct_base_user_prompt(listing_data, main_prompt, taxonomy, few_shot)
        full_prompt_t1 = f"{base_prompt}\n\n--- INSTRUCTION SPÉCIALE PORTIER ---\n{gatekeeper_instruction}"

        qwen_observation = analyzer._run_t1_qwen_observation(full_prompt_t1, images)
        if not qwen_observation or qwen_observation.get("qwenGatekeeperError"):
            err = qwen_observation.get("qwenGatekeeperError") if qwen_observation else "aucune réponse"
            return "error", deal_id, err

        (
            db.collection('artifacts').document(app_id)
            .collection('users').document(uid).collection('guitar_deals').document(deal_id)
            .update({f"aiAnalysis.{k}": v for k, v in qwen_observation.items()})
        )
        gemini_verdict = (deal.get('aiAnalysis') or {}).get('gatekeeperVerdict')
        return "ok", deal_id, (gemini_verdict, qwen_observation.get('qwenGatekeeperVerdict'))
    except Exception as e:
        return "error", deal_id, str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    from backend.scripts.export_neck_reset_sample import setup_firebase
    from backend.analyzer import DealAnalyzer
    from config import APP_ID_TARGET, DEFAULT_MAIN_PROMPT, DEFAULT_TAXONOMY, DEFAULT_FEW_SHOT_EXAMPLES, DEFAULT_GATEKEEPER_INSTRUCTION

    db = setup_firebase()
    analyzer = DealAnalyzer()

    gatekeeper_instruction = DEFAULT_GATEKEEPER_INSTRUCTION
    if isinstance(gatekeeper_instruction, list):
        gatekeeper_instruction = "\n".join(gatekeeper_instruction)

    users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"🔍 {len(user_ids)} utilisateur(s) trouvé(s).")

    candidates = []
    for uid in user_ids:
        deals_ref = (
            db.collection('artifacts').document(APP_ID_TARGET)
            .collection('users').document(uid).collection('guitar_deals')
        )
        for doc in deals_ref.stream():
            deal = doc.to_dict()
            ai = deal.get('aiAnalysis') or {}
            if ai.get('gatekeeperVerdict') and not ai.get('qwenGatekeeperVerdict'):
                candidates.append((uid, doc.id, deal))

    candidates.sort(key=lambda c: (c[2].get('timestamp') is None, c[2].get('timestamp')), reverse=True)
    candidates = candidates[:args.limit]
    print(f"📋 {len(candidates)} annonce(s) éligible(s) (gatekeeperVerdict sans qwenGatekeeperVerdict), "
          f"limité à {args.limit}, {args.workers} worker(s) en parallèle.")

    n_ok, n_no_image, n_error = 0, 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                _process_one, db, APP_ID_TARGET, analyzer, gatekeeper_instruction,
                DEFAULT_MAIN_PROMPT, DEFAULT_TAXONOMY, DEFAULT_FEW_SHOT_EXAMPLES, uid, deal_id, deal
            )
            for uid, deal_id, deal in candidates
        ]
        for future in as_completed(futures):
            status, deal_id, extra = future.result()
            if status == "ok":
                n_ok += 1
                gemini_verdict, qwen_verdict = extra
                print(f"  ✅ {deal_id} : gatekeeperVerdict={gemini_verdict!r} vs qwenGatekeeperVerdict={qwen_verdict!r}")
            elif status == "no_image":
                n_no_image += 1
            else:
                n_error += 1
                print(f"  ⚠️ {deal_id} : {extra}")

    print(f"\n{'=' * 60}\nRésultat\n{'=' * 60}")
    print(f"{n_ok} annonce(s) complétée(s), {n_no_image} sans photo récupérable, {n_error} échec(s) Qwen.")


if __name__ == "__main__":
    main()
