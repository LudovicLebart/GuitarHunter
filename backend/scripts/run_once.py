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

    2026-09-14 : diagnostic de la progression de l'export complet Firestore→Postgres
    (Phase A.4) lancé au run #491 (PID=1793707).

    Résultat (run #494, voir JOURNAL.md) : SUCCÈS. Process terminé (plus dans `ps`).
    Comptages Postgres finaux : 6533 guitar_deals (6167 + 347 + 17 + 2 sur 4 utilisateurs
    actifs), 244 deal_chat, 4 restoration_plan_items, 50 cities, 25 shared_deals. Le
    fichier de log lui-même était partiellement corrompu (bannières de démarrage
    dupliquées) — probablement une relance concurrente du même script par un autre
    déploiement déclenché pendant que `run_once.py` était armé (une autre session
    travaillait sur `dev` en parallèle). Idempotent donc sans perte, mais leçon retenue :
    un futur script d'action doit se protéger contre un double lancement concurrent
    (verrou fichier ou vérification `ps` avant de lancer) si `dev` reste actif pendant
    l'armement. Désarmé ci-dessous.
    """
    import subprocess

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logger = logging.getLogger("run_once")

    def _run(cmd, timeout=15):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            combined = "\n".join(p for p in (out, err) if p)
            return f"[exit={r.returncode}] {combined}" if combined else f"[exit={r.returncode}] (vide)"
        except Exception as e:
            return f"(échec: {e})"

    pid = "1793707"
    logger.info(f"Process encore actif ? ps -p {pid} : {_run(['ps', '-p', pid, '-o', 'pid,etime,cmd'])}")

    log_path = os.path.expanduser("~/export_full_a4.log")
    logger.info(f"--- Dernières lignes de {log_path} ---")
    logger.info(_run(['tail', '-n', '60', log_path]))

    env_path = os.path.expanduser("~/.guitarhunter_staging_db.env")
    dsn = None
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    dsn = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except FileNotFoundError:
        logger.error(f"Fichier introuvable : {env_path}")
        return

    if not dsn:
        logger.error(f"DATABASE_URL introuvable dans {env_path} — abandon des comptages Postgres.")
        return

    import asyncio
    import asyncpg

    async def _counts():
        conn = await asyncpg.connect(dsn, timeout=10)
        try:
            per_user = await conn.fetch(
                "SELECT user_id, COUNT(*) AS n FROM guitar_deals GROUP BY user_id ORDER BY n DESC"
            )
            total_deals = await conn.fetchval("SELECT COUNT(*) FROM guitar_deals")
            total_chat = await conn.fetchval("SELECT COUNT(*) FROM deal_chat")
            total_resto = await conn.fetchval("SELECT COUNT(*) FROM restoration_plan_items")
            total_cities = await conn.fetchval("SELECT COUNT(*) FROM cities")
            total_shared = await conn.fetchval("SELECT COUNT(*) FROM shared_deals")
            logger.info("--- Comptages Postgres (guitarhunter_pg_staging) ---")
            logger.info(f"Total guitar_deals : {total_deals}")
            for row in per_user:
                logger.info(f"  user_id={row['user_id'][:12]}... : {row['n']} annonces")
            logger.info(f"Total deal_chat : {total_chat}")
            logger.info(f"Total restoration_plan_items : {total_resto}")
            logger.info(f"Total cities : {total_cities}")
            logger.info(f"Total shared_deals : {total_shared}")
        finally:
            await conn.close()

    try:
        asyncio.run(_counts())
    except Exception as e:
        logger.error(f"Échec de la connexion/requête Postgres : {e}")


if __name__ == "__main__":
    if not ACTIVE:
        print("[run_once] Rien à exécuter (ACTIVE=False, comportement par défaut).")
        sys.exit(0)
    print("[run_once] Exécution de l'action ponctuelle...")
    run()
    print("[run_once] Terminé.")
