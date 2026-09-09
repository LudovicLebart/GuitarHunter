"""Service API (FastAPI) — première tranche du Chantier A (bus de commandes uniquement).

Construit en isolation sur la branche `claude/firestore-postgres-migration`, sans toucher au
chemin Firestore existant (FIRESTORE_MIGRATION_PLAN.md §5.1). Rien n'est branché à la prod :
ni le frontend (`firestoreService.js`) ni le bot (`main.py`) n'appellent ce service pour
l'instant — bascule décidée séparément une fois toutes les tranches validées à parité.

Lancement local : uvicorn backend.api.main:app --reload
"""
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Optional

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from backend.api.auth import get_current_uid, verify_token
from backend.api.db import DATABASE_URL, close_pool, get_pool, init_pool
from backend.api import commands_repo, deals_repo


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="Guitar Hunter API", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


class CommandCreate(BaseModel):
    type: str
    payload: Optional[Any] = None


class CommandOut(BaseModel):
    id: int
    type: str
    payload: Optional[Any] = None
    status: str


@app.post("/commands", response_model=CommandOut, status_code=status.HTTP_201_CREATED)
async def create_command(body: CommandCreate, uid: str = Depends(get_current_uid)):
    """Équivalent HTTP de `firestoreService.js::addCommand()` — même contrat (type, payload)."""
    pool = get_pool()
    command_id = await commands_repo.create_command(pool, uid, body.type, body.payload)
    return CommandOut(id=command_id, type=body.type, payload=body.payload, status="pending")


@app.get("/commands/{command_id}", response_model=CommandOut)
async def get_command(command_id: int, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    row = await commands_repo.get_command(pool, uid, command_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commande introuvable.")
    return CommandOut(id=row["id"], type=row["type"], payload=row["payload"], status=row["status"])


# --- Deals (tranche 2) --------------------------------------------------------------------
# Remplace onDealsIndexUpdate/fetchDealsByIds/rejectDeal/deleteDeal/toggleDealFavorite/
# toggleDealPurchased/setDealClassification (firestoreService.js). Chat et plan de
# restauration : tranches suivantes, pas dans ce périmètre.

@app.get("/deals")
async def list_deals(status_filter: Optional[str] = Query(None, alias="status"), favorite: bool = False, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    rows = await deals_repo.list_deals(pool, uid, status=status_filter, favorite_only=favorite)
    return [dict(r) for r in rows]


class DealIdsBody(BaseModel):
    ids: list[str]


@app.post("/deals/by-ids")
async def get_deals_by_ids(body: DealIdsBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    rows = await deals_repo.get_deals_by_ids(pool, uid, body.ids)
    return [dict(r) for r in rows]


@app.get("/deals/{deal_id}")
async def get_deal(deal_id: str, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    row = await deals_repo.get_deal(pool, uid, deal_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")
    return dict(row)


@app.patch("/deals/{deal_id}/favorite")
async def patch_favorite(deal_id: str, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    new_value = await deals_repo.toggle_favorite(pool, uid, deal_id)
    if new_value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")
    return {"isFavorite": new_value}


class PurchasedBody(BaseModel):
    purchasePrice: Optional[float] = None


@app.patch("/deals/{deal_id}/purchased")
async def patch_purchased(deal_id: str, body: PurchasedBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    new_value = await deals_repo.toggle_purchased(pool, uid, deal_id, body.purchasePrice)
    if new_value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")
    return {"isPurchased": new_value}


class ClassificationBody(BaseModel):
    classificationPath: Optional[str] = None


@app.patch("/deals/{deal_id}/classification")
async def patch_classification(deal_id: str, body: ClassificationBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await deals_repo.set_classification(pool, uid, deal_id, body.classificationPath)
    return {"manualClassification": body.classificationPath}


@app.patch("/deals/{deal_id}/reject")
async def patch_reject(deal_id: str, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await deals_repo.reject_deal(pool, uid, deal_id)
    return {"status": "rejected"}


@app.delete("/deals/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deal(deal_id: str, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    deleted = await deals_repo.delete_deal(pool, uid, deal_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")


# --- Temps réel (remplace onDealsIndexUpdate) ----------------------------------------------
# Le navigateur ne peut pas poser d'en-tête Authorization sur une connexion WebSocket native
# -> le token Firebase est passé en paramètre de requête (?token=...), vérifié avant accept().

@app.websocket("/ws/deals")
async def ws_deals(websocket: WebSocket, token: str = Query(...)):
    try:
        uid = verify_token(token)
    except ValueError:
        await websocket.close(code=1008)  # policy violation
        return

    await websocket.accept()

    # Connexion dédiée à ce socket (pas le pool applicatif) : LISTEN doit tenir sur UNE
    # connexion vivante en continu, incompatible avec un pool qui recycle ses connexions.
    listen_conn = await asyncpg.connect(DATABASE_URL)
    loop = asyncio.get_running_loop()

    def _on_notify(connection, pid, channel, payload):
        data = json.loads(payload)
        if data.get("user_id") != uid:
            return  # canal partagé entre tous les utilisateurs, filtré ici (voir schema.sql)
        loop.create_task(websocket.send_json(data))

    await listen_conn.add_listener("deal_changes", _on_notify)
    # Accusé de réception explicite : entre l'établissement de la connexion WS (accept())
    # et l'enregistrement effectif du LISTEN ci-dessus, une notification Postgres émise
    # entre-temps ne serait jamais délivrée (Postgres ne rejoue pas les NOTIFY manqués).
    # Le client attend ce message avant de déclencher une action censée produire un push,
    # au lieu de deviner un délai arbitraire.
    await websocket.send_json({"type": "ready"})
    try:
        while True:
            await websocket.receive_text()  # ne sert qu'à détecter la déconnexion du client
    except WebSocketDisconnect:
        pass
    finally:
        await listen_conn.remove_listener("deal_changes", _on_notify)
        await listen_conn.close()
