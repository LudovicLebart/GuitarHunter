"""
Export à l'échelle du Dataset A (docs/management/plans/NECK_RESET_VISION_PLAN.md §3/§3ter) :
manifeste de toutes les annonces guitare (acoustique, classique, électrique, basse — tous
types, contrairement à export_neck_reset_sample.py qui restait limité à acoustique/classique
pour l'Étape 0) avec au moins une photo déjà en Firebase Storage.

Contrairement à export_neck_reset_sample.py (échantillon de 50 pour revue visuelle humaine,
sortie HTML), ce script exporte le corpus complet en JSON Lines — pensé pour alimenter le
pipeline de labellisation automatisée des keypoints (§3bis), pas pour une revue manuelle.

Exclusion des items rejetés : `status == 'rejected'` (legacy) ou `aiAnalysis.verdict` dans
REJECTED_ITEM/REJECTED_SERVICE/REJECTED. BAD_DEAL est volontairement CONSERVÉ — ce n'est pas
un rejet (cf. CLAUDE.md § Points d'Attention Critiques, "BAD_DEAL ≠ REJECTED") : la guitare est
réelle et photographiée, juste jugée trop chère par l'IA, donc pleinement utilisable pour
Dataset A.

Lecture seule, aucune écriture Firestore. Nécessite un accès Firestore réel (voir
export_neck_reset_sample.py pour le contexte d'exécution via CI, ops/run-script).

Usage :
  python -m backend.scripts.export_dataset_a
  python -m backend.scripts.export_dataset_a --output dataset_a_manifest.jsonl
"""

import sys
import os
import json
import argparse
from collections import Counter

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import firebase_admin
from firebase_admin import credentials, firestore
from config import FIREBASE_KEY_PATH, APP_ID_TARGET

# Feuilles de la taxonomie sous le nœud "guitare" (prompts.json::taxonomy_master) — exclut
# volontairement amplificateur/etui_housse, hors sujet pour la détection de keypoints guitare.
GUITAR_LEAF_MARKERS = ("electrique", "acoustique_acier", "electro_acoustique", "classique_nylon", "basse")

REJECTED_VERDICTS = {"REJECTED_ITEM", "REJECTED_SERVICE", "REJECTED"}


def setup_firebase():
    if not firebase_admin._apps:
        if not os.path.exists(FIREBASE_KEY_PATH):
            print(f"❌ Erreur : Fichier de clé introuvable à {FIREBASE_KEY_PATH}")
            sys.exit(1)
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def is_guitar(deal):
    classification = ((deal.get('aiAnalysis') or {}).get('classification') or '').lower()
    return any(marker in classification for marker in GUITAR_LEAF_MARKERS)


def is_rejected(deal):
    if deal.get('status') == 'rejected':
        return True
    verdict = (deal.get('aiAnalysis') or {}).get('verdict')
    return verdict in REJECTED_VERDICTS


def collect(db, user_ids):
    records = []
    classification_counts = Counter()
    skipped_rejected = 0
    skipped_no_photo = 0
    skipped_not_guitar = 0

    for uid in user_ids:
        deals_ref = db.collection('artifacts').document(APP_ID_TARGET) \
                      .collection('users').document(uid).collection('guitar_deals')
        for doc in deals_ref.stream():
            deal = doc.to_dict()

            if is_rejected(deal):
                skipped_rejected += 1
                continue

            image_urls = deal.get('storageImageUrls') or []
            if not image_urls:
                skipped_no_photo += 1
                continue

            if not is_guitar(deal):
                skipped_not_guitar += 1
                continue

            classification = (deal.get('aiAnalysis') or {}).get('classification', 'N/A')
            classification_counts[classification] += 1

            records.append({
                'deal_id': doc.id,
                'user_id': uid,
                'title': deal.get('title', doc.id),
                'classification': classification,
                'verdict': (deal.get('aiAnalysis') or {}).get('verdict'),
                'image_urls': image_urls,
            })

    return records, classification_counts, skipped_rejected, skipped_no_photo, skipped_not_guitar


def main():
    parser = argparse.ArgumentParser(description="Export à l'échelle du Dataset A (toutes guitares, items rejetés exclus).")
    parser.add_argument("--output", default="dataset_a_manifest.jsonl", help="Chemin du manifeste JSON Lines de sortie.")
    args = parser.parse_args()

    db = setup_firebase()

    print("🔍 Récupération de la liste des utilisateurs enregistrés...")
    users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"   {len(user_ids)} utilisateur(s) trouvé(s).")

    print("📦 Parcours de toutes les annonces guitare (tous types, items rejetés exclus)...")
    records, classification_counts, skipped_rejected, skipped_no_photo, skipped_not_guitar = collect(db, user_ids)

    total_images = sum(len(r['image_urls']) for r in records)

    with open(args.output, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f"\n✅ {len(records)} annonce(s) retenue(s) → {total_images} photo(s) au total → {args.output}")
    print(f"   Exclues : {skipped_rejected} rejetée(s), {skipped_no_photo} sans photo, {skipped_not_guitar} hors périmètre guitare (ampli/étui/autre).")
    print("\n--- Répartition par classification ---")
    for classification, count in classification_counts.most_common(20):
        print(f"   {classification:40s} {count}")


if __name__ == "__main__":
    main()
