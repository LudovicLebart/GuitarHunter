"""
Script "one-shot" exécuté automatiquement à CHAQUE déploiement
(.github/workflows/deploy.yml, job `deploy`, étape "Script de maintenance ponctuel") —
ce job est le seul contexte où le serveur a déjà les credentials Firebase en place
(.env / backend/config/serviceAccountKey.json écrits juste avant dans le même job).

Sert à exécuter une action ponctuelle en production (ex: script de migration) depuis un
environnement de dev qui n'y a lui-même aucun accès à Firestore.

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
import logging

# Comme rebuild_index.py : nécessaire pour que `from backend.scripts... import ...` résolve,
# `python3 backend/scripts/run_once.py` n'ajoutant que le dossier du script (pas la racine du
# repo) à sys.path. Le job `deploy` exécute toujours ce script depuis la racine (~/GuitareHunter).
sys.path.insert(0, os.getcwd())

ACTIVE = True


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-08 : mesure de l'effet réel du correctif de caching implicite Gemini
    (`ce2e7fb`, déployé le 2026-09-07 ~03:49 UTC — voir JOURNAL.md). Parcourt
    `artifacts/{APP_ID}/users/*/logs` (collection_group, TTL Firestore 3 jours sur ces
    documents — d'où l'urgence) à la recherche des lignes `[tokens] model=... cached=...`
    émises par `analyzer.py::_call_gemini_json`, et logue un résumé avant/après le
    déploiement (appels, ratio cached>0, tokens cachés par modèle) dans les logs du job
    GitHub Actions. Lecture seule, aucune écriture Firestore.
    """
    import re
    import datetime
    from collections import defaultdict
    from config import FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
    from backend.database import DatabaseService

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    DEPLOY_TS = datetime.datetime(2026, 9, 7, 3, 49, 2, tzinfo=datetime.timezone.utc).timestamp()
    TOKENS_RE = re.compile(
        r"\[tokens\] model=(?P<model>\S+) images=(?P<images>\d+) "
        r"in=(?P<in_>\d+) out=(?P<out>\d+) cached=(?P<cached>\d+) total=(?P<total>\d+)"
    )

    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db = db_service.db
    if not db:
        logger.error("Erreur de connexion à Firebase.")
        return

    # Regroupe les compteurs par période (avant/après déploiement) puis par modèle.
    stats = {
        'before': defaultdict(lambda: {'calls': 0, 'cached_calls': 0, 'in_tokens': 0, 'cached_tokens': 0}),
        'after': defaultdict(lambda: {'calls': 0, 'cached_calls': 0, 'in_tokens': 0, 'cached_tokens': 0}),
    }
    recent_cached_examples = []
    scanned = 0
    matched = 0

    for doc in db.collection_group('logs').stream():
        scanned += 1
        data = doc.to_dict() or {}
        message = data.get('message', '')
        m = TOKENS_RE.search(message)
        if not m:
            continue
        matched += 1

        created_at = data.get('createdAt')
        period = 'after' if (created_at is not None and created_at >= DEPLOY_TS) else 'before'
        model = m.group('model')
        in_tokens = int(m.group('in_'))
        cached_tokens = int(m.group('cached'))

        bucket = stats[period][model]
        bucket['calls'] += 1
        bucket['in_tokens'] += in_tokens
        bucket['cached_tokens'] += cached_tokens
        if cached_tokens > 0:
            bucket['cached_calls'] += 1
            if period == 'after':
                recent_cached_examples.append((created_at, message))

    logger.info(f"Scan terminé : {scanned} documents lus, {matched} lignes [tokens] trouvées.")

    for period_label, period_key in (("AVANT le déploiement (< 2026-09-07 03:49 UTC)", 'before'),
                                      ("APRÈS le déploiement (>= 2026-09-07 03:49 UTC)", 'after')):
        logger.info(f"--- {period_label} ---")
        period_stats = stats[period_key]
        if not period_stats:
            logger.info("  (aucun appel [tokens] trouvé sur cette période)")
            continue
        for model, s in sorted(period_stats.items()):
            ratio = (s['cached_calls'] / s['calls'] * 100) if s['calls'] else 0.0
            token_ratio = (s['cached_tokens'] / s['in_tokens'] * 100) if s['in_tokens'] else 0.0
            logger.info(
                f"  model={model} calls={s['calls']} cached_calls={s['cached_calls']} "
                f"({ratio:.1f}%) in_tokens={s['in_tokens']} cached_tokens={s['cached_tokens']} "
                f"({token_ratio:.1f}% des tokens d'entrée)"
            )

    recent_cached_examples.sort(key=lambda t: t[0] or 0, reverse=True)
    logger.info(f"Exemples récents (après déploiement) avec cached>0, max 10 sur {len(recent_cached_examples)} :")
    for created_at, message in recent_cached_examples[:10]:
        ts = datetime.datetime.fromtimestamp(created_at, tz=datetime.timezone.utc).isoformat() if created_at else '?'
        logger.info(f"  [{ts}] {message}")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
