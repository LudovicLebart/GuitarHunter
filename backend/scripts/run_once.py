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


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-06 : pour amorcer `backend/benchmark/dataset.json` (pipeline de benchmark
    vision Gemini/GPT-4o-mini/Qwen2.5-VL, jugé par Claude), on a besoin de quelques
    "pépites" réelles déjà passées par le Tier 3 (Expert Pro) — photos stables
    (Firebase Storage) + résumé technique détaillé. Lecture seule (aucune écriture
    Firestore), idempotent : parcourt `guitar_deals` de tous les utilisateurs, ne garde
    que les annonces où l'Expert Pro a bien été déclenché (`aiAnalysis.tier3_trigger`
    présent) ET qui ont des photos (`storageImageUrls`), trie par score combiné
    (deal_score + restoration_interest_score) décroissant — pas juste la plus récente
    scannée — et imprime les 5 meilleures en JSON dans les logs GitHub Actions.

    Exécuté le 2026-09-06 (run GitHub Actions du 03:32 UTC) : 149 annonces éligibles
    (Tier 3 déclenché + photos), 5 meilleures extraites et versées dans
    backend/benchmark/dataset.json. ACTIVE repassé à False.
    """
    import json

    from backend.scripts.export_neck_reset_sample import setup_firebase
    from config import APP_ID_TARGET

    db = setup_firebase()

    print("🔍 Récupération de la liste des utilisateurs enregistrés...")
    users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"   {len(user_ids)} utilisateur(s) trouvé(s).")

    gems = []
    for uid in user_ids:
        deals_ref = db.collection('artifacts').document(APP_ID_TARGET) \
                      .collection('users').document(uid).collection('guitar_deals')
        for doc in deals_ref.stream():
            deal = doc.to_dict()
            analysis = deal.get('aiAnalysis') or {}
            if not analysis.get('tier3_trigger'):
                continue
            image_urls = deal.get('storageImageUrls') or []
            if not image_urls:
                continue
            gems.append({
                'user_id': uid,
                'deal_id': doc.id,
                'title': deal.get('title'),
                'classification': analysis.get('classification'),
                'deal_score': analysis.get('deal_score'),
                'restoration_interest_score': analysis.get('restoration_interest_score'),
                'authenticity_score': analysis.get('authenticity_score'),
                'condition_score': analysis.get('condition_score'),
                'tier3_trigger': analysis.get('tier3_trigger'),
                'summary': analysis.get('summary'),
                'image_urls': image_urls,
                'source_url': deal.get('url'),
            })

    print(f"📦 {len(gems)} annonce(s) passée(s) par le Tier 3 avec photos.")
    gems.sort(
        key=lambda g: (g.get('deal_score') or 0) + (g.get('restoration_interest_score') or 0),
        reverse=True,
    )
    top = gems[:5]
    print("🏆 TOP 5 PÉPITES (JSON) :")
    print(json.dumps(top, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
