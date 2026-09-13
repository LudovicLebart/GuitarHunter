"""
Deux diagnostics combinés, lecture seule (aucune écriture Firestore) :

1. Répartition réelle du coût ($) par Tier, sur la même fenêtre de facturation et avec
   exactement la même méthode que le run #421 (JOURNAL.md 2026-09-07, écart de 3,4% avec la
   facture réelle) — jusqu'ici seul le total ($9,10 pour la cascade) avait été consigné, jamais
   la part de chaque Tier. Complète le tableau de répartition en VOLUME déjà documenté
   (T1=70%/T2=25%/T3=5% des annonces) avec la répartition en $ correspondante — les deux
   diffèrent car chaque Tier suivant coûte nettement plus cher par appel.

2. Taux de `storageImageUrls` rempli, comparé entre un échantillon d'annonces rejetées et un
   échantillon d'annonces acceptées — pour savoir si l'absence de photo stockée constatée sur
   les rejets (run #35, `audit_rejected_gems.py`) est systématique ou un hasard de petit
   échantillon (n=11 initial, insuffisant pour trancher).

Usage : python -m backend.scripts.analyze_tier_cost_and_photo_storage
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

# Mêmes constantes que run_once.py (run #421) — reproduction fidèle pour comparabilité directe.
PERIOD_START = "2026-09-01T00:00:00+00:00"
PERIOD_END = "2026-09-07T00:00:00+00:00"
CHARS_PER_TOKEN = 4
TOKENS_PER_IMAGE = 900
T1_PROMPT_TOKENS = 5353
T2_PROMPT_TOKENS = 4900
T3_PROMPT_TOKENS = 4933
T1_OUTPUT_TOKENS_DEFAULT = 330
T2_OUTPUT_TOKENS_DEFAULT = 135
PRICING = {"t1": (0.30, 2.50), "t2": (0.75, 3.75), "t3": (2.00, 12.00), "chat": (2.00, 12.00)}
SYSTEM_INSTRUCTION_CHARS = 700

PHOTO_SAMPLE_SIZE = 30


def _chat_cost_for_deal(chat_docs):
    """Copié tel quel de run_once.py — même méthode déjà validée (run #419/#421)."""
    cumulative_text_chars = 0
    cumulative_images = 0
    total_input_tokens = 0
    total_output_tokens = 0
    num_calls = 0
    for msg_doc in chat_docs:
        msg = msg_doc.to_dict()
        parts = msg.get('parts') or []
        text_chars = sum(len(p.get('text', '')) for p in parts if isinstance(p, dict) and p.get('text'))
        n_images = sum(1 for p in parts if isinstance(p, dict) and p.get('inlineData'))
        if msg.get('role') == 'model':
            num_calls += 1
            input_tokens = (
                cumulative_text_chars // CHARS_PER_TOKEN
                + SYSTEM_INSTRUCTION_CHARS // CHARS_PER_TOKEN
                + cumulative_images * TOKENS_PER_IMAGE
            )
            total_input_tokens += input_tokens
            total_output_tokens += text_chars // CHARS_PER_TOKEN
        cumulative_text_chars += text_chars
        cumulative_images += n_images
    in_rate, out_rate = PRICING["chat"]
    cost = total_input_tokens * in_rate / 1_000_000 + total_output_tokens * out_rate / 1_000_000
    return cost


def analyze_tier_cost(db, app_id):
    print(f"\n{'=' * 60}\nPartie A — répartition du coût par Tier ({PERIOD_START} → {PERIOD_END})\n{'=' * 60}")
    period_start = datetime.fromisoformat(PERIOD_START)
    period_end = datetime.fromisoformat(PERIOD_END)

    users_ref = db.collection('artifacts').document(app_id).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]

    cost_by_tier = {1: 0.0, 2: 0.0, 3: 0.0}
    chat_cost_total = 0.0
    deals_in_period = 0

    for uid in user_ids:
        deals_ref = (
            db.collection('artifacts').document(app_id)
            .collection('users').document(uid).collection('guitar_deals')
        )
        for doc in deals_ref.stream():
            deal = doc.to_dict()
            ts = deal.get('timestamp')
            if ts is None or ts < period_start or ts >= period_end:
                continue
            deals_in_period += 1

            photos = len(deal.get('storageImageUrls') or [])
            analysis = deal.get('aiAnalysis') or {}
            model_used = analysis.get('model_used') or ''
            tier_count = min(model_used.count('->') + 1, 3) if model_used else 1
            analysis_output_tokens = len(analysis.get('analysis') or '') // CHARS_PER_TOKEN

            t1_in_rate, t1_out_rate = PRICING["t1"]
            cost_by_tier[1] += (
                (T1_PROMPT_TOKENS + photos * TOKENS_PER_IMAGE) * t1_in_rate / 1_000_000
                + T1_OUTPUT_TOKENS_DEFAULT * t1_out_rate / 1_000_000
            )
            if tier_count >= 2:
                t2_in_rate, t2_out_rate = PRICING["t2"]
                t2_output = analysis_output_tokens if tier_count == 2 else T2_OUTPUT_TOKENS_DEFAULT
                cost_by_tier[2] += (
                    (T2_PROMPT_TOKENS + photos * TOKENS_PER_IMAGE) * t2_in_rate / 1_000_000
                    + t2_output * t2_out_rate / 1_000_000
                )
            if tier_count >= 3:
                t3_in_rate, t3_out_rate = PRICING["t3"]
                cost_by_tier[3] += (
                    (T3_PROMPT_TOKENS + photos * TOKENS_PER_IMAGE) * t3_in_rate / 1_000_000
                    + analysis_output_tokens * t3_out_rate / 1_000_000
                )

            chat_docs = list(
                db.collection('artifacts').document(app_id)
                .collection('users').document(uid)
                .collection('guitar_deals').document(doc.id)
                .collection('chat').order_by('createdAt').stream()
            )
            if chat_docs:
                chat_cost_total += _chat_cost_for_deal(chat_docs)

    cascade_total = sum(cost_by_tier.values())
    grand_total = cascade_total + chat_cost_total

    print(f"{deals_in_period} annonce(s) dans la fenêtre.")
    print(f"Coût cascade reconstruit : ${cascade_total:.4f} (attendu ≈ $9.10, run #421) + chat ${chat_cost_total:.4f} = ${grand_total:.4f}")
    print("\nRépartition du coût par Tier :")
    for tier, cost in cost_by_tier.items():
        pct_cascade = 100 * cost / cascade_total if cascade_total else 0
        pct_grand = 100 * cost / grand_total if grand_total else 0
        print(f"  Tier {tier} : ${cost:.4f} — {pct_cascade:.1f}% de la cascade, {pct_grand:.1f}% de la facture totale (chat inclus)")
    pct_chat = 100 * chat_cost_total / grand_total if grand_total else 0
    print(f"  Chat      : ${chat_cost_total:.4f} — {pct_chat:.1f}% de la facture totale")


def analyze_photo_storage_rate(db, app_id):
    print(f"\n{'=' * 60}\nPartie B — taux de storageImageUrls, rejetés vs acceptés\n{'=' * 60}")
    from google.cloud.firestore_v1.base_query import FieldFilter

    users_ref = db.collection('artifacts').document(app_id).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]

    for status_value, label in (("rejected", "rejetées"), ("analyzed", "acceptées/analysées")):
        sampled = 0
        with_photo = 0
        per_user_limit = max(1, PHOTO_SAMPLE_SIZE // max(1, len(user_ids)))
        for uid in user_ids:
            deals_ref = (
                db.collection('artifacts').document(app_id)
                .collection('users').document(uid).collection('guitar_deals')
            )
            query = deals_ref.where(filter=FieldFilter("status", "==", status_value)).limit(per_user_limit)
            for doc in query.stream():
                deal = doc.to_dict()
                sampled += 1
                if deal.get('storageImageUrls'):
                    with_photo += 1
                if sampled >= PHOTO_SAMPLE_SIZE:
                    break
            if sampled >= PHOTO_SAMPLE_SIZE:
                break
        pct = round(100 * with_photo / sampled, 1) if sampled else None
        print(f"  {label:25s} : {with_photo}/{sampled} avec storageImageUrls rempli ({pct}%)")


def main():
    from backend.scripts.export_neck_reset_sample import setup_firebase
    from config import APP_ID_TARGET

    db = setup_firebase()
    analyze_tier_cost(db, APP_ID_TARGET)
    analyze_photo_storage_rate(db, APP_ID_TARGET)


if __name__ == "__main__":
    main()
