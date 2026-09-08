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

ACTIVE = False


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-09 : diagnostic de timing pour confirmer/infirmer l'hypothèse posée dans
    JOURNAL.md (2026-09-08, mesure du fix caching) — le cache observé sur Tier 2
    (17,1% des appels, run #427) ressemble à des retries JSON sur la MÊME annonce
    (`_call_gemini_json` rappelle avec le prompt précédent + un texte ajouté, préfixe
    quasi identique garanti) plutôt qu'un vrai partage du bloc statique (taxonomie/
    few-shot) entre annonces différentes — ce qui expliquerait aussi pourquoi Tier 1
    (JSON simple, peu de retries) est resté à 0%.

    Parcourt TOUS les appels [tokens] (pas seulement cached>0, contrairement au run
    précédent) et les avertissements "JSON invalide" de _call_gemini_json. Pour
    chaque modèle : écart entre appels consécutifs (indique si des annonces
    différentes sont assez rapprochées pour espérer un cache implicite), et pour
    chaque appel caché, présence ou non d'un avertissement JSON juste avant (retry
    confirmé vs partage inter-annonces possible). Lecture seule, aucune écriture Firestore.
    """
    import re
    import datetime
    from collections import defaultdict
    from config import FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
    from backend.database import DatabaseService

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    TOKENS_RE = re.compile(
        r"\[tokens\] model=(?P<model>\S+) images=(?P<images>\d+) "
        r"in=(?P<in_>\d+) out=(?P<out>\d+) cached=(?P<cached>\d+) total=(?P<total>\d+)"
    )
    JSON_INVALID_RE = re.compile(r"JSON invalide généré par (?P<model>\S+)")
    RETRY_WINDOW_S = 30  # fenêtre de recherche d'un avertissement JSON juste avant un appel caché

    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db = db_service.db
    if not db:
        logger.error("Erreur de connexion à Firebase.")
        return

    calls_by_model = defaultdict(list)     # model -> [(created_at, cached_tokens)]
    warnings_by_model = defaultdict(list)  # model -> [created_at]
    scanned = 0

    for doc in db.collection_group('logs').stream():
        scanned += 1
        data = doc.to_dict() or {}
        message = data.get('message', '')
        created_at = data.get('createdAt')
        if created_at is None:
            continue

        m = TOKENS_RE.search(message)
        if m:
            calls_by_model[m.group('model')].append((created_at, int(m.group('cached'))))
            continue

        w = JSON_INVALID_RE.search(message)
        if w:
            warnings_by_model[w.group('model')].append(created_at)

    logger.info(f"Scan terminé : {scanned} documents lus.")

    for model, events in sorted(calls_by_model.items()):
        events.sort(key=lambda t: t[0])
        gaps = [events[i][0] - events[i - 1][0] for i in range(1, len(events))]
        cached_events = [e for e in events if e[1] > 0]
        warns = sorted(warnings_by_model.get(model, []))

        retry_confirmed = sum(
            1 for created_at, _ in cached_events
            if any(0 <= (created_at - w) <= RETRY_WINDOW_S for w in warns)
        )
        retry_unconfirmed = len(cached_events) - retry_confirmed

        logger.info(
            f"--- model={model} : {len(events)} appels, {len(cached_events)} cachés, "
            f"{len(warns)} avertissements JSON invalide ---"
        )
        if gaps:
            gaps_sorted = sorted(gaps)
            under_60s = sum(1 for g in gaps if g < 60)
            logger.info(
                f"  Écart entre appels consécutifs (s) : min={gaps_sorted[0]:.1f} "
                f"médiane={gaps_sorted[len(gaps_sorted) // 2]:.1f} max={gaps_sorted[-1]:.1f} "
                f"({under_60s}/{len(gaps)} écarts < 60s)"
            )
        logger.info(
            f"  Cachés AVEC avertissement JSON <{RETRY_WINDOW_S}s avant (= retry confirmé sur la même annonce) : {retry_confirmed}"
        )
        logger.info(
            f"  Cachés SANS avertissement JSON à proximité (= partage inter-annonces possible) : {retry_unconfirmed}"
        )


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
