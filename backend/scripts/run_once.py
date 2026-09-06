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


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-06 : pour remplacer les suppositions du benchmark de coût Gemini (nombre de
    photos/annonce, longueur de sortie par Tier) par de vraies distributions mesurées.
    Lecture seule (aucune écriture Firestore), idempotent : parcourt `guitar_deals` de
    tous les utilisateurs, mesure pour chaque annonce analysée le nombre de photos
    (`storageImageUrls`) et la longueur du champ `aiAnalysis.analysis` (le rapport
    Markdown/puces produit par le dernier Tier exécuté), ventilée selon que le Tier 3 a
    été déclenché ou non (déduit du nombre de maillons dans `aiAnalysis.model_used`,
    ex: "gemini-3.5-flash-lite -> gemini-3.7-flash" = 2 maillons = pas de T3 ;
    "... -> gemini-3.1-pro-preview" = 3 maillons = T3 déclenché). Imprime des
    statistiques agrégées (moyenne/médiane/min/max), pas les données brutes.
    """
    import statistics

    from backend.scripts.export_neck_reset_sample import setup_firebase
    from config import APP_ID_TARGET

    db = setup_firebase()

    print("🔍 Récupération de la liste des utilisateurs enregistrés...")
    users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"   {len(user_ids)} utilisateur(s) trouvé(s).")

    photo_counts = []
    analysis_len_no_t3 = []
    analysis_len_t3 = []
    total_deals = 0

    for uid in user_ids:
        deals_ref = db.collection('artifacts').document(APP_ID_TARGET) \
                      .collection('users').document(uid).collection('guitar_deals')
        for doc in deals_ref.stream():
            deal = doc.to_dict()
            analysis = deal.get('aiAnalysis') or {}
            if not analysis:
                continue
            total_deals += 1

            image_urls = deal.get('storageImageUrls') or []
            photo_counts.append(len(image_urls))

            analysis_text = analysis.get('analysis') or ''
            model_used = analysis.get('model_used') or ''
            tier_count = model_used.count('->') + 1 if model_used else 0
            if tier_count >= 3:
                analysis_len_t3.append(len(analysis_text))
            elif tier_count == 2 and analysis_text:
                analysis_len_no_t3.append(len(analysis_text))

    def print_stats(values, label):
        if not values:
            print(f"📊 {label} : aucune donnée")
            return
        print(
            f"📊 {label} : n={len(values)}, moyenne={statistics.mean(values):.0f}, "
            f"médiane={statistics.median(values):.0f}, min={min(values)}, max={max(values)}"
        )

    print(f"📦 {total_deals} annonce(s) analysée(s) au total.")
    print_stats(photo_counts, "Photos par annonce")
    print_stats(analysis_len_no_t3, "Longueur champ 'analysis' en caractères (Tier 2 seul, sans T3)")
    print_stats(analysis_len_t3, "Longueur champ 'analysis' en caractères (Tier 3 déclenché)")
    n_t3 = len(analysis_len_t3)
    n_no_t3 = len(analysis_len_no_t3)
    denom = n_t3 + n_no_t3
    if denom:
        print(f"🎯 Part Tier 3 déclenché : {n_t3}/{denom} ({100 * n_t3 / denom:.1f}%)")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
