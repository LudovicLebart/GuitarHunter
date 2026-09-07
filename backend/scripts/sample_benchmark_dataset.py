"""
Chantier B (docs/management/plans/CHANTIER_B_PERCEPTION_RAISONNEMENT_PLAN.md §7, étape 8) :
échantillonne un jeu d'annonces réelles pour reconstruire le dataset de benchmark, en
incluant délibérément des annonces rejetées au Tier 1 (contrairement à l'ancien `dataset.json`,
qui n'avait que des annonces acceptées) — nécessaire pour mesurer le risque identifié en §1
du plan : sous l'option large, la perception remplace l'examen direct des photos sur 100% du
volume, y compris au Portier qui filtre toutes les annonces, pas seulement sur les 5% qui
atteignent le Tier 3.

Contrairement à `dataset.json` actuel, la vérité terrain n'est PAS générée ici : chaque
annonce exportée porte un `ground_truth_draft` structuré, pré-rempli à partir de la sortie
Gemini de production existante (`aiAnalysis`) — à réviser et confirmer manuellement (interface
de validation, §7 étape 9) avant tout run de benchmark. Une sortie Gemini non révisée ne peut
JAMAIS servir de vérité terrain telle quelle (comparer un candidat à Gemini contre les propres
réponses de Gemini est circulaire — correction Claude Opus, `COST_OPTIMIZATION_CHANTIERS.md`).

Dérivé de `export_neck_reset_sample.py` (échantillonnage aléatoire, lecture seule) et
`export_dataset_a.py` (filtre taxonomie guitare par préfixe complet — pas une sous-chaîne, qui
matcherait à tort des étuis, cf. bug déjà documenté dans ce dernier script).

Lecture seule, aucune écriture Firestore. Nécessite un accès Firestore réel — ce script doit
tourner via le workflow `ops/run-script` (voir `export_neck_reset_sample.py` pour le contexte),
pas depuis cet environnement de dev sandbox (`FIREBASE_KEY_PATH` absent ici).

Usage :
  python -m backend.scripts.sample_benchmark_dataset                    # 40 annonces, tous users
  python -m backend.scripts.sample_benchmark_dataset --sample-size 30
  python -m backend.scripts.sample_benchmark_dataset --seed 42          # échantillon reproductible
"""

import sys
import os
import json
import argparse
import random
from collections import defaultdict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import firebase_admin
from firebase_admin import credentials, firestore
from config import FIREBASE_KEY_PATH, APP_ID_TARGET

# Même filtre taxonomie que export_dataset_a.py (préfixe complet, pas sous-chaîne — un simple
# `marker in classification` matcherait à tort des étuis, cf. bug déjà documenté là-bas).
GUITAR_LEAF_PREFIXES = (
    "guitare.electrique",
    "guitare.acoustique_acier",
    "guitare.electro_acoustique",
    "guitare.classique_nylon",
    "guitare.basse",
)

# Verdicts qui arrêtent la cascade au Tier 1 (Portier) — DEFAULT_REJECTION_VERDICTS (config.py)
# plus les verdicts legacy de rejet pur (analyzer.py::_run_analysis_cascade, legacy_rejection).
# BAD_DEAL en fait partie ICI (arrête bien la cascade au Tier 1, analyzer.py:343) même si son
# `status` Firestore reste "analyzed" et non "rejected" (CLAUDE.md, "BAD_DEAL ≠ REJECTED" — une
# distinction de *statut produit*, pas de *tier atteint*, qui est ce qui nous intéresse ici).
T1_STOP_VERDICTS = {
    "BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE", "INCOMPLETE_DATA",
    "REJECTED", "REJECTED (SERVICE)",
}


def setup_firebase():
    if not firebase_admin._apps:
        if not os.path.exists(FIREBASE_KEY_PATH):
            print(f"❌ Erreur : Fichier de clé introuvable à {FIREBASE_KEY_PATH}")
            print("   Ce script nécessite un accès Firestore réel — voir le docstring en tête de fichier.")
            sys.exit(1)
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def is_guitar(deal):
    classification = ((deal.get('aiAnalysis') or {}).get('classification') or '').lower()
    return any(classification.startswith(prefix) for prefix in GUITAR_LEAF_PREFIXES)


def tier_reached(deal):
    """Même formule que backend/scripts/run_once.py::run() — nombre de maillons dans
    `model_used` ('gemini-x -> gemini-y -> ...'), plafonné à 3."""
    model_used = (deal.get('aiAnalysis') or {}).get('model_used') or ''
    if not model_used:
        return 1
    return min(model_used.count('->') + 1, 3)


def is_t1_rejection(deal, tier):
    if tier != 1:
        return False
    verdict = (deal.get('aiAnalysis') or {}).get('verdict')
    return deal.get('status') == 'rejected' or verdict in T1_STOP_VERDICTS


def _default_question(classification, price):
    label = classification.split('.')[-1] if classification and classification != 'N/A' else "cet instrument"
    price_part = f" par rapport à son prix affiché ({price}$)" if price else ""
    return (
        f"Identifie cette annonce ({label}) et évalue son authenticité, son état général et "
        f"sa valeur estimée{price_part}."
    )


def collect_candidates(db, user_ids):
    """Parcourt guitar_deals de tous les utilisateurs, garde les annonces guitare avec au
    moins une photo stockée — rejets Tier 1 COMPRIS (contrairement à export_dataset_a.py, qui
    les exclut pour un usage différent). Regroupé par strate pour l'échantillonnage §5."""
    by_stratum = defaultdict(list)  # clé : 'rejet_t1' | 'tier2' | 'tier3'
    for uid in user_ids:
        deals_ref = db.collection('artifacts').document(APP_ID_TARGET) \
                      .collection('users').document(uid).collection('guitar_deals')
        for doc in deals_ref.stream():
            deal = doc.to_dict()
            image_urls = deal.get('storageImageUrls') or []
            if not image_urls:
                continue
            if not is_guitar(deal):
                continue

            tier = tier_reached(deal)
            stratum = 'rejet_t1' if is_t1_rejection(deal, tier) else f'tier{tier}'

            analysis = deal.get('aiAnalysis') or {}
            classification = analysis.get('classification', 'N/A')
            price = deal.get('price')

            by_stratum[stratum].append({
                'deal_id': doc.id,
                'user_id': uid,
                'title': deal.get('title', doc.id),
                'price': price,
                'source_url': deal.get('url', ''),
                'classification': classification,
                'image_urls': image_urls,
                'tier_reached': tier,
                'stratum': stratum,
                'question': _default_question(classification, price),
                # Vérité terrain PROVISOIRE — sortie de production Gemini, jamais la vérité
                # terrain elle-même (voir docstring). Champs alignés sur le contrat JSON de
                # prod (prompts.json) pour rester comparables une fois révisés.
                'ground_truth_draft': {
                    'identification': {
                        'brand': analysis.get('brand'),
                        'model_name': analysis.get('model_name'),
                        'production_year': analysis.get('production_year'),
                        'country_of_origin': analysis.get('country_of_origin'),
                    },
                    'authenticite': {
                        'score': analysis.get('authenticity_score'),
                    },
                    'etat': {
                        'condition_score': analysis.get('condition_score'),
                        'color': analysis.get('color'),
                        'finish_application': analysis.get('finish_application'),
                        'finish_texture': analysis.get('finish_texture'),
                    },
                    'valeur': {
                        'estimated_value': analysis.get('estimated_value'),
                        'resale_potential': analysis.get('resale_potential'),
                        'estimated_gross_margin': analysis.get('estimated_gross_margin'),
                    },
                    'verdict_prod': analysis.get('verdict'),
                    'notes': '',
                },
                'confirmed': False,
            })
    return by_stratum


def stratified_sample(by_stratum, sample_size, rng):
    """Répartit l'échantillon également entre les strates disponibles (rejet_t1/tier2/tier3).
    Une strate trop petite ne fait pas échouer l'échantillonnage : son déficit — ainsi que la
    perte de la division entière (sample_size % nombre de strates) — est reporté sur le reste
    du pool plutôt que de réduire la taille totale de l'échantillon."""
    strata = [s for s in by_stratum if by_stratum[s]]
    if not strata:
        return []
    target_per_stratum = sample_size // len(strata)
    sample = []
    for stratum in strata:
        take = min(target_per_stratum, len(by_stratum[stratum]))
        sample.extend(rng.sample(by_stratum[stratum], take))
    deficit = sample_size - len(sample)
    if deficit > 0:
        chosen_ids = {item['deal_id'] for item in sample}
        pool = [item for stratum in strata for item in by_stratum[stratum] if item['deal_id'] not in chosen_ids]
        sample.extend(rng.sample(pool, min(deficit, len(pool))))
    return sample


def main():
    parser = argparse.ArgumentParser(
        description="Échantillonne un dataset de benchmark (Chantier B) avec vérité terrain provisoire à confirmer."
    )
    parser.add_argument("--sample-size", type=int, default=40, help="Taille totale de l'échantillon (défaut: 40).")
    parser.add_argument("--seed", type=int, default=None, help="Graine aléatoire pour un échantillon reproductible.")
    parser.add_argument("--output", default="benchmark_dataset_draft.json", help="Chemin du manifeste JSON de sortie.")
    args = parser.parse_args()

    db = setup_firebase()

    print("🔍 Récupération de la liste des utilisateurs enregistrés...")
    users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"   {len(user_ids)} utilisateur(s) trouvé(s).")

    print("📦 Parcours des annonces guitare avec photo (rejets Tier 1 compris)...")
    by_stratum = collect_candidates(db, user_ids)
    for stratum, items in by_stratum.items():
        print(f"   {stratum:10s} : {len(items)} annonce(s) éligible(s).")

    if not any(by_stratum.values()):
        print("❌ Aucune annonce éligible trouvée. Rien à échantillonner.")
        sys.exit(1)

    rng = random.Random(args.seed)
    sample = stratified_sample(by_stratum, args.sample_size, rng)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)

    stratum_counts = defaultdict(int)
    for item in sample:
        stratum_counts[item['stratum']] += 1
    print(f"\n✅ {len(sample)} annonce(s) échantillonnée(s) → {args.output}")
    for stratum, count in stratum_counts.items():
        print(f"   {stratum:10s} : {count}")
    print("\n⚠️  ground_truth_draft est une SORTIE DE PRODUCTION GEMINI, pas une vérité terrain —")
    print("   à réviser/confirmer via l'interface de validation (§7 étape 9) avant tout run de benchmark.")


if __name__ == "__main__":
    main()
