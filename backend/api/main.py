"""Service API (FastAPI) — première tranche du Chantier A (bus de commandes uniquement).

Construit en isolation sur la branche `claude/firestore-postgres-migration`, sans toucher au
chemin Firestore existant (FIRESTORE_MIGRATION_PLAN.md §5.1). Rien n'est branché à la prod :
ni le frontend (`firestoreService.js`) ni le bot (`main.py`) n'appellent ce service pour
l'instant — bascule décidée séparément une fois toutes les tranches validées à parité.

Lancement local : uvicorn backend.api.main:app --reload
"""
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from backend.api.auth import get_current_uid
from backend.api.db import close_pool, get_pool, init_pool
from backend.api import commands_repo


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
