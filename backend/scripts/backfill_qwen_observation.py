"""Chantier H (validation) : accélère l'accumulation de données de comparaison Qwen vs Gemini
au rôle de Portier, en rejouant l'observation Qwen SEULE (pas Gemini, déjà connu) sur des
annonces déjà analysées en production.

Contexte : `gatekeeperVerdict` (verdict brut de Gemini T1) est déployé depuis le 2026-09-12
(commit `892263f`/`daef248`) — toute annonce analysée en production depuis cette date en
dispose déjà. Ce script rejoue Qwen sur les annonces les plus récentes qui en disposent, pour
constituer un échantillon de comparaison de taille `--limit` (200 par défaut), sans attendre
l'accumulation naturelle du trafic futur.

Coût : UNIQUEMENT l'appel Qwen (~0,0011$/annonce, TokenRouter) — le verdict Gemini existant est
réutilisé tel quel, aucun second appel Gemini (pas la peine de repayer une décision déjà prise
réellement en production).

Sélection : les `--limit` annonces avec `aiAnalysis.gatekeeperVerdict` présent les plus
récentes (`timestamp` décroissant — photos encore valides côté Storage), qu'elles aient déjà
`qwenGatekeeperVerdict` ou non — celles qui l'ont déjà (ex : observation live de Chantier H
depuis le 2026-09-13) sont comptées dans l'échantillon sans ré-appel Qwen (statut
"already_done"), seules les autres déclenchent un appel réel.

Rate limit TokenRouter (run #41, 2026-09-13) : le compte est plafonné à 5 requêtes/minute
("Maximum 5 requests within 1 minutes") — dépassé par le premier essai à 10 workers (10 échecs
429 sur 15). `--workers` par défaut abaissé à 3, et chaque appel Qwen retente avec backoff
(15s, 30s, 45s) sur une erreur 429 avant d'abandonner.

Parallélisé (`--workers`, 3 par défaut) : chaque annonce ne dépend d'aucune autre (lecture d'un
doc distinct, un appel Qwen indépendant, une écriture ciblée sur ce même doc).

Usage : python -m backend.scripts.backfill_qwen_observation [--limit 200] [--workers 3]
"""
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.getcwd())

QWEN_RATE_LIMIT_RETRY_DELAYS_S = (15, 30, 45)


def _process_one(db, app_id, analyzer, gatekeeper_instruction, main_prompt, taxonomy, few_shot, uid, deal_id, deal):
    """Traite une annonce : télécharge ses photos déjà stockées, reconstruit le prompt EXACT
    du Portier de production, appelle Qwen (observation seule, avec retry sur 429), écrit le
    résultat. Retourne une chaîne de statut ('ok'/'already_done'/'no_image'/'error') — jamais
    d'exception (capturée ici)."""
    try:
        existing_ai = deal.get('aiAnalysis') or {}
        gemini_verdict = existing_ai.get('gatekeeperVerdict')
        if existing_ai.get('qwenGatekeeperVerdict'):
            return "already_done", deal_id, (gemini_verdict, existing_ai.get('qwenGatekeeperVerdict'))

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

        qwen_observation, err = None, None
        for attempt, retry_delay in enumerate((0,) + QWEN_RATE_LIMIT_RETRY_DELAYS_S):
            if retry_delay:
                time.sleep(retry_delay)
            qwen_observation = analyzer._run_t1_qwen_observation(full_prompt_t1, images)
            err = qwen_observation.get("qwenGatekeeperError") if qwen_observation else "aucune réponse"
            if qwen_observation and not qwen_observation.get("qwenGatekeeperError"):
                break
            if "429" not in str(err):
                break  # erreur non liée au rate limit : inutile de retenter

        if not qwen_observation or qwen_observation.get("qwenGatekeeperError"):
            return "error", deal_id, err

        (
            db.collection('artifacts').document(app_id)
            .collection('users').document(uid).collection('guitar_deals').document(deal_id)
            .update({f"aiAnalysis.{k}": v for k, v in qwen_observation.items()})
        )
        return "ok", deal_id, (gemini_verdict, qwen_observation.get('qwenGatekeeperVerdict'))
    except Exception as e:
        return "error", deal_id, str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--workers", type=int, default=3)
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
            if ai.get('gatekeeperVerdict'):
                candidates.append((uid, doc.id, deal))

    candidates.sort(key=lambda c: (c[2].get('timestamp') is None, c[2].get('timestamp')), reverse=True)
    candidates = candidates[:args.limit]
    print(f"📋 {len(candidates)} annonce(s) avec gatekeeperVerdict (les plus récentes), "
          f"limité à {args.limit}, {args.workers} worker(s) en parallèle.")

    n_ok, n_already_done, n_no_image, n_error = 0, 0, 0, 0
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
            elif status == "already_done":
                n_already_done += 1
                gemini_verdict, qwen_verdict = extra
                print(f"  ↩️ {deal_id} (déjà fait) : gatekeeperVerdict={gemini_verdict!r} vs qwenGatekeeperVerdict={qwen_verdict!r}")
            elif status == "no_image":
                n_no_image += 1
            else:
                n_error += 1
                print(f"  ⚠️ {deal_id} : {extra}")

    print(f"\n{'=' * 60}\nRésultat\n{'=' * 60}")
    print(f"{n_ok} annonce(s) complétée(s) maintenant, {n_already_done} déjà faite(s) (comptées dans "
          f"l'échantillon), {n_no_image} sans photo récupérable, {n_error} échec(s) Qwen. "
          f"Échantillon total de comparaison : {n_ok + n_already_done}/{len(candidates)}.")


if __name__ == "__main__":
    main()
