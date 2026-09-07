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

ACTIVE = True

# Annonce ciblée par l'utilisateur (2026-09-06) : une conversation de chat "qui va continuer",
# pour vérifier concrètement l'effet de l'élision de photos (Plan 1 tokens, Lot C/D,
# useDealChat.js) et la taille réelle des photos jointes par l'utilisateur depuis son téléphone
# (suspicion : peut-être pas compressées avant envoi à Gemini — à vérifier, `filesToInlineParts`
# les fait pourtant passer par le même redimensionnement 1024px/JPEG 80% que les photos
# d'annonce, voir geminiChatService.js).
TARGET_DEAL_ID = "1021543367184410"


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-06 : récupère la conversation de chat d'une annonce précise (voir TARGET_DEAL_ID)
    pour vérifier concrètement, sur un cas réel, si l'élision de vieilles photos jointes par
    l'utilisateur (`elideOldChatPhotos`, useDealChat.js, budget MAX_HISTORY_IMAGES=6) fonctionne
    comme prévu, et la taille réelle des photos jointes (prises au téléphone, donc a priori plus
    grosses que les photos d'annonce Marketplace) une fois passées par le redimensionnement
    partagé (`blobToInlinePart`, 1024px/JPEG 80%) — l'annonce elle-même ne stocke JAMAIS ses
    photos en base64 dans le chat (uniquement des URLs dans `storageImageUrls`, résolues à la
    demande), donc toute part `inlineData` trouvée ici est nécessairement une photo jointe par
    l'utilisateur. Lecture seule (aucune écriture Firestore), idempotent : essaie chaque
    utilisateur enregistré jusqu'à trouver le document, imprime pour chaque message du tour :
    rôle, texte affiché (tronqué), nombre de parts image et taille base64 totale (octets) de ces
    parts. Termine par un total agrégé sur toute la conversation.
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

    total_image_parts = 0
    total_image_bytes = 0
    for i, msg_doc in enumerate(messages, 1):
        msg = msg_doc.to_dict()
        role = msg.get('role', '?')
        display_text = (msg.get('displayText') or '').replace('\n', ' ')
        parts = msg.get('parts') or []
        image_parts = [p for p in parts if isinstance(p, dict) and p.get('inlineData')]
        msg_image_bytes = sum(len(p['inlineData'].get('data', '')) for p in image_parts)
        total_image_parts += len(image_parts)
        total_image_bytes += msg_image_bytes

        truncated = display_text[:300] + ('…' if len(display_text) > 300 else '')
        print(f"[{i}] {role} — {len(parts)} part(s), {len(image_parts)} image(s) "
              f"({msg_image_bytes:,} octets base64) — attachedImagePartIndices="
              f"{msg.get('attachedImagePartIndices')}")
        if truncated:
            print(f"    \"{truncated}\"")

    print(f"\n📊 TOTAL : {total_image_parts} part(s) image sur {len(messages)} messages, "
          f"{total_image_bytes:,} octets base64 cumulés (~{total_image_bytes * 3 // 4:,} octets image réels).")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
