"""


Script "one-shot" exécuté automatiquement à CHAQUE déploiement
(.github/workflows/deploy.yml, job `deploy`, étape "Script de maintenance ponctuel") —
ce job est le seul contexte où le serveur a déjà les credentials Firebase en place
(.env / backend/config/serviceAccountKey.json écrits juste avant dans le même job).

Sert à exécuter une action ponctuelle en production (ex: script de migration) depuis un
environnement de dev qui n'a lui-même aucun accès à Firestore.

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

ACTIVE = False

# Annonce ciblée par l'utilisateur (2026-09-06/07) : conversation de chat réelle, pour estimer
# le vrai coût en tokens cumulé sur toute la conversation (chaque tour Gemini renvoie l'historique
# complet en entrée, donc le coût croît avec le nombre de tours, pas linéairement).
TARGET_DEAL_ID = "1021543367184410"

CHARS_PER_TOKEN = 4  # approximation grossière (pas le vrai tokenizer Gemini, non disponible ici)
TOKENS_PER_IMAGE = 900  # calibré sur les tokens/photo réels mesurés côté cascade T1 (run #415)
# SYSTEM_INSTRUCTION (geminiChatService.js) : ~700 caractères, fixe, envoyé à CHAQUE appel du chat
# (pas seulement au premier tour) — via le paramètre systemInstruction du modèle, jamais dans
# `parts` donc invisible dans les documents `chat` eux-mêmes.
SYSTEM_INSTRUCTION_CHARS = 700


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-07 : suite après l'extraction de la conversation (run #417) — l'utilisateur demande
    une estimation du coût réel en tokens de toute la conversation. Un chat Gemini renvoie
    l'historique COMPLET à chaque tour (pas juste le dernier message) : le coût cumulé croît donc
    avec le carré du nombre de tours, pas linéairement. Reconstruit ce cumul tour par tour à
    partir de `parts` (pas `displayText` — `parts` inclut le contexte de plan de restauration
    injecté invisiblement à chaque tour utilisateur, voir buildRestorationPlanContextText,
    geminiChatService.js) : pour chaque message modèle, input = tout ce qui précède (cumul texte
    + images déjà vues) + SYSTEM_INSTRUCTION_CHARS fixe ; output = la taille de ce message modèle
    lui-même. Approximation grossière (CHARS_PER_TOKEN=4, pas le vrai tokenizer Gemini,
    inaccessible ici) — donne un ordre de grandeur, pas un chiffre facturé exact. Lecture seule
    (aucune écriture Firestore), idempotent.

    Exécuté le 2026-09-07 (run GitHub Actions #419) : 20 appels modèle sur la conversation
    complète (aucun marqué isError, malgré les 4 placeholders "⚠️ Erreur" vus au run #417 — leur
    contenu compte quand même dans le cumul, output≈14 tokens chacun, l'essentiel du coût de ces
    tours vient de l'input déjà accumulé à ce point). Input cumulé ≈162 051 tokens, output cumulé
    ≈7 570 tokens, total ≈169 621 tokens. Coût estimé (tarif gemini-3.1-pro-preview) ≈$0.41 pour
    CETTE SEULE conversation — à comparer aux ~$0.004-0.005 estimés pour toute la cascade T1-T3
    de cette même annonce (run #415) : le chat coûterait ~80-100x plus que l'analyse automatique.
    Croissance de l'input par appel clairement super-linéaire (2 121 → 14 419 tokens du 1er au
    20e appel), confirmant que chaque tour repaye l'historique complet. ACTIVE repassé à False.
    """
    from backend.scripts.export_neck_reset_sample import setup_firebase
    from config import APP_ID_TARGET

    db = setup_firebase()

    print("🔍 Récupération de la liste des utilisateurs enregistrés...")
    users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"   {len(user_ids)} utilisateur(s) trouvé(s).")

    deal_doc = None
    owner_uid = None
    for uid in user_ids:
        ref = db.collection('artifacts').document(APP_ID_TARGET) \
                .collection('users').document(uid).collection('guitar_deals').document(TARGET_DEAL_ID)
        snap = ref.get()
        if snap.exists:
            deal_doc = snap
            owner_uid = uid
            break

    if deal_doc is None:
        print(f"❌ Annonce {TARGET_DEAL_ID} introuvable chez aucun des {len(user_ids)} utilisateurs.")
        return

    deal = deal_doc.to_dict()
    print(f"📄 Annonce trouvée chez l'utilisateur {owner_uid[:8]}… : \"{deal.get('title', 'N/A')}\"")

    chat_ref = db.collection('artifacts').document(APP_ID_TARGET) \
                 .collection('users').document(owner_uid) \
                 .collection('guitar_deals').document(TARGET_DEAL_ID).collection('chat') \
                 .order_by('createdAt')
    messages = list(chat_ref.stream())
    print(f"💬 {len(messages)} message(s) dans la conversation.\n")

    def parts_stats(parts):
        text_chars = 0
        n_images = 0
        for p in (parts or []):
            if not isinstance(p, dict):
                continue
            if p.get('text'):
                text_chars += len(p['text'])
            elif p.get('inlineData'):
                n_images += 1
        return text_chars, n_images

    cumulative_text_chars = 0
    cumulative_images = 0
    total_input_tokens = 0
    total_output_tokens = 0
    num_calls = 0
    num_errors = 0

    for i, msg_doc in enumerate(messages, 1):
        msg = msg_doc.to_dict()
        role = msg.get('role', '?')
        parts = msg.get('parts') or []
        text_chars, n_images = parts_stats(parts)

        if role == 'model':
            num_calls += 1
            input_tokens = (
                cumulative_text_chars // CHARS_PER_TOKEN
                + SYSTEM_INSTRUCTION_CHARS // CHARS_PER_TOKEN
                + cumulative_images * TOKENS_PER_IMAGE
            )
            output_tokens = text_chars // CHARS_PER_TOKEN
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
            if msg.get('isError'):
                num_errors += 1
            print(f"[{i}] model, appel #{num_calls} — input≈{input_tokens:,} tokens "
                  f"(historique : {cumulative_text_chars:,} car. + {cumulative_images} image(s)), "
                  f"output≈{output_tokens:,} tokens{' [ERREUR]' if msg.get('isError') else ''}")

        cumulative_text_chars += text_chars
        cumulative_images += n_images

    total_tokens = total_input_tokens + total_output_tokens
    print(f"\n📊 TOTAL SUR TOUTE LA CONVERSATION ({num_calls} appels, dont {num_errors} en erreur) :")
    print(f"   input cumulé ≈ {total_input_tokens:,} tokens")
    print(f"   output cumulé ≈ {total_output_tokens:,} tokens")
    print(f"   total ≈ {total_tokens:,} tokens")
    cost_low = total_input_tokens * 2.00 / 1_000_000 + total_output_tokens * 12.00 / 1_000_000
    print(f"   coût estimé (tarif gemini-3.1-pro-preview, $2.00/$12.00 par M in/out) ≈ ${cost_low:.4f}")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
