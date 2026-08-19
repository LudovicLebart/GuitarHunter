"""
Diagnostic ponctuel : compare la résolution réelle des images stockées (Firebase Storage)
selon la plateforme d'origine de l'annonce (Facebook vs Kijiji).

Contexte : docs/management/plans/NECK_RESET_VISION_PLAN.md — on a mesuré que les photos
Facebook échantillonnées font ~720x960px (résolution d'affichage du carrousel DOM, pas
forcément l'original uploadé par le vendeur — backend/scraping/parser.py lit `img.src` sans
vérifier `srcset`). Kijiji lit ses images depuis le JSON structuré `__NEXT_DATA__`
(backend/scraping/kijiji/parser.py), une source a priori plus fiable pour obtenir l'URL
canonique/originale. Ce script vérifie si l'écart de résolution se confirme dans les faits.

Identification de la plateforme : les deal_id Kijiji sont préfixés `kijiji_`
(cf. CLAUDE.md § Points d'Attention Critiques — "préfixe kijiji_ de l'ID").

Lecture seule, aucune écriture Firestore. Nécessite un accès Firestore réel
(voir backend/scripts/export_neck_reset_sample.py pour le contexte d'exécution via CI).

Usage :
  python -m backend.scripts.compare_image_resolution_by_source
  python -m backend.scripts.compare_image_resolution_by_source --sample-per-source 15
"""

import sys
import os
import argparse
import random
import statistics
from io import BytesIO

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import requests
import firebase_admin
from firebase_admin import credentials, firestore
from PIL import Image
from config import FIREBASE_KEY_PATH, APP_ID_TARGET

ACOUSTIC_MARKERS = ("acoustique", "classique")


def setup_firebase():
    if not firebase_admin._apps:
        if not os.path.exists(FIREBASE_KEY_PATH):
            print(f"❌ Erreur : Fichier de clé introuvable à {FIREBASE_KEY_PATH}")
            sys.exit(1)
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def is_acoustic_or_classical(deal):
    classification = (deal.get('aiAnalysis') or {}).get('classification') or ''
    return any(marker in classification.lower() for marker in ACOUSTIC_MARKERS)


def source_of(deal_id):
    return "kijiji" if deal_id.startswith("kijiji_") else "facebook"


def collect_candidates(db, user_ids):
    buckets = {"facebook": [], "kijiji": []}
    for uid in user_ids:
        deals_ref = db.collection('artifacts').document(APP_ID_TARGET) \
                      .collection('users').document(uid).collection('guitar_deals')
        for doc in deals_ref.stream():
            deal = doc.to_dict()
            image_urls = deal.get('storageImageUrls') or []
            if not image_urls or not is_acoustic_or_classical(deal):
                continue
            buckets[source_of(doc.id)].append({
                'deal_id': doc.id,
                'title': deal.get('title', doc.id),
                'image_url': image_urls[0],
            })
    return buckets


def measure(image_url):
    response = requests.get(image_url, timeout=15)
    response.raise_for_status()
    img = Image.open(BytesIO(response.content))
    return img.size[0], img.size[1], len(response.content)


def report_source(name, sample):
    print(f"\n=== {name.upper()} — {len(sample)} annonce(s) mesurée(s) ===")
    widths, heights, sizes_kb = [], [], []
    for d in sample:
        try:
            w, h, nbytes = measure(d['image_url'])
        except Exception as e:
            print(f"  ⚠️  {d['deal_id']} — échec mesure ({e})")
            continue
        widths.append(w)
        heights.append(h)
        sizes_kb.append(nbytes / 1024)
        print(f"  {d['title'][:45]:45s} {w:5d}x{h:<5d}  {nbytes/1024:6.1f} Ko")

    if widths:
        print(f"  --- Moyenne : {statistics.mean(widths):.0f}x{statistics.mean(heights):.0f}px, "
              f"{statistics.mean(sizes_kb):.1f} Ko | "
              f"Max : {max(widths)}x{max(heights)}px | Min : {min(widths)}x{min(heights)}px")


def main():
    parser = argparse.ArgumentParser(description="Compare la résolution des images Storage par plateforme d'origine (Facebook vs Kijiji).")
    parser.add_argument("--sample-per-source", type=int, default=15, help="Nombre d'annonces à mesurer par plateforme (défaut: 15).")
    parser.add_argument("--seed", type=int, default=None, help="Graine aléatoire pour un échantillon reproductible.")
    args = parser.parse_args()

    db = setup_firebase()

    print("🔍 Récupération de la liste des utilisateurs enregistrés...")
    users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"   {len(user_ids)} utilisateur(s) trouvé(s).")

    print("📦 Parcours des annonces acoustique/classique avec photos, classées par plateforme...")
    buckets = collect_candidates(db, user_ids)
    print(f"   Facebook : {len(buckets['facebook'])} annonce(s) éligible(s).")
    print(f"   Kijiji   : {len(buckets['kijiji'])} annonce(s) éligible(s).")

    rng = random.Random(args.seed)
    for name in ("facebook", "kijiji"):
        pool = buckets[name]
        if not pool:
            print(f"\n=== {name.upper()} — aucune annonce éligible, rien à mesurer ===")
            continue
        sample = rng.sample(pool, min(args.sample_per_source, len(pool)))
        report_source(name, sample)


if __name__ == "__main__":
    main()
