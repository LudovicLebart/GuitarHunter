"""Entrypoint du démon HA (`backend/ha/watchdog.py::run_forever`) — destiné à tourner comme
service systemd dédié, symétriquement sur le Lenovo ET le Dell (voir
docs/management/plans/DB_REDUNDANCY_DELL_PLAN.md §7.3/7.5.1).

Ne construit `HaConfig` que depuis les variables d'environnement HA_* (config.py) — échoue tôt
et explicitement si l'une des variables obligatoires manque, plutôt que de démarrer un watchdog
mal configuré qui ne ferait jamais rien (ou pire, échouerait silencieusement à chaque tour).
"""
import logging
import os
import sys

import firebase_admin
from firebase_admin import credentials

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from config import (
    FIREBASE_KEY_PATH,
    HA_NODE_ID, HA_PEER_HOST, HA_PEER_SSH_USER, HA_PEER_SSH_KEY_PATH, HA_PEER_HEALTH_URL,
    HA_LOCAL_SERVICE_NAME, HA_PEER_SERVICE_NAME, HA_LOCAL_PG_DSN,
    HA_LEASE_TTL_SECONDS, HA_HEARTBEAT_INTERVAL_SECONDS, HA_FAILOVER_CONFIRM_ROUNDS,
)
from backend.ha.watchdog import HaConfig, run_forever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ha.watchdog.entrypoint")

_REQUIRED = {
    "HA_NODE_ID": HA_NODE_ID,
    "HA_PEER_HOST": HA_PEER_HOST,
    "HA_PEER_SSH_USER": HA_PEER_SSH_USER,
    "HA_PEER_SSH_KEY_PATH": HA_PEER_SSH_KEY_PATH,
    "HA_PEER_HEALTH_URL": HA_PEER_HEALTH_URL,
    "HA_LOCAL_SERVICE_NAME": HA_LOCAL_SERVICE_NAME,
    "HA_PEER_SERVICE_NAME": HA_PEER_SERVICE_NAME,
    "HA_LOCAL_PG_DSN": HA_LOCAL_PG_DSN,
}


def main() -> None:
    missing = [name for name, value in _REQUIRED.items() if not value]
    if missing:
        logger.error(f"[HA] Variables d'environnement manquantes, watchdog non démarré : {', '.join(missing)}")
        sys.exit(1)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(FIREBASE_KEY_PATH))

    cfg = HaConfig(
        node_id=HA_NODE_ID,
        peer_host=HA_PEER_HOST,
        peer_ssh_user=HA_PEER_SSH_USER,
        peer_ssh_key_path=HA_PEER_SSH_KEY_PATH,
        peer_health_url=HA_PEER_HEALTH_URL,
        local_service_name=HA_LOCAL_SERVICE_NAME,
        peer_service_name=HA_PEER_SERVICE_NAME,
        local_pg_dsn=HA_LOCAL_PG_DSN,
        lease_ttl_seconds=HA_LEASE_TTL_SECONDS,
        heartbeat_interval_seconds=HA_HEARTBEAT_INTERVAL_SECONDS,
        failover_confirm_rounds=HA_FAILOVER_CONFIRM_ROUNDS,
    )
    logger.info(f"[HA] Watchdog démarré — node_id={cfg.node_id}, peer_host={cfg.peer_host}")
    run_forever(cfg)


if __name__ == "__main__":
    main()
