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

    2026-09-10 (suite) : le premier essai du dry-run (run #439) a été tué par mon propre timeout
    de 300s sur le sous-processus d'export — pas un crash, juste plus long que prévu (le script
    boucle en série sur chaque annonce + ses sous-collections chat/restorationPlan, un aller-retour
    Firestore à la fois). Chaque annonce est migrée dans sa propre transaction Postgres (voir
    `_migrate_deal`), donc rien n'est corrompu — juste incomplet. Avant de relancer avec un timeout
    plus long, ce passage mesure : (a) le nombre réel d'annonces de `config.USER_ID_TARGET` côté
    Firestore, (b) ce qui est déjà arrivé côté Postgres de staging — pour calibrer le prochain essai
    plutôt que de deviner. Purement en LECTURE des deux côtés.
    """
    import subprocess
    import sys
    from pathlib import Path

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    CREDS_PATH = Path.home() / ".guitarhunter_staging_db.env"

    logger.info("=== Mesure : taille réelle des données + progression du dry-run précédent ===")

    from config import FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET, USER_ID_TARGET, APP_ID_TARGET
    from backend.database import DatabaseService

    if not USER_ID_TARGET:
        logger.error("config.USER_ID_TARGET est vide.")
        return

    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    if db_service.offline_mode or not db_service.db:
        logger.error("Firebase en mode hors-ligne.")
        return
    user_ref = (
        db_service.db.collection("artifacts").document(APP_ID_TARGET)
        .collection("users").document(USER_ID_TARGET)
    )
    deal_docs = list(user_ref.collection("guitar_deals").stream())
    logger.info(f"Firestore : {len(deal_docs)} annonce(s) pour l'utilisateur {USER_ID_TARGET[:8]}.")
    # Échantillon (10 premières) pour estimer le nombre moyen de messages de chat par annonce —
    # le vrai coût en allers-retours Firestore, pas juste le nombre d'annonces.
    sample = deal_docs[:10]
    total_chat = sum(len(list(d.reference.collection("chat").stream())) for d in sample)
    total_resto = sum(len(list(d.reference.collection("restorationPlan").stream())) for d in sample)
    if sample:
        logger.info(
            f"Échantillon ({len(sample)} annonces) : {total_chat} message(s) de chat, "
            f"{total_resto} étape(s) de restauration au total."
        )

    if not CREDS_PATH.exists():
        logger.warning(f"{CREDS_PATH} introuvable — impossible de vérifier la progression côté Postgres.")
        return
    database_url = None
    for line in CREDS_PATH.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            database_url = line[len("DATABASE_URL="):].strip()
    if not database_url:
        logger.warning("DATABASE_URL absent du fichier de credentials.")
        return

    pip = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "asyncpg"], capture_output=True, text=True, timeout=60)
    if pip.returncode != 0:
        logger.error(f"Échec de l'installation d'asyncpg : {pip.stderr.strip()}")
        return

    import asyncio
    import asyncpg

    async def _count():
        conn = await asyncpg.connect(database_url, timeout=5)
        try:
            deals = await conn.fetchval("SELECT count(*) FROM guitar_deals WHERE user_id = $1", USER_ID_TARGET)
            chat = await conn.fetchval(
                "SELECT count(*) FROM deal_chat WHERE deal_id IN (SELECT id FROM guitar_deals WHERE user_id = $1)",
                USER_ID_TARGET,
            )
            resto = await conn.fetchval(
                "SELECT count(*) FROM restoration_plan_items WHERE deal_id IN (SELECT id FROM guitar_deals WHERE user_id = $1)",
                USER_ID_TARGET,
            )
            return deals, chat, resto
        finally:
            await conn.close()

    try:
        deals, chat, resto = asyncio.run(_count())
        logger.info(f"Postgres (staging) déjà présent : {deals} annonce(s), {chat} message(s) de chat, {resto} étape(s) de restauration.")
    except Exception as e:
        logger.error(f"Connexion au Postgres de staging impossible : {e}")

    logger.info("=== Fin de la mesure ===")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
