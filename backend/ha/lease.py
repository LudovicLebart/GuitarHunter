"""Bail de leadership (le "juge") pour la bascule HA Lenovo/Dell — un document Firestore unique,
externe aux deux machines, tranche qui est primaire.

Un health-check mutuel entre seulement 2 machines est structurellement ambigu : en cas de
coupure réseau *entre elles*, chacune peut croire l'autre morte (split-brain). Firestore, tiers
indépendant des deux machines et déjà dans l'infra du projet, sert d'arbitre : une transaction
ne peut être gagnée que par un seul appelant à la fois, donc au plus un nœud détient le bail à
un instant donné, quoi qu'il arrive sur le réseau *entre* Lenovo et Dell.

Document : `system_ha/leader` — `{host, heartbeat_at, expires_at}`. Volontairement en dehors de
`artifacts/{APP_ID}/...` (chemin multi-tenant, voir CLAUDE.md) : concerne l'infra elle-même, pas
les données d'un utilisateur.
"""
import time

from firebase_admin import firestore

LEASE_COLLECTION = "system_ha"
LEASE_DOC = "leader"


def _lease_ref(db):
    return db.collection(LEASE_COLLECTION).document(LEASE_DOC)


def read_leader(db) -> dict | None:
    """Lecture simple, hors transaction — pour un check périodique (watchdog), pas pour décider
    seule d'une prise de bail (voir acquire_or_renew)."""
    snap = _lease_ref(db).get()
    return snap.to_dict() if snap.exists else None


def acquire_or_renew(db, node_id: str, ttl_seconds: int) -> bool:
    """Tente de prendre ou de renouveler le bail pour `node_id`.

    Retourne True si `node_id` détient le bail après l'appel (bail libre, déjà expiré, ou déjà
    détenu par `node_id`), False si un AUTRE nœud le détient encore valablement. Transaction
    Firestore : de deux tentatives concurrentes (les deux nœuds pensant le bail expiré au même
    moment), une seule peut gagner.
    """
    ref = _lease_ref(db)

    @firestore.transactional
    def _txn(transaction) -> bool:
        snap = ref.get(transaction=transaction)
        now = time.time()
        data = snap.to_dict() if snap.exists else None
        held_by_other_and_valid = (
            data is not None
            and data.get("host") != node_id
            and data.get("expires_at", 0) > now
        )
        if held_by_other_and_valid:
            return False
        transaction.set(ref, {
            "host": node_id,
            "heartbeat_at": now,
            "expires_at": now + ttl_seconds,
        })
        return True

    return _txn(db.transaction())


def release(db, node_id: str) -> None:
    """Libère volontairement le bail (arrêt propre du service) — seulement si `node_id` le
    détient encore, pour ne jamais effacer par erreur le bail d'un autre nœud."""
    ref = _lease_ref(db)
    snap = ref.get()
    if snap.exists and snap.to_dict().get("host") == node_id:
        ref.delete()
