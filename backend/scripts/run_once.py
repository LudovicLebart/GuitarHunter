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

sys.path.insert(0, os.getcwd())

ACTIVE = False


# Fichiers du Chantier A (Phase A.2, branche claude/firestore-postgres-migration) — jamais
# mergés sur dev/master, donc absents du checkout courant : extraits TEMPORAIREMENT via
# `git show FETCH_HEAD:<path>` (jamais un checkout/merge, voir _extract_branch_files), exécutés,
# puis supprimés dans le `finally` de run() — dev reste inchangé après coup (le prochain déploiement
# repart de toute façon d'un `git reset --hard origin/<branche>` qui écraserait tout résidu).
_MIGRATION_BRANCH = "claude/firestore-postgres-migration"
_EXTRACT_PATHS = ["backend/api", "backend/deal_mapping.py"]


def _extract_branch_files(logger):
    import subprocess
    subprocess.run(["git", "fetch", "origin", _MIGRATION_BRANCH], check=True)
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "FETCH_HEAD", "--", *_EXTRACT_PATHS],
        check=True, capture_output=True, text=True,
    ).stdout
    written = []
    for path in (p for p in listing.splitlines() if p.strip()):
        content = subprocess.run(
            ["git", "show", f"FETCH_HEAD:{path}"], check=True, capture_output=True, text=True
        ).stdout
        existed = os.path.exists(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append((path, existed))
    logger.info(f"{len(written)} fichiers extraits temporairement de '{_MIGRATION_BRANCH}'.")
    return written


def _cleanup_extracted(written, logger):
    for path, existed in written:
        if not existed:
            try:
                os.remove(path)
            except OSError:
                pass
    logger.info("Fichiers extraits temporairement nettoyés.")


def _read_staging_dsn(logger):
    """Le mot de passe du conteneur `guitarhunter_pg_staging` (provisionné le 2026-09-10, voir
    JOURNAL.md) a été écrit dans ce fichier par le script de provisioning — déjà supprimé par son
    propre protocole one-shot, donc son format exact de clés n'est plus visible depuis cette
    session de dev. Plusieurs conventions plausibles essayées ici plutôt que d'en supposer une
    seule ; les noms de CLÉS (jamais les valeurs) sont logués pour diagnostiquer sans rien
    divulguer si aucune ne correspond."""
    path = os.path.expanduser("~/.guitarhunter_staging_db.env")
    if not os.path.exists(path):
        logger.error(f"Fichier introuvable : {path}")
        return None
    values = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    if "DATABASE_URL" in values:
        logger.info("DSN staging : trouvé directement sous la clé DATABASE_URL.")
        return values["DATABASE_URL"]
    host = values.get("PGHOST", "127.0.0.1")
    port = values.get("PGPORT", "5433")
    user = values.get("PGUSER") or values.get("POSTGRES_USER") or "postgres"
    dbname = values.get("PGDATABASE") or values.get("POSTGRES_DB") or "guitarhunter"
    password = values.get("PGPASSWORD") or values.get("POSTGRES_PASSWORD")
    if not password:
        logger.error(f"Aucune clé de mot de passe reconnue. Clés présentes : {sorted(values.keys())}")
        return None
    logger.info(f"DSN staging reconstruit depuis des clés éclatées (user={user}, host={host}, port={port}, db={dbname}).")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def run():
    """Action ponctuelle à exécuter en production. Repasser ACTIVE à False après usage.

    2026-09-18 : Chantier G — diagnostic lecture seule de l'efficacité du filtre
    "Recherche Active" (voir backend/scripts/check_active_search_filter_logs.py) — CONFIRMÉ,
    résultat lu dans les logs GitHub Actions (runs #507/#508, dev + master). Fichier de log
    serveur du jour vide (0 activité depuis minuit UTC) ; côté Firestore, 36 NOT_PROMOTED
    historiques cohérents avec le filtre (Dreadnought/Stratocaster/Classique écartés), mais
    l'échantillon "60 dernières annonces" mélange des analyses d'AVANT la configuration du
    filtre (35/55 "promues" sans classification ou hors-filtre, ex: Dreadnought, amplis,
    étuis) — pas concluant tel quel, à rejouer après une vraie fenêtre d'activité récente si
    le sujet redevient prioritaire. Désarmé ci-dessous — rien à rejouer.
    """
    pass


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
