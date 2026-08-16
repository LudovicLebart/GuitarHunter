"""
Audit + normalisation des classifications taxonomiques (2026-08-16) — GRATUIT, AUCUN APPEL GEMINI.

Contexte : jusqu'au correctif du 2026-08-16, `aiAnalysis.classification` pouvait contenir
indifféremment un chemin complet, un nom de feuille, ou un nom générique ambigu (le prompt ne
précisait pas le format attendu). Un nom nu comme "Guitare Electrique" est structurellement
ambigu — c'est à la fois une feuille de `etui_housse.Etui_Rigide` et la lecture du chemin
`guitare.electrique` — et c'est ce qui faisait compter des étuis comme des guitares.

Ce script fait DEUX choses, dans la même passe :

  1. AUDIT (toujours) : classe chaque annonce selon ce que donne
     `backend/taxonomy.py::canonicalize()` — `exact_path`, `leaf`, `ambiguous`, `unknown`,
     `empty` — et affiche le détail des valeurs problématiques avec des exemples de titres.
     C'est ce comptage qui doit décider de la suite (correction manuelle vs ré-analyse payante).

  2. NORMALISATION (sauf --dry-run) : réécrit en CHEMIN CANONIQUE complet les annonces dont la
     valeur se résout sans ambiguïté (`exact_path` au format non canonique, ou `leaf`), dans le
     document ET dans l'index léger.

⚠️ Ce script ne CORRIGE aucune erreur de classement : il ne fait qu'uniformiser ce qui est déjà
juste. Une valeur ambiguë est laissée telle quelle (l'annonce apparaît dans « Autres » et reste
corrigeable à la main dans l'app), et une annonce que l'IA a réellement mal classée reste mal
classée — seule une ré-analyse ou une correction manuelle peut la réparer.

Une correction manuelle existante (`manualClassification`) est toujours respectée : le script ne
touche jamais l'index d'une annonce corrigée par l'utilisateur.

Idempotent : relancé, il ne réécrit que ce qui ne l'est pas déjà (sûr pour `run_once.py`, dont
l'action s'exécute une fois par branche déployée, donc généralement deux fois de suite).

Usage local (nécessite les credentials Firebase) :
    python3 backend/scripts/audit_classifications.py --dry-run
    python3 backend/scripts/audit_classifications.py
"""
import sys
import os
import argparse
import logging
from collections import Counter, defaultdict

sys.path.insert(0, os.getcwd())

from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET, DEFAULT_TAXONOMY
from backend.database import DatabaseService
from backend.repository import FirestoreRepository
from backend.taxonomy import build_index, canonicalize

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("audit_classifications")

PAGE_SIZE = 500
MAX_EXAMPLES = 5


def run(dry_run=False):
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db_client = db_service.db
    if not db_client:
        logger.error("Erreur de connexion à Firebase.")
        return

    index = build_index(DEFAULT_TAXONOMY)

    users_ref = db_client.collection('artifacts').document(APP_ID_TARGET).collection('users')
    users = list(users_ref.stream())
    logger.info(f"{'[DRY-RUN] ' if dry_run else ''}Audit des classifications sur {len(users)} utilisateurs.")

    totals = Counter()
    problem_values = Counter()
    # Exemples de titres par valeur problématique — indispensables pour juger sur pièces
    # (ex: "Guitare Electrique" sur un titre d'étui = classement correct mais nom nu ambigu).
    examples = defaultdict(list)
    normalized_total = 0

    for user_doc in users:
        user_id = user_doc.id
        repo = FirestoreRepository(db_client, APP_ID_TARGET, user_id)

        query = repo.collection_ref.select(
            ['aiAnalysis', 'manualClassification', 'title', 'status']
        ).order_by('__name__').limit(PAGE_SIZE)

        user_counts = Counter()
        user_normalized = 0
        last_doc = None

        while True:
            current = query.start_after(last_doc) if last_doc else query
            docs = list(current.stream())
            if not docs:
                break

            for doc in docs:
                data = doc.to_dict() or {}
                ai = data.get('aiAnalysis')
                # `aiAnalysis` peut être une liste sur les annonces corrompues par l'ancien
                # bug ArrayUnion (voir JOURNAL.md 2026-08-12) — même garde que repository.py.
                if isinstance(ai, list):
                    ai = ai[0] if ai else {}
                if not isinstance(ai, dict):
                    ai = {}

                raw = ai.get('classification')
                canonical, reason = canonicalize(raw, DEFAULT_TAXONOMY, index)

                # Une annonce déjà corrigée à la main est comptée à part : elle n'a plus besoin de
                # rien, l'inclure dans les "à réparer" gonflerait le chiffre qui décide de la suite.
                if data.get('manualClassification'):
                    user_counts['manual'] += 1
                    continue

                user_counts[reason] += 1
                if reason in ('ambiguous', 'unknown') and raw:
                    problem_values[str(raw)] += 1
                    if len(examples[str(raw)]) < MAX_EXAMPLES:
                        examples[str(raw)].append(data.get('title') or '(sans titre)')

                # Normalisation : uniquement ce qui se résout, et uniquement si ce n'est pas
                # déjà la valeur canonique. Une correction manuelle prime et n'est pas touchée.
                if canonical and canonical != raw and not data.get('manualClassification'):
                    if not dry_run:
                        ai_updated = dict(ai)
                        ai_updated['classification'] = canonical
                        repo.collection_ref.document(doc.id).update({'aiAnalysis': ai_updated})
                        repo._update_deal_index(doc.id, ai_analysis=ai_updated)
                    user_normalized += 1

            last_doc = docs[-1]

        total_user = sum(user_counts.values())
        logger.info(
            f"  {user_id[:12]}… : {total_user} annonces | "
            f"chemin complet: {user_counts['exact_path']} | feuille: {user_counts['leaf']} | "
            f"AMBIGU: {user_counts['ambiguous']} | INCONNU: {user_counts['unknown']} | "
            f"sans classification: {user_counts['empty']} | corrigées manuellement: {user_counts['manual']} | "
            f"{'à normaliser' if dry_run else 'normalisées'}: {user_normalized}"
        )
        totals.update(user_counts)
        normalized_total += user_normalized

    total = sum(totals.values())
    logger.info("=" * 78)
    logger.info(f"TOTAL : {total} annonces")
    for reason in ('exact_path', 'leaf', 'ambiguous', 'unknown', 'empty', 'manual'):
        count = totals[reason]
        share = (count / total * 100) if total else 0
        logger.info(f"  {reason:<12} : {count:>6}  ({share:.1f}%)")
    logger.info(f"  {'normalisées' if not dry_run else 'à normaliser':<12} : {normalized_total:>6}")

    if problem_values:
        logger.info("-" * 78)
        logger.info("Valeurs NON résolvables (à corriger à la main ou par ré-analyse), par fréquence :")
        for value, count in problem_values.most_common(25):
            logger.info(f"  {count:>5} × '{value}'")
            for title in examples[value]:
                logger.info(f"          ex: {title[:90]}")
    else:
        logger.info("Aucune valeur non résolvable — rien à réparer.")

    logger.info("=" * 78)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Audit et normalisation des classifications taxonomiques.")
    parser.add_argument('--dry-run', action='store_true', help="Compte et affiche sans rien écrire.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
