"""
Script "one-shot" exécuté automatiquement à CHAQUE déploiement
(.github/workflows/deploy.yml, job `deploy`, étape "Script de maintenance ponctuel") —
ce job est le seul contexte où le serveur a déjà les credentials Firebase en place
(.env / backend/config/serviceAccountKey.json écrits juste avant dans le même job).

Sert à exécuter une action ponctuelle en production (ex: script de migration) depuis un
environnement de dev qui n'y a lui-même aucun accès à Firestore.

⚠️ NO-OP PAR DÉFAUT (ACTIVE = False). Protocole d'usage :
  1. Passer ACTIVE à True et écrire l'action dans run().
  2. Commit + push (déclenche le déploiement, qui exécute run() sur le serveur).
  3. Vérifier le résultat via les logs de l'étape dans l'onglet GitHub Actions (ou dans l'app).
  4. Repasser IMMÉDIATEMENT ACTIVE à False, dans un commit séparé — sinon l'action se
     répète à CHAQUE déploiement futur.

Le job `deploy` se déclenche sur push `master` ET `dev` — une action ici s'exécute donc
généralement deux fois de suite. Écrire uniquement des actions idempotentes (rejouables
sans effet de bord cumulatif). Un échec ici n'interrompt pas le reste du déploiement
(voir deploy.yml : l'étape est volontairement non bloquante).
"""
import sys
import os

# Comme rebuild_index.py : nécessaire pour que `from backend.scripts... import ...` résolve,
# `python3 backend/scripts/run_once.py` n'ajoutant que le dossier du script (pas la racine du
# repo) à sys.path. Le job `deploy` exécute toujours ce script depuis la racine (~/GuitareHunter).
sys.path.insert(0, os.getcwd())

ACTIVE = True

# Fenêtre de la facture GeminiDev fournie par l'utilisateur (rapport "20260901-20260930", mais
# les données ne couvrent en réalité que le début du mois — cf. JOURNAL.md "septembre partiel").
# Bornes larges pour ne rien perdre en bord de fenêtre.
PERIOD_START = "2026-09-01T00:00:00+00:00"
PERIOD_END = "2026-09-07T00:00:00+00:00"

CHARS_PER_TOKEN = 4  # approximation grossière (pas le vrai tokenizer Gemini, non disponible ici)
TOKENS_PER_IMAGE = 900  # calibré sur les tokens/photo réels mesurés côté cascade T1 (run #415)
# Tokens fixes du prompt de la cascade par Tier (mesurés directement sur prompts.json, run du
# 2026-09-06 — base_prompt commun + instruction spécifique par Tier).
T1_PROMPT_TOKENS = 5353
T2_PROMPT_TOKENS = 4900
T3_PROMPT_TOKENS = 4933
# Sorties par défaut quand la vraie longueur n'est pas mesurable pour ce Tier sur ce document
# (T1 : jamais stocké dans aiAnalysis, calibré sur la facture Sept 1-6 réelle 190689/579≈330 ;
# T2 : calibré sur la médiane mesurée run #415 quand le champ 'analysis' final vient du Tier 3
# et qu'on n'a donc plus la propre sortie du Tier 2, écrasée par le Tier 3).
T1_OUTPUT_TOKENS_DEFAULT = 330
T2_OUTPUT_TOKENS_DEFAULT = 135
# Tarifs $/M tokens (in, out) — voir JOURNAL.md 2026-09-06 pour les sources.
PRICING = {
    "t1": (0.30, 2.50),
    "t2": (0.75, 3.75),
    "t3": (2.00, 12.00),
    "chat": (2.00, 12.00),  # gemini-3.1-pro-preview, même modèle que le Tier 3
}
# SYSTEM_INSTRUCTION (geminiChatService.js) : ~700 caractères, fixe, envoyé à CHAQUE appel du chat.
SYSTEM_INSTRUCTION_CHARS = 700


def _chat_cost_for_deal(chat_docs):
    """Reconstruit le coût cumulé d'une conversation de chat (même méthode que le run #419) :
    chaque appel modèle repaye tout l'historique précédent en entrée."""
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
    return num_calls, total_input_tokens, total_output_tokens, cost


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-07 : boucle la boucle de l'enquête coût Gemini — analyse TOUTES les annonces de la
    fenêtre de la facture réelle fournie par l'utilisateur (voir PERIOD_START/PERIOD_END,
    filtrées sur `timestamp`, seul champ date disponible — écrit à la création ET ré-écrit à
    chaque ré-analyse, donc approximatif mais le seul signal exploitable). Pour chaque annonce
    de la période : reconstruit le coût de la cascade T1→T2→T3 (mêmes constantes mesurées que
    les runs #415/#417/#419 : prompt fixe par Tier + photos + sortie réelle du champ
    `aiAnalysis.analysis` quand disponible pour ce Tier) ET, si une sous-collection `chat` existe,
    le coût cumulé de toute la conversation (même méthode que le run #419 : chaque tour repaye
    l'historique). Additionne tout pour donner un total bottom-up comparable directement à la
    facture réelle Gemini de la période ($9.76 sur le CSV fourni par l'utilisateur, 1-6 sept
    2026). Lecture seule (aucune écriture Firestore), idempotent.
    """
    import statistics
    from datetime import datetime

    from backend.scripts.export_neck_reset_sample import setup_firebase
    from config import APP_ID_TARGET

    db = setup_firebase()
    period_start = datetime.fromisoformat(PERIOD_START)
    period_end = datetime.fromisoformat(PERIOD_END)

    print("🔍 Récupération de la liste des utilisateurs enregistrés...")
    users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"   {len(user_ids)} utilisateur(s) trouvé(s).")

    photo_counts = []
    tier_counts = {1: 0, 2: 0, 3: 0}
    cascade_cost_total = 0.0
    chats_found = 0
    chat_calls_total = 0
    chat_cost_total = 0.0
    deals_in_period = 0

    for uid in user_ids:
        deals_ref = db.collection('artifacts').document(APP_ID_TARGET) \
                      .collection('users').document(uid).collection('guitar_deals')
        for doc in deals_ref.stream():
            deal = doc.to_dict()
            ts = deal.get('timestamp')
            if ts is None or ts < period_start or ts >= period_end:
                continue
            deals_in_period += 1

            image_urls = deal.get('storageImageUrls') or []
            photos = len(image_urls)
            photo_counts.append(photos)

            analysis = deal.get('aiAnalysis') or {}
            model_used = analysis.get('model_used') or ''
            tier_count = min(model_used.count('->') + 1, 3) if model_used else 1
            tier_counts[tier_count] = tier_counts.get(tier_count, 0) + 1
            analysis_output_tokens = len(analysis.get('analysis') or '') // CHARS_PER_TOKEN

            # Cascade : T1 tourne toujours, T2 si tier_count>=2, T3 si tier_count>=3.
            t1_in_rate, t1_out_rate = PRICING["t1"]
            cascade_cost_total += (
                (T1_PROMPT_TOKENS + photos * TOKENS_PER_IMAGE) * t1_in_rate / 1_000_000
                + T1_OUTPUT_TOKENS_DEFAULT * t1_out_rate / 1_000_000
            )
            if tier_count >= 2:
                t2_in_rate, t2_out_rate = PRICING["t2"]
                t2_output = analysis_output_tokens if tier_count == 2 else T2_OUTPUT_TOKENS_DEFAULT
                cascade_cost_total += (
                    (T2_PROMPT_TOKENS + photos * TOKENS_PER_IMAGE) * t2_in_rate / 1_000_000
                    + t2_output * t2_out_rate / 1_000_000
                )
            if tier_count >= 3:
                t3_in_rate, t3_out_rate = PRICING["t3"]
                cascade_cost_total += (
                    (T3_PROMPT_TOKENS + photos * TOKENS_PER_IMAGE) * t3_in_rate / 1_000_000
                    + analysis_output_tokens * t3_out_rate / 1_000_000
                )

            # Chat : sous-collection lue seulement si elle existe (déals sans chat = la majorité).
            chat_docs = list(
                db.collection('artifacts').document(APP_ID_TARGET)
                  .collection('users').document(uid)
                  .collection('guitar_deals').document(doc.id)
                  .collection('chat').order_by('createdAt').stream()
            )
            if chat_docs:
                chats_found += 1
                num_calls, _, _, cost = _chat_cost_for_deal(chat_docs)
                chat_calls_total += num_calls
                chat_cost_total += cost
                print(f"💬 {doc.id} : {num_calls} appel(s) chat, coût estimé ≈ ${cost:.4f}")

    print(f"\n📦 {deals_in_period} annonce(s) dans la fenêtre {PERIOD_START} → {PERIOD_END}.")
    if photo_counts:
        print(
            f"📊 Photos par annonce : moyenne={statistics.mean(photo_counts):.1f}, "
            f"médiane={statistics.median(photo_counts):.0f}, max={max(photo_counts)}"
        )
    print(f"🎯 Répartition par Tier atteint : T1 seul={tier_counts.get(1, 0)}, "
          f"T2={tier_counts.get(2, 0)}, T3={tier_counts.get(3, 0)}")
    print(f"💬 {chats_found} annonce(s) avec conversation de chat ({chat_calls_total} appels modèle au total).")
    print(f"\n💰 Coût cascade T1-T3 estimé sur la période ≈ ${cascade_cost_total:.4f}")
    print(f"💰 Coût chat estimé sur la période ≈ ${chat_cost_total:.4f}")
    print(f"💰 TOTAL bottom-up estimé ≈ ${cascade_cost_total + chat_cost_total:.4f}")
    print(f"💵 Facture Gemini API réelle fournie par l'utilisateur (1-6 sept 2026, CSV) : $9.76")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
