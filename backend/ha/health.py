"""Vérifications mutuelles entre les deux nœuds HA (Lenovo/Dell) — garde-fou SECONDAIRE avant
qu'un nœud standby ne se promeuve suite à un bail Firestore expiré (voir lease.py pour le juge
principal, qui reste la seule source de vérité pour "qui est primaire").

Un bail expiré peut signaler soit une vraie panne, soit un bug de renouvellement côté nœud actif
encore bien vivant — ces checks tranchent lequel : si le pair répond ET rapporte son service
actif, pas de bascule automatique malgré le bail expiré (voir watchdog.py).
"""
import logging
import subprocess

import requests

_module_logger = logging.getLogger(__name__)

_SSH_BASE_OPTS = ["-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes"]


def is_peer_reachable(peer_health_url: str, timeout: float = 5.0) -> bool:
    """La machine paire répond-elle (allumée + réseau tailnet OK) ? Sonde un endpoint HTTP
    léger (ex: /health de guitarhunter-api), pas un simple ping ICMP — un ping qui passe ne
    garantit pas que le service applicatif tourne."""
    try:
        resp = requests.get(peer_health_url, timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def is_peer_service_active(ssh_host: str, ssh_user: str, ssh_key_path: str, service_name: str,
                            timeout: float = 10.0, logger: logging.Logger = None) -> bool:
    """Le service systemd est-il rapporté actif sur la machine paire, via SSH ? Distinct de
    is_peer_reachable() : une machine peut répondre sur le tailnet avec son service pourtant
    arrêté (crash applicatif, maintenance manuelle)."""
    log = logger or _module_logger
    try:
        result = subprocess.run(
            ["ssh", "-i", ssh_key_path, *_SSH_BASE_OPTS, f"{ssh_user}@{ssh_host}",
             f"systemctl is-active {service_name}"],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip() == "active"
    except (subprocess.TimeoutExpired, OSError) as e:
        log.warning(f"[HA] Vérification SSH du service distant ({service_name}@{ssh_host}) impossible : {e}")
        return False


def stop_peer_service(ssh_host: str, ssh_user: str, ssh_key_path: str, service_name: str,
                       timeout: float = 15.0, logger: logging.Logger = None) -> bool:
    """Fencing : tente d'arrêter activement le service sur la machine paire avant de se
    promouvoir soi-même, pour réduire (sans l'éliminer complètement — pas de vraie garantie de
    fencing possible sur 2 machines résidentielles sans matériel dédié) le risque que les deux
    nœuds tournent en même temps si le pair redevient joignable juste après la bascule.

    Nécessite une règle sudoers NOPASSWD dédiée sur la machine paire pour
    `systemctl stop <service_name>` (même pattern que la règle déjà en place pour
    guitarhunter-api-prod, voir docs/reference/ARCHITECTURE.md § Déploiement Tailscale).

    Retourne True si l'arrêt a réussi OU si la machine est injoignable (rien à arrêter de ce
    côté — cas le plus probable d'une vraie panne)."""
    log = logger or _module_logger
    try:
        result = subprocess.run(
            ["ssh", "-i", ssh_key_path, *_SSH_BASE_OPTS, f"{ssh_user}@{ssh_host}",
             f"sudo systemctl stop {service_name}"],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            log.warning(f"[HA] Échec de l'arrêt distant de {service_name}@{ssh_host} : {result.stderr.strip()}")
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError) as e:
        log.info(f"[HA] Machine paire injoignable pour le fencing de {service_name} ({e}) — probablement déjà en panne.")
        return True
