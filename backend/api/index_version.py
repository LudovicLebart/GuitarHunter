"""Version de l'index des annonces, pour `ETag` / `304` sur `GET /deals/index` (2026-11-04, PERF_API_INDEX_PLAN M2).

Un seul processus uvicorn : une connexion LISTEN dédiée, ouverte au démarrage, incrémente un compteur à chaque
notification `deal_changes` (annonces, correspondances, état utilisateur) ou `restoration_plan_changes` (frais de
restauration, qui entrent dans l'index). Le compteur sert d'ETag : une relecture sans changement coûte un 304 sans
SQL ni sérialisation.

Garde-fous (un 304 à tort ferait afficher un index périmé) :
- tant que la connexion LISTEN n'est pas établie (démarrage, coupure Postgres), AUCUN ETag n'est émis ; le compteur
  est aussi incrémenté à chaque (re)connexion, car des notifications ont pu être perdues entre-temps ;
- les suppressions sont notifiées (triggers DELETE de `schema.sql`) ; `TTL_SECONDS` n'est qu'un filet de sécurité
  (écriture qui échapperait aux triggers) : l'ETag change aussi à chaque tranche d'une heure ;
- le compteur démarre à l'heure courante (ns) : après un redémarrage de l'API un ancien ETag ne peut pas redevenir valide ;
- la coupure de la connexion LISTEN retire l'ETag immédiatement (écouteur de terminaison), sans attendre le sondage ;
- l'ETag est propre à l'utilisateur (empreinte de l'uid) : un autre compte sur le même navigateur ne peut pas
  valider le cache du premier.
"""
import asyncio
import hashlib
import logging
import time

import asyncpg

logger = logging.getLogger(__name__)

CHANNELS = ("deal_changes", "restoration_plan_changes")
TTL_SECONDS = 3600

_version = time.time_ns()
_healthy = False


def bump() -> None:
    global _version
    _version += 1


def is_healthy() -> bool:
    return _healthy


def etag_for(uid: str, variant: str, now: float | None = None) -> str | None:
    """ETag faible de l'index de `uid` pour une variante de format, ou None si on ne peut pas garantir sa fraîcheur."""
    if not _healthy:
        return None
    bucket = int((time.time() if now is None else now) // TTL_SECONDS)
    who = hashlib.sha256(uid.encode("utf-8")).hexdigest()[:10]
    return f'W/"{who}-{variant}-{_version}-{bucket}"'


def matches(if_none_match: str | None, etag: str | None) -> bool:
    """`If-None-Match` peut lister plusieurs ETags ; comparaison faible (préfixe `W/` ignoré)."""
    if not if_none_match or not etag:
        return False
    wanted = etag.removeprefix("W/")
    return any(part.strip().removeprefix("W/") == wanted for part in if_none_match.split(","))


def _on_connection_lost(_connection) -> None:
    global _healthy
    _healthy = False
    bump()


async def run_listener(dsn: str) -> None:
    """Boucle de fond : se (re)connecte tant que l'API tourne. À lancer avec `asyncio.create_task`, annuler à l'arrêt."""
    global _healthy
    delay = 1.0
    while True:
        conn = None
        try:
            conn = await asyncpg.connect(dsn)
            conn.add_termination_listener(_on_connection_lost)
            for channel in CHANNELS:
                await conn.add_listener(channel, lambda *_: bump())
            bump()  # des notifications ont pu être manquées pendant l'absence
            _healthy = True
            delay = 1.0
            while not conn.is_closed():
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("index_version: connexion LISTEN perdue, nouvelle tentative dans %.0f s", delay, exc_info=True)
        finally:
            _healthy = False
            bump()
            if conn is not None and not conn.is_closed():
                try:
                    await conn.close()
                except Exception:  # noqa: BLE001 - fermeture best-effort
                    pass
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30.0)
