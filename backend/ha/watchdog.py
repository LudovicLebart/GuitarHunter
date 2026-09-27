"""Démon HA — surveille le nœud pair, prend le rôle de primaire (Postgres + services
applicatifs) en cas de panne confirmée, notifie l'utilisateur.

Symétrique : destiné à tourner sur CHAQUE machine (Lenovo et Dell), piloté entièrement par le
bail Firestore (lease.py) — pas de configuration "qui est primaire" codée en dur d'un côté ou de
l'autre. `HaConfig.node_id`/`peer_host` sont les seuls réglages qui diffèrent entre les deux
déploiements du même code.

Préparation uniquement (chantier "redondance Dell") : pas encore branché à une unité systemd
réelle ni déployé sur le Dell/Lenovo — voir docs/management/plans/DB_REDUNDANCY_DELL_PLAN.md
pour l'état d'avancement et les étapes restantes (provisioning Postgres/Dell, unités systemd,
CI, indirection frontend). Ne PAS lancer en production tel quel : `local_service_name` doit
correspondre à une unité systemd réelle et `PEER_SSH_KEY_PATH`/la règle sudoers associée doivent
exister sur les deux machines.
"""
import logging
import subprocess
import time
from dataclasses import dataclass

import psycopg
from firebase_admin import firestore

from backend.ha import lease
from backend.ha.health import is_peer_reachable, is_peer_service_active, stop_peer_service
from backend.notifications import NtfyNotifier

logger = logging.getLogger("ha.watchdog")


@dataclass
class HaConfig:
    node_id: str                 # "lenovo" ou "dell" — identifie CETTE machine.
    peer_host: str                # IP/hostname tailnet de la machine PAIRE.
    peer_ssh_user: str
    peer_ssh_key_path: str
    peer_health_url: str          # ex: https://serveur.tail16b52e.ts.net/prod/health
    local_service_name: str       # unité systemd du bot/API sur CETTE machine (standby par défaut).
    peer_service_name: str        # unité systemd équivalente sur la machine paire.
    local_pg_dsn: str             # DSN de la réplique Postgres locale (à promouvoir en cas de bascule).
    lease_ttl_seconds: int = 60
    heartbeat_interval_seconds: int = 15
    # Nombre de tours consécutifs de bail expiré avant de tenter une bascule — évite de basculer
    # sur un simple pic de latence Firestore ou un redémarrage bref du renouvellement.
    failover_confirm_rounds: int = 3


def promote_local_postgres_replica(pg_dsn: str) -> None:
    """`pg_promote()` (Postgres 12+) est un no-op si la base locale n'est déjà plus en standby —
    sûr à appeler même si ce nœud est déjà primaire (idempotent)."""
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        conn.execute("SELECT pg_promote();")


def start_local_service(service_name: str, timeout: float = 30.0) -> None:
    """Nécessite la même règle sudoers NOPASSWD que health.stop_peer_service, mais pour
    `systemctl start <service_name>` en LOCAL cette fois."""
    subprocess.run(["sudo", "systemctl", "start", service_name], check=True, timeout=timeout)


def _attempt_failover(db, cfg: HaConfig) -> bool:
    """Tente la bascule vers CE nœud. Retourne True si elle a eu lieu."""
    if is_peer_reachable(cfg.peer_health_url) and is_peer_service_active(
        cfg.peer_host, cfg.peer_ssh_user, cfg.peer_ssh_key_path, cfg.peer_service_name, logger=logger
    ):
        logger.warning(
            f"[HA] Bail expiré mais {cfg.peer_host} répond ET son service ({cfg.peer_service_name}) "
            "est actif — probable bug de renouvellement du bail, PAS de bascule automatique."
        )
        NtfyNotifier.send(
            "⚠️ Bail HA expiré sans panne détectée",
            f"Le bail Firestore a expiré mais {cfg.peer_host} répond et son service tourne. "
            f"Bascule automatique refusée par {cfg.node_id} — vérifier le watchdog du nœud actif.",
            priority="high", logger=logger,
        )
        return False

    logger.warning(f"[HA] Panne confirmée de {cfg.peer_host} — tentative de bascule vers {cfg.node_id}.")
    stop_peer_service(cfg.peer_host, cfg.peer_ssh_user, cfg.peer_ssh_key_path,
                       cfg.peer_service_name, logger=logger)

    if not lease.acquire_or_renew(db, cfg.node_id, cfg.lease_ttl_seconds):
        logger.info("[HA] Bascule abandonnée — un autre nœud a pris le bail entre-temps.")
        return False

    promote_local_postgres_replica(cfg.local_pg_dsn)
    start_local_service(cfg.local_service_name)

    logger.warning(f"[HA] Bascule effectuée — {cfg.node_id} est désormais primaire.")
    NtfyNotifier.send(
        "🔴 Bascule HA effectuée",
        f"{cfg.node_id} a pris le relais suite à une panne de {cfg.peer_host}. "
        "Retour à la normale : procédure MANUELLE (voir le runbook) — pas de re-bascule automatique.",
        priority="urgent", logger=logger,
    )
    return True


def run_forever(cfg: HaConfig, db=None) -> None:
    """Boucle principale — à lancer comme process/service dédié sur chaque machine (jamais dans
    le thread du bot lui-même : ce démon doit continuer à tourner même si le bot/API local est
    arrêté, sans quoi il ne pourrait jamais détecter une panne de CE nœud pour aider l'autre)."""
    db = db or firestore.client()
    consecutive_expired_rounds = 0

    while True:
        try:
            leader = lease.read_leader(db)
            now = time.time()
            i_am_leader = (
                leader is not None
                and leader.get("host") == cfg.node_id
                and leader.get("expires_at", 0) > now
            )

            if i_am_leader:
                lease.acquire_or_renew(db, cfg.node_id, cfg.lease_ttl_seconds)
                consecutive_expired_rounds = 0
            else:
                lease_expired = leader is None or leader.get("expires_at", 0) <= now
                consecutive_expired_rounds = consecutive_expired_rounds + 1 if lease_expired else 0

                if consecutive_expired_rounds >= cfg.failover_confirm_rounds:
                    if _attempt_failover(db, cfg):
                        consecutive_expired_rounds = 0
        except Exception:
            logger.exception("[HA] Erreur non gérée dans la boucle watchdog — tour ignoré, réessai au prochain cycle.")

        time.sleep(cfg.heartbeat_interval_seconds)
