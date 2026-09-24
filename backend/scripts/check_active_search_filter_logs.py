"""
Diagnostic en LECTURE SEULE de l'efficacité du filtre "Recherche Active" (Chantier G).

Contexte : demande utilisateur de vérifier, depuis les données réelles côté serveur, ce que le
filtre `analysisConfig.activeSearchFamilies` laisse effectivement passer vers T2/T3 par rapport à
ce qu'il écarte (verdict `NOT_PROMOTED`, voir `backend/analyzer.py::_run_analysis_cascade`).

Deux sources, lues l'une et l'autre :
1. **Le vrai fichier de log serveur** (`logging_config.py::LOG_DIR`, `logs/bot_{uid[:8]}.log`,
   relatif au `cwd` du processus bot — identique à celui de ce script quand il tourne via
   `run_once.py` sur le même serveur/répertoire, voir `.github/workflows/deploy.yml` job `deploy`).
   Correction utilisateur (2026-09-18) : c'est la source de vérité actuelle, pas Firestore.
   Correction revue de code (2026-09-20) : `backupCount=0` sur un `TimedRotatingFileHandler` ne
   supprime PAS les anciens fichiers (contrairement à l'hypothèse précédente) — chaque rotation
   minuit UTC renomme l'ancien fichier en lui ajoutant un suffixe de date
   (`bot_{uid[:8]}.log.2026-09-19`) et ceux-ci s'accumulent indéfiniment ; seul le fichier SANS
   suffixe est la journée en cours. Contient les lignes `🔎 Hors recherche active (...)` mais PAS
   la classification exacte de l'annonce écartée (le message ne l'inclut pas).
2. **Les documents `guitar_deals`** (`aiAnalysis.gatekeeperClassification`) pour savoir précisément
   QUELLES classifications sont écartées vs promues — complémentaire au fichier de log, qui donne le
   volume/la fréquence mais pas le détail par catégorie.

Usage (exécuté via backend/scripts/run_once.py, seul contexte où les credentials Firebase sont en
place en production — voir CLAUDE.md) :
    python backend/scripts/check_active_search_filter_logs.py
    python backend/scripts/check_active_search_filter_logs.py --user-id UID
"""
import sys
import os
import glob
import argparse
from collections import Counter

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from config import FIREBASE_KEY_PATH, APP_ID_TARGET

RECENT_SAMPLE_SIZE = 60
LOG_DIR = os.path.join(os.getcwd(), 'logs')  # même calcul que backend/logging_config.py::LOG_DIR
NOT_PROMOTED_MARKER = "Hors recherche active"
TIER2_MARKER = "Étape 2 : Analyste"
TAIL_EXCERPT_LINES = 20


def read_server_log_files(uid_prefix=None):
    """Lit directement le(s) fichier(s) de log serveur (source de vérité — voir docstring).

    Motif corrigé le 2026-09-20 (revue de code) : `bot_*.log` seul ne matchait que le fichier du
    jour courant, pas les fichiers tournés (`bot_xxx.log.2026-09-19`, jamais supprimés — voir
    docstring du module) — `bot_*.log*` couvre les deux."""
    base = f"bot_{uid_prefix}" if uid_prefix else "bot_"
    pattern = os.path.join(LOG_DIR, f"{base}*.log*")
    log_files = sorted(glob.glob(pattern))

    print(f"\n{'#' * 90}")
    print(f"FICHIERS DE LOG SERVEUR ({LOG_DIR})")
    if not log_files:
        print(f"  Aucun fichier trouvé pour le motif '{pattern}'.")
        print(f"  (rotation quotidienne UTC, backupCount=0 — seule la journée en cours est conservée)")
        return

    for path in log_files:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        not_promoted_lines = [l for l in lines if NOT_PROMOTED_MARKER in l]
        tier2_lines = [l for l in lines if TIER2_MARKER in l]

        print(f"\n  {os.path.basename(path)} — {len(lines)} lignes")
        print(f"    '{NOT_PROMOTED_MARKER}' (écartées par le filtre) : {len(not_promoted_lines)}")
        print(f"    '{TIER2_MARKER}' (promues vers T2/T3)            : {len(tier2_lines)}")

        relevant = [l for l in lines if NOT_PROMOTED_MARKER in l or TIER2_MARKER in l]
        if relevant:
            print(f"    Dernières lignes pertinentes (max {TAIL_EXCERPT_LINES}) :")
            for line in relevant[-TAIL_EXCERPT_LINES:]:
                print(f"      {line.rstrip()}")


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

    read_server_log_files(uid_prefix=args.user_id[:8] if args.user_id else None)

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
