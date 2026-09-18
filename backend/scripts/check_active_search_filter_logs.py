"""
Diagnostic en LECTURE SEULE de l'efficacité du filtre "Recherche Active" (Chantier G).

Contexte : demande utilisateur de vérifier, depuis les données réelles côté serveur, ce que le
filtre `analysisConfig.activeSearchFamilies` laisse effectivement passer vers T2/T3 par rapport à
ce qu'il écarte (verdict `NOT_PROMOTED`, voir `backend/analyzer.py::_run_analysis_cascade`).

Le message de log `self.logger.info("🔎 Hors recherche active...")` (visible dans le LogViewer)
ne contient PAS la classification de l'annonce écartée — juste la liste de familles actives et le
verdict du Portier. Pour savoir CE QUI est réellement filtré (et CE QUI passe), ce script lit
directement les documents `guitar_deals` (champ `aiAnalysis.gatekeeperClassification`), plus fiable
et plus précis qu'un grep de texte de log.

Usage (exécuté via backend/scripts/run_once.py, seul contexte où les credentials Firebase sont en
place en production — voir CLAUDE.md) :
    python backend/scripts/check_active_search_filter_logs.py
    python backend/scripts/check_active_search_filter_logs.py --user-id UID
"""
import sys
import os
import argparse
from collections import Counter

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from config import FIREBASE_KEY_PATH, APP_ID_TARGET

RECENT_SAMPLE_SIZE = 60


def setup_firebase():
    if not firebase_admin._apps:
        if not os.path.exists(FIREBASE_KEY_PATH):
            print(f"❌ Erreur : Fichier de clé introuvable à {FIREBASE_KEY_PATH}")
            sys.exit(1)
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def print_top(counter, label, limit=15):
    if not counter:
        print(f"      (aucune)")
        return
    for classification, count in counter.most_common(limit):
        print(f"      {count:>4}  {classification or '(classification absente)'}")
    remaining = sum(counter.values()) - sum(c for _, c in counter.most_common(limit))
    if remaining > 0:
        print(f"      ... +{remaining} autres ({label})")


def check_user(db, uid, email):
    user_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users').document(uid)
    user_doc = user_ref.get()
    if not user_doc.exists:
        return
    config = user_doc.to_dict().get('analysisConfig') or {}
    active_families = config.get('activeSearchFamilies') or []

    print(f"\n{'=' * 90}")
    print(f"Utilisateur : {email or uid} ({uid[:8]}...)")
    print(f"activeSearchFamilies : {active_families or '(vide — comportement par défaut, tout analyser)'}")

    if not active_families:
        print("  → Aucun filtre actif pour cet utilisateur, rien à vérifier.")
        return

    deals_ref = user_ref.collection('guitar_deals')

    # 1. Total réel écarté (NOT_PROMOTED), toute la rétention Firestore confondue.
    not_promoted_docs = list(
        deals_ref.where(filter=FieldFilter('aiAnalysis.verdict', '==', 'NOT_PROMOTED')).stream()
    )
    not_promoted_classifications = Counter(
        (d.to_dict().get('aiAnalysis') or {}).get('gatekeeperClassification') for d in not_promoted_docs
    )
    print(f"\n  Total NOT_PROMOTED (écartées par le filtre, jamais envoyées à T2/T3) : {len(not_promoted_docs)}")
    print(f"  Classifications écartées (top 15) :")
    print_top(not_promoted_classifications, "écartées")

    # 2. Échantillon récent (toutes analyses confondues) pour voir ce qui passe VS ce qui est
    # écarté sur la même fenêtre temporelle — évite de comparer un total historique (1) à un
    # instantané non représentatif.
    recent_docs = list(
        deals_ref.order_by('timestamp', direction=firestore.Query.DESCENDING)
        .limit(RECENT_SAMPLE_SIZE).stream()
    )
    recent_not_promoted = 0
    recent_promoted_classifications = Counter()
    for d in recent_docs:
        analysis = d.to_dict().get('aiAnalysis') or {}
        if analysis.get('verdict') == 'NOT_PROMOTED':
            recent_not_promoted += 1
        else:
            recent_promoted_classifications[analysis.get('gatekeeperClassification')] += 1

    print(f"\n  Sur les {len(recent_docs)} dernières annonces traitées (toutes classifications) :")
    print(f"    Écartées (NOT_PROMOTED) : {recent_not_promoted}")
    print(f"    Promues vers T2/T3 (correspond au filtre, ou pépite) : {len(recent_docs) - recent_not_promoted}")
    print(f"  Classifications promues (top 15) :")
    print_top(recent_promoted_classifications, "promues")


def main():
    parser = argparse.ArgumentParser(description="Vérifie l'efficacité réelle du filtre Recherche Active (lecture seule)")
    parser.add_argument("--user-id", help="Limiter à un seul UID (défaut : tous les utilisateurs)")
    args = parser.parse_args()

    db = setup_firebase()

    if args.user_id:
        targets = [(args.user_id, None)]
    else:
        from firebase_admin import auth
        targets = [(u.uid, u.email) for u in auth.list_users().iterate_all()]

    for uid, email in targets:
        check_user(db, uid, email)


if __name__ == "__main__":
    main()
