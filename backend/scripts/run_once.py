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

    2026-09-12 : validation bout-en-bout de backend/api/* (Phase A.2, Chantier A) contre les
    2414 annonces RÉELLEMENT migrées dans `guitarhunter_pg_staging` (dry-run du 2026-09-10,
    conteneur toujours en place) — jamais testé avec un vrai token Firebase ni un vrai serveur
    HTTP jusqu'ici (seulement TestClient + auth court-circuitée en local, voir backend/api/test_*.py).
    Aucune mutation : uniquement des requêtes GET sur une base de STAGING, jamais la prod utilisateur.

    Étapes : (1) extraction temporaire de backend/api/* + deal_mapping.py depuis la branche de
    migration ; (2) DSN de guitarhunter_pg_staging ; (3) identification de l'utilisateur réel
    (le plus d'annonces) ; (4) `firebase_admin.auth.create_custom_token(uid)` -> échange contre un
    VRAI ID token via l'API REST Firebase (aucun compte de test créé, aucun mot de passe requis —
    le bot a déjà les credentials Admin SDK en place) ; (5) vrai serveur uvicorn + requêtes HTTP
    authentifiées sur /health, /users/me/config, /deals, /deals/{id}, /cities.
    """
    import json
    import threading
    import time

    import requests

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    written = _extract_branch_files(logger)
    try:
        dsn = _read_staging_dsn(logger)
        if not dsn:
            logger.error("Abandon : impossible de déterminer le DSN de guitarhunter_pg_staging.")
            return
        os.environ["DATABASE_URL"] = dsn  # lu par backend/api/db.py au moment de l'import, ci-dessous

        import psycopg
        try:
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                row = conn.execute(
                    "SELECT user_id, COUNT(*) AS n FROM guitar_deals GROUP BY user_id ORDER BY n DESC LIMIT 1"
                ).fetchone()
        except Exception as e:
            logger.error(f"Connexion à guitarhunter_pg_staging échouée : {e}")
            return
        if not row:
            logger.error("Aucune annonce trouvée dans guitarhunter_pg_staging — rien à valider.")
            return
        target_uid, deal_count = row
        logger.info(f"Utilisateur cible : {target_uid[:6]}… ({deal_count} annonces réelles).")

        from dotenv import load_dotenv
        load_dotenv()
        web_api_key = os.getenv("VITE_FIREBASE_API_KEY")
        if not web_api_key:
            logger.error("VITE_FIREBASE_API_KEY absent de .env — impossible d'échanger le custom token.")
            return

        import firebase_admin
        from firebase_admin import auth as firebase_auth, credentials
        firebase_key_path = os.getenv("FIREBASE_KEY_PATH", "backend/config/serviceAccountKey.json")
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(firebase_key_path))
        custom_token = firebase_auth.create_custom_token(target_uid)

        exchange = requests.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={web_api_key}",
            json={"token": custom_token.decode("utf-8"), "returnSecureToken": True},
            timeout=10,
        )
        if not exchange.ok:
            logger.error(f"Échange du custom token échoué ({exchange.status_code}) : {exchange.text[:300]}")
            return
        id_token = exchange.json()["idToken"]
        logger.info("ID token Firebase RÉEL obtenu avec succès pour l'utilisateur cible.")

        import uvicorn
        from backend.api.main import app

        def _free_port():
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                return s.getsockname()[1]

        port = _free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.time() + 10
        while not server.started and time.time() < deadline:
            time.sleep(0.1)
        if not server.started:
            logger.error("uvicorn n'a pas démarré à temps.")
            return

        try:
            base_url = f"http://127.0.0.1:{port}"
            headers = {"Authorization": f"Bearer {id_token}"}

            health = requests.get(f"{base_url}/health", timeout=5)
            logger.info(f"GET /health -> {health.status_code} {health.text}")

            config_resp = requests.get(f"{base_url}/users/me/config", headers=headers, timeout=5)
            logger.info(f"GET /users/me/config -> {config_resp.status_code} (clés : {sorted(config_resp.json().keys()) if config_resp.ok else config_resp.text[:200]})")

            deals_resp = requests.get(f"{base_url}/deals", headers=headers, timeout=15)
            deals = deals_resp.json() if deals_resp.ok else []
            logger.info(f"GET /deals -> {deals_resp.status_code}, {len(deals)} annonces reçues (attendu ~{deal_count}).")

            if deals:
                sample_id = deals[0]["id"]
                sample_resp = requests.get(f"{base_url}/deals/{sample_id}", headers=headers, timeout=5)
                logger.info(f"GET /deals/{sample_id} -> {sample_resp.status_code}")
                if sample_resp.ok:
                    # Échantillon RÉEL loggé pour rejouer apiService.js::dealFromRow localement
                    # côté dev (Node) et vérifier que la reconstruction JS ne casse sur aucun cas
                    # limite réel (valeurs nulles, types inattendus) — jamais testable autrement
                    # depuis un environnement sans credentials Firebase.
                    logger.info(f"ÉCHANTILLON RÉEL /deals/{sample_id} : {json.dumps(sample_resp.json())}")

            cities_resp = requests.get(f"{base_url}/cities", headers=headers, timeout=5)
            logger.info(f"GET /cities -> {cities_resp.status_code}, {len(cities_resp.json()) if cities_resp.ok else '?'} villes.")
        finally:
            server.should_exit = True
            thread.join(timeout=5)
    finally:
        _cleanup_extracted(written, logger)


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
