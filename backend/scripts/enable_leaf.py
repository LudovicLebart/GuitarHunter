"""Active Leaf Hunter pour les utilisateurs du bot (`leafConfig.enabled = true`) — IDEMPOTENT.

Ne touche QUE `users.config.leafConfig` : `enabled` passe à true, `scanConfig.home` reçoit Saint-Bruno-de-Montarville
(décision utilisateur 2026-11-22) s'il n'a pas déjà un point de repère ; le reste de `leafConfig` (réglages posés
ensuite par l'utilisateur) est conservé. Utilisateurs visés : `USER_IDS_TARGET` (.env du bot).

    python -m backend.scripts.enable_leaf --dry-run   # rapport seul
    python -m backend.scripts.enable_leaf
En production : via `backend/scripts/run_once.py` (voir son protocole : désarmer ensuite)."""
import argparse
import os
import sys

sys.path.insert(0, os.getcwd())

import psycopg  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

import config  # noqa: E402,F401  (charge .env : DATABASE_URL, USER_IDS_TARGET)
from backend.leaf.config import DEFAULT_HOME  # noqa: E402


def run(dry_run: bool = False) -> int:
    uids = list(config.USER_IDS_TARGET)
    if not uids:
        print("[enable_leaf] USER_IDS_TARGET vide : aucun utilisateur visé.")
        return 0
    done = 0
    with psycopg.connect(os.getenv("DATABASE_URL", "").replace("\r", "").strip(), connect_timeout=10, autocommit=True) as conn:
        for uid in uids:
            row = conn.execute("SELECT config FROM users WHERE uid = %s", (uid,)).fetchone()
            if not row:
                print(f"[enable_leaf] {uid[:8]} : utilisateur introuvable, ignoré.")
                continue
            cfg = row[0] or {}
            leaf = dict(cfg.get("leafConfig") or {})
            scan = dict(leaf.get("scanConfig") or {})
            home = scan.get("home") or {}
            if home.get("latitude") is None or home.get("longitude") is None:
                scan["home"] = {"latitude": DEFAULT_HOME["latitude"], "longitude": DEFAULT_HOME["longitude"],
                                "name": DEFAULT_HOME["name"]}
            leaf.update({"enabled": True, "scanConfig": scan})
            print(f"[enable_leaf] {uid[:8]} : leafConfig.enabled = true, ville de référence "
                  f"{(scan['home'].get('name') or 'personnalisée')}{' (simulation)' if dry_run else ''}.")
            if not dry_run:
                conn.execute("UPDATE users SET config = jsonb_set(COALESCE(config, '{}'::jsonb), '{leafConfig}', %s, true) "
                             "WHERE uid = %s", (Jsonb(leaf), uid))
            done += 1
    return done


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    run(ap.parse_args().dry_run)
