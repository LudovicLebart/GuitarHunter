"""
Étape 0 du plan "Détection visuelle neck reset" (docs/management/plans/NECK_RESET_VISION_PLAN.md §4).

Échantillonne aléatoirement des annonces acoustique/classique déjà scrapées (tous
utilisateurs confondus) et génère une page HTML locale affichant leurs photos, pour
compter à la main combien ont au moins une vue exploitable (guitare assez grande dans
le cadre, zone manche/chevalet nette) — c'est ce chiffre qui décide de la viabilité du
projet, pas l'architecture du pipeline.

Ce script ne modifie rien dans Firestore (lecture seule) et ne nécessite aucune
dépendance au-delà de firebase-admin (déjà dans requirements.txt).

Prérequis : ce script doit tourner dans un environnement avec accès Firestore réel
(FIREBASE_KEY_PATH valide) — l'environnement de dev sandbox n'en a pas
(cf. CLAUDE.md § Points d'Attention Critiques).

Usage :
  python -m backend.scripts.export_neck_reset_sample                       # 50 annonces, tous users
  python -m backend.scripts.export_neck_reset_sample --sample-size 80
  python -m backend.scripts.export_neck_reset_sample --user-id UID
  python -m backend.scripts.export_neck_reset_sample --seed 42             # échantillon reproductible
"""

import sys
import os
import argparse
import random
import html

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import firebase_admin
from firebase_admin import credentials, firestore
from config import FIREBASE_KEY_PATH, APP_ID_TARGET

# Sous-chaînes de classification (aiAnalysis.classification, cf. prompts.json taxonomy_master)
# considérées comme acoustique/classique. "electro_acoustique" contient déjà "acoustique".
ACOUSTIC_MARKERS = ("acoustique", "classique")


def setup_firebase():
    if not firebase_admin._apps:
        if not os.path.exists(FIREBASE_KEY_PATH):
            print(f"❌ Erreur : Fichier de clé introuvable à {FIREBASE_KEY_PATH}")
            print("   Ce script nécessite un accès Firestore réel — voir le docstring en tête de fichier.")
            sys.exit(1)
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def is_acoustic_or_classical(deal):
    classification = (deal.get('aiAnalysis') or {}).get('classification') or ''
    classification = classification.lower()
    return any(marker in classification for marker in ACOUSTIC_MARKERS)


def collect_candidates(db, user_ids):
    """Parcourt guitar_deals de chaque utilisateur, retourne les annonces acoustique/classique avec photos."""
    candidates = []
    for uid in user_ids:
        deals_ref = db.collection('artifacts').document(APP_ID_TARGET) \
                      .collection('users').document(uid).collection('guitar_deals')
        for doc in deals_ref.stream():
            deal = doc.to_dict()
            image_urls = deal.get('storageImageUrls') or []
            if not image_urls:
                continue
            if not is_acoustic_or_classical(deal):
                continue
            candidates.append({
                'user_id': uid,
                'deal_id': doc.id,
                'title': deal.get('title', doc.id),
                'classification': (deal.get('aiAnalysis') or {}).get('classification', 'N/A'),
                'image_urls': image_urls,
                'source_url': deal.get('url', ''),
            })
    return candidates


def build_html_report(sample, output_path):
    cards = []
    for i, d in enumerate(sample, 1):
        imgs_html = "".join(
            f'<img src="{html.escape(u)}" loading="lazy">' for u in d['image_urls']
        )
        source_link_html = ""
        if d['source_url']:
            safe_url = html.escape(d['source_url'])
            source_link_html = f'<p class="meta"><a href="{safe_url}" target="_blank">annonce d’origine</a></p>'
        cards.append(f"""
        <section class="card">
          <h2>#{i} — {html.escape(d['title'])}</h2>
          <p class="meta">classification: {html.escape(str(d['classification']))} · deal_id: {html.escape(d['deal_id'])} · user: {html.escape(d['user_id'][:8])}…</p>
          {source_link_html}
          <div class="verdict">
            <label><input type="radio" name="v{i}" value="oui"> exploitable</label>
            <label><input type="radio" name="v{i}" value="non"> pas exploitable</label>
          </div>
          <div class="gallery">{imgs_html}</div>
        </section>
        """)

    page = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<title>Étape 0 — Échantillon photos neck reset ({len(sample)} annonces)</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 0 auto; padding: 1.5rem; background: #fafafa; }}
  h1 {{ font-size: 1.3rem; }}
  .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; }}
  .card h2 {{ font-size: 1rem; margin: 0 0 0.25rem; }}
  .meta {{ color: #666; font-size: 0.85rem; margin: 0.15rem 0; }}
  .verdict {{ margin: 0.5rem 0; font-size: 0.9rem; }}
  .verdict label {{ margin-right: 1rem; }}
  .gallery {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }}
  .gallery img {{ max-height: 220px; border-radius: 4px; border: 1px solid #ccc; }}
</style></head>
<body>
<h1>Étape 0 — {len(sample)} annonces acoustique/classique échantillonnées</h1>
<p>Pour chaque annonce, compte si au moins une photo permet de voir nettement la zone manche/chevalet (assez grande dans le cadre, pas floue). Le choix "exploitable/pas exploitable" ci-dessous n'est PAS sauvegardé (page statique) — note juste le total à la main ou dans un fichier à part.</p>
{"".join(cards)}
</body></html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(page)


def main():
    parser = argparse.ArgumentParser(description="Étape 0 : échantillon de photos acoustique/classique pour évaluer le taux d'exploitabilité.")
    parser.add_argument("--sample-size", type=int, default=50, help="Nombre d'annonces à échantillonner (défaut: 50).")
    parser.add_argument("--user-id", help="Limiter à un seul UID Firebase (défaut: tous les utilisateurs enregistrés).")
    parser.add_argument("--seed", type=int, default=None, help="Graine aléatoire pour un échantillon reproductible.")
    parser.add_argument("--output", default="neck_reset_sample.html", help="Chemin du fichier HTML de sortie (défaut: neck_reset_sample.html).")
    args = parser.parse_args()

    db = setup_firebase()

    if args.user_id:
        user_ids = [args.user_id]
    else:
        print("🔍 Récupération de la liste des utilisateurs enregistrés...")
        users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
        user_ids = [doc.id for doc in users_ref.stream()]
        print(f"   {len(user_ids)} utilisateur(s) trouvé(s).")

    print("📦 Parcours des annonces acoustique/classique avec photos...")
    candidates = collect_candidates(db, user_ids)
    print(f"   {len(candidates)} annonce(s) éligible(s) (acoustique/classique + au moins 1 photo).")

    if not candidates:
        print("❌ Aucune annonce éligible trouvée. Rien à échantillonner.")
        sys.exit(1)

    rng = random.Random(args.seed)
    sample_size = min(args.sample_size, len(candidates))
    sample = rng.sample(candidates, sample_size)

    build_html_report(sample, args.output)
    print(f"✅ {sample_size} annonce(s) échantillonnée(s) → {args.output}")
    print("   Ouvre ce fichier dans un navigateur et compte à la main le nombre d'annonces exploitables.")


if __name__ == "__main__":
    main()
