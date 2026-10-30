"""Service API (FastAPI) — première tranche du Chantier A (bus de commandes uniquement).

Construit en isolation sur la branche `claude/firestore-postgres-migration`, sans toucher au
chemin Firestore existant (FIRESTORE_MIGRATION_PLAN.md §5.1). Rien n'est branché à la prod :
ni le frontend (`firestoreService.js`) ni le bot (`main.py`) n'appellent ce service pour
l'instant — bascule décidée séparément une fois toutes les tranches validées à parité.

Lancement local : uvicorn backend.api.main:app --reload
"""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional, Union

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.gzip import GZipMiddleware

from backend.api.auth import get_current_uid, is_admin_uid, verify_token
from backend.api.db import DATABASE_URL, close_pool, get_pool, init_pool
from backend.api import (chat_repo, cities_repo, commands_repo, deals_repo, fiches_repo, logs_repo, restoration_repo, shared_repo,
                         usage_repo, users_repo)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="Guitar Hunter API", lifespan=lifespan)

logger = logging.getLogger(__name__)

# Regroupement des notifications `deal_changes` par socket (voir `ws_deals`).
_NOTIFY_BATCH_DELAY_S = 0.25
_NOTIFY_BULK_THRESHOLD = 50

# Origines autorisées à lire les réponses (le navigateur bloque sinon les appels cross-origin
# du frontend, hébergé sur une origine différente). Auth par en-tête Authorization (pas de
# cookies) — allow_credentials=False, pas besoin d'assouplir vers "*".
ALLOWED_ORIGINS = [
    "https://ludoviclebart.github.io",
    "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Server-Timing"],  # lisible par fetch() cross-origin (mesure de /deals/index)
)

# Compression des réponses HTTP (2026-09-27) : aucune n'était activée — le JSON de /deals/index
# (très répétitif, donc très compressible) partait en clair, coûteux sur la bande passante montante
# limitée d'un serveur résidentiel exposé via Tailscale Funnel. Sans effet sur les WebSockets
# (upgrades de connexion, jamais des réponses HTTP classiques — ce middleware ne s'y applique pas).
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Un handler d'exception explicite passe par CORSMiddleware (contrairement à une exception non
# gérée, qui remonte jusqu'au ServerErrorMiddleware de Starlette — en dehors de CORSMiddleware,
# donc sans en-têtes CORS) : le navigateur ne peut alors plus distinguer une vraie panne réseau
# d'un 500 serveur, les deux se rapportant comme un `TypeError: Failed to fetch` générique côté
# fetch(). Trouvé le 2026-09-26 en investiguant un "Failed to fetch" systématique côté UI.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Erreur non gérée sur %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur."})


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Config utilisateur / botStatus (Phase A.2) --------------------------------------------
# Remplace onBotConfigUpdate/updateUserConfig (firestoreService.js). L'utilisateur (ligne
# `users`) est créé par le bot (`pg_repository.py::ensure_initial_structure`), jamais ici —
# un GET avant le premier démarrage du bot renvoie 404, comme `onBotConfigUpdate` déclenchait
# `onError({ message: "Dossier Python introuvable" })` côté Firestore.

class UserConfigPatch(BaseModel):
    """Corps libre (mêmes clés que `scanConfig`/`exclusionKeywords`/`analysisConfig`, décidées
    côté frontend) — pas de schéma Pydantic strict, comme le blob JSONB `config` qui les reçoit."""
    model_config = {"extra": "allow"}


@app.get("/users/me/config")
async def get_my_config(uid: str = Depends(get_current_uid)):
    pool = get_pool()
    config = await users_repo.get_user_config(pool, uid)
    if config is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dossier Python introuvable.")
    return config


@app.patch("/users/me/config")
async def patch_my_config(body: UserConfigPatch, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    try:
        merged = await users_repo.update_user_config(pool, uid, body.model_dump(exclude_unset=True))
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dossier Python introuvable.")
    return merged


@app.websocket("/ws/users/me/config")
async def ws_user_config(websocket: WebSocket, token: str = Query(...)):
    try:
        uid = verify_token(token)
    except ValueError:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    listen_conn = await asyncpg.connect(DATABASE_URL)
    listener_added = False
    try:
        loop = asyncio.get_running_loop()

        def _on_notify(connection, pid, channel, payload):
            data = json.loads(payload)
            if data.get("user_id") != uid:
                return
            loop.create_task(websocket.send_json(data))

        await listen_conn.add_listener("user_config_changes", _on_notify)
        listener_added = True
        await websocket.send_json({"type": "ready"})
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
    finally:
        if listener_added:
            await listen_conn.remove_listener("user_config_changes", _on_notify)
        await listen_conn.close()


class CommandCreate(BaseModel):
    type: str
    payload: Optional[Any] = None


class CommandOut(BaseModel):
    id: int
    type: str
    payload: Optional[Any] = None
    status: str
    # Message d'échec renseigné par le bot (`commands.error_message`) — le frontend
    # (useCities.js) l'affiche tel quel dans le bandeau d'erreur ; sans ce champ, tout échec
    # d'ADD_CITY retombait sur un message générique sans cause.
    error: Optional[str] = None


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
    return CommandOut(id=row["id"], type=row["type"], payload=row["payload"], status=row["status"],
                      error=row["error_message"])


class UsageIn(BaseModel):
    """Usage d'un appel Gemini fait par le chat (navigateur). Bornes larges mais finies : l'endpoint
    est authentifié, pas public, mais un client buggé ne doit pas pouvoir polluer la table."""
    model: str
    action: str
    deal_id: Optional[str] = None
    images: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    thoughts_tokens: int = 0
    latency_ms: Optional[int] = None
    ok: bool = True
    error_type: Optional[str] = None


@app.post("/usage", status_code=status.HTTP_204_NO_CONTENT)
async def post_usage(body: UsageIn, uid: str = Depends(get_current_uid)):
    """Chantier C-0 : enregistre l'usage d'un tour de chat. Jamais bloquant côté client
    (appel fire-and-forget) ; ici, validation minimale puis insertion."""
    row = body.model_dump()
    for k in ("images", "input_tokens", "cached_tokens", "output_tokens", "thoughts_tokens"):
        if not 0 <= row[k] <= 5_000_000:
            raise HTTPException(status_code=422, detail=f"{k} hors bornes")
    if len(row["model"]) > 100 or len(row["action"]) > 60 or len(row["error_type"] or "") > 40:
        raise HTTPException(status_code=422, detail="model/action/error_type trop longs")
    await usage_repo.add_usage(get_pool(), uid, row)


@app.get("/logs")
async def list_logs(limit: int = Query(100, ge=1, le=1000), uid: str = Depends(get_current_uid)):
    """Derniers logs du bot de l'utilisateur (LogViewer), du plus ancien au plus récent. Pas de
    WebSocket : le frontend poll toutes les 3s, cadence du flush de `PostgresHandler`."""
    return await logs_repo.list_logs(get_pool(), uid, limit)


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


# Déclaré AVANT /deals/{deal_id} : un chemin dynamique à un segment intercepterait sinon
# silencieusement "index" comme un deal_id (même piège déjà rencontré sur PATCH .../order vs
# .../{item_id}, tranche 4 restauration — voir JOURNAL.md).
@app.get("/deals/index")
async def list_deals_index(request: Request, status_filter: Optional[str] = Query(None, alias="status"), favorite: bool = False, perf: bool = False, uid: str = Depends(get_current_uid)):
    """Version allégée de `GET /deals` (2026-09-26) : exclut les colonnes lourdes (images,
    texte de raisonnement IA, overrides détaillés) — mesuré à 34 Mo/7210 annonces sur `GET /deals`,
    téléchargés et parsés en entier à chaque chargement de page. `apiService.js::onDealsIndexUpdate`
    consomme désormais cet endpoint pour peupler la liste/les stats ; les documents complets
    restent chargés à la demande via `POST /deals/by-ids`, seulement pour les annonces visibles
    (mécanisme déjà existant côté frontend, `useDealsManager.js::loadedDeals`).

    `?perf=1` (2026-10-13, diagnostic opt-in) : réponse mesurée — en-têtes `Server-Timing` (`sql`,
    `ser`, `raw`, `rows`) et une ligne de log. Sans ce paramètre, chemin et en-têtes inchangés."""
    pool = get_pool()
    # Le diagnostic coûte une sérialisation tamponnée en mémoire sur l'unique worker : réservé aux ADMINS (claim `admin`) ;
    # pour tout autre utilisateur `?perf=1` est ignoré en silence (chemin normal, aucune erreur côté client).
    if perf and not await asyncio.to_thread(is_admin_uid, uid):
        perf = False
    if not perf:
        rows = await deals_repo.list_deals_index(pool, uid, status=status_filter, favorite_only=favorite)
        return [dict(r) for r in rows]
    t0 = time.perf_counter()
    rows = await deals_repo.list_deals_index(pool, uid, status=status_filter, favorite_only=favorite)
    t_sql = time.perf_counter()
    response = JSONResponse(content=jsonable_encoder([dict(r) for r in rows]))
    t_ser = time.perf_counter()
    sql_ms, ser_ms, raw_bytes = (t_sql - t0) * 1000, (t_ser - t_sql) * 1000, len(response.body)
    response.headers["Server-Timing"] = f'sql;dur={sql_ms:.0f}, ser;dur={ser_ms:.0f}, raw;desc="{raw_bytes}", rows;desc="{len(rows)}"'
    origin = request.headers.get("origin")
    if origin in ALLOWED_ORIGINS:       # la même liste que CORS : un front de test autorisé reçoit aussi ses mesures
        response.headers["Timing-Allow-Origin"] = origin
    logger.info("GET /deals/index?perf=1: %d annonces, sql=%.0f ms, sérialisation=%.0f ms, brut=%.1f Mo", len(rows), sql_ms, ser_ms, raw_bytes / 1e6)
    return response


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
    confirmUnpurchase: bool = False  # exigé pour DÉSACHETER (efface prix, date et revente)


@app.patch("/deals/{deal_id}/purchased")
async def patch_purchased(deal_id: str, body: PurchasedBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    new_value = await deals_repo.toggle_purchased(pool, uid, deal_id, body.purchasePrice, body.confirmUnpurchase)
    if new_value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")
    if new_value == "confirmation_required":
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, "Annuler un achat efface le prix, la date et la revente : confirmation requise.")
    if new_value == "locked_by_other_user":
        # Achat GLOBAL (2026-09-19) : un autre utilisateur a déjà acheté cette annonce partagée.
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette annonce a déjà été achetée par un autre utilisateur.")
    return {"isPurchased": new_value}


class UserSaleBody(BaseModel):
    salePrice: Optional[float] = None
    soldAt: Optional[datetime] = None


@app.patch("/deals/{deal_id}/user-sale")
async def patch_user_sale(deal_id: str, body: UserSaleBody, uid: str = Depends(get_current_uid)):
    """Revente par l'acheteur (2026-10-10) : `salePrice` absent/null annule la revente."""
    if body.salePrice is not None and body.salePrice < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Le prix de vente doit être positif.")
    pool = get_pool()
    result = await deals_repo.set_user_sale(pool, uid, deal_id, body.salePrice, body.soldAt)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")
    if result == "not_purchaser":
        raise HTTPException(status.HTTP_409_CONFLICT, "Seul l'acheteur peut déclarer la revente.")
    return {"userSalePrice": body.salePrice}


class ClassificationBody(BaseModel):
    classificationPath: Optional[str] = None


@app.patch("/deals/{deal_id}/classification")
async def patch_classification(deal_id: str, body: ClassificationBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    found = await deals_repo.set_classification(pool, uid, deal_id, body.classificationPath)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")
    return {"manualClassification": body.classificationPath}


class GalleryImageBody(BaseModel):
    url: str


@app.post("/deals/{deal_id}/gallery")
async def add_gallery_image(deal_id: str, body: GalleryImageBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    found = await deals_repo.add_gallery_image(pool, uid, deal_id, body.url)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")
    return {"status": "ok"}


class AnalysisOverridesBody(BaseModel):
    """Corps libre (sous-ensemble quelconque des colonnes `aiAnalysis` promues, voir
    `deals_repo.py::apply_manual_analysis_overrides`) — pas de schéma Pydantic strict, la
    whitelist réelle est appliquée côté repository."""
    model_config = {"extra": "allow"}


@app.patch("/deals/{deal_id}/analysis-overrides")
async def patch_analysis_overrides(deal_id: str, body: AnalysisOverridesBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    found = await deals_repo.apply_manual_analysis_overrides(pool, uid, deal_id, body.model_dump(exclude_unset=True))
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")
    return {"status": "ok"}


@app.patch("/deals/{deal_id}/reject")
async def patch_reject(deal_id: str, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    found = await deals_repo.reject_deal(pool, uid, deal_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")
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
    # `listener_added` + le try englobant dès ici (pas seulement autour de la boucle de
    # réception) : si add_listener() ou send_json() lève (ex: client déconnecté juste après
    # accept()) avant d'atteindre le try/finally plus bas, listen_conn ne serait jamais fermée
    # — fuite de connexion Postgres réelle trouvée en revue de code, hors du pool borné
    # (max_size=10), qui finit par épuiser les connexions disponibles côté serveur.
    listener_added = False
    pending_ids: set = set()
    flush_handle = None
    try:
        loop = asyncio.get_running_loop()
        pool = get_pool()

        # Regroupement des notifications (2026-10-13) : le trigger émet UN NOTIFY par ligne
        # écrite (un UPDATE de milliers de lignes = des milliers de messages), et chacun coûtait
        # une requête de visibilité au pool (max 10) — qui affamait aussi `/deals/index`. On
        # accumule les ids pendant `_NOTIFY_BATCH_DELAY_S`, puis UNE requête `ANY($2)` et un
        # message par id visible ; au-delà de `_NOTIFY_BULK_THRESHOLD` ids visibles, un seul
        # message `{"type": "bulk"}` (le client relit de toute façon l'index complet).
        async def _flush_pending():
            nonlocal flush_handle
            flush_handle = None
            ids = list(pending_ids)
            pending_ids.clear()
            if not ids:
                return
            try:
                # 2026-09-19 (catalogue partagé) : le trigger ne pousse plus `user_id` (une annonce
                # peut concerner PLUSIEURS utilisateurs) — c'est ici, pas dans le trigger, que se
                # décide qui est concerné : uniquement les utilisateurs dont le scan a matché ce
                # deal_id (voir `deals_repo._is_visible`, même logique).
                rows = await pool.fetch(
                    "SELECT deal_id FROM user_deal_matches WHERE user_id = $1 AND deal_id = ANY($2::text[])",
                    uid, ids,
                )
                visible = [r["deal_id"] for r in rows]
                if len(visible) > _NOTIFY_BULK_THRESHOLD:
                    await websocket.send_json({"type": "bulk"})
                else:
                    for deal_id in visible:
                        await websocket.send_json({"id": deal_id})
            except Exception:
                # Socket fermé entre-temps ou pool indisponible : le client rattrape de toute
                # façon (reconnexion + relecture complète au "ready").
                logger.debug("ws_deals: envoi groupé abandonné", exc_info=True)

        def _on_notify(connection, pid, channel, payload):
            nonlocal flush_handle
            deal_id = json.loads(payload).get("id")
            if deal_id is None:
                return
            pending_ids.add(deal_id)
            if flush_handle is None:
                flush_handle = loop.call_later(_NOTIFY_BATCH_DELAY_S, lambda: loop.create_task(_flush_pending()))

        # Si Postgres coupe cette connexion LISTEN (redémarrage, timeout), le WebSocket resterait
        # ouvert mais muet : le client se croirait à jour sans l'être. On ferme le socket pour
        # qu'il se reconnecte (le "ready" suivant déclenche une relecture complète).
        async def _close_ws_after_pg_loss():
            try:
                await websocket.close(code=1011)
            except Exception:
                pass  # déjà fermé côté client

        def _on_pg_terminated(connection):
            loop.create_task(_close_ws_after_pg_loss())

        listen_conn.add_termination_listener(_on_pg_terminated)
        await listen_conn.add_listener("deal_changes", _on_notify)
        listener_added = True
        # Accusé de réception explicite : entre l'établissement de la connexion WS (accept())
        # et l'enregistrement effectif du LISTEN ci-dessus, une notification Postgres émise
        # entre-temps ne serait jamais délivrée (Postgres ne rejoue pas les NOTIFY manqués).
        # Le client attend ce message avant de déclencher une action censée produire un push,
        # au lieu de deviner un délai arbitraire.
        await websocket.send_json({"type": "ready"})
        try:
            while True:
                await websocket.receive_text()  # ne sert qu'à détecter la déconnexion du client
        except (WebSocketDisconnect, RuntimeError):
            # RuntimeError : socket déjà fermé côté serveur (connexion LISTEN coupée, voir
            # `_on_pg_terminated`) — Starlette lève alors au lieu de WebSocketDisconnect.
            pass
    finally:
        if flush_handle is not None:
            flush_handle.cancel()
        if listener_added:
            await listen_conn.remove_listener("deal_changes", _on_notify)
            # Retiré AVANT close() : fermer nous-mêmes la connexion déclencherait sinon le
            # listener de terminaison (fermeture inutile d'un socket déjà parti).
            listen_conn.remove_termination_listener(_on_pg_terminated)
        await listen_conn.close()


# --- Chat (tranche 3) ----------------------------------------------------------------------
# Remplace onDealChatUpdate/addDealChatMessage/replaceDealChatMessage/markChatMessage*
# (firestoreService.js). `deal_chat` n'a pas de user_id propre (FK vers guitar_deals) : chaque
# route vérifie la VISIBILITÉ du deal parent (pas la propriété/achat — corrigé 2026-09-27, le
# chat avait été réservé à l'acheteur par erreur en même temps que le plan de restauration, qui
# lui reste réservé à l'acheteur ou aux favoris : voir `_require_plan_access` plus bas).

async def _require_plan_access(pool, deal_id: str, uid: str) -> None:
    """Plan de restauration personnel (2026-10-11) : acheteur de l'annonce, ou utilisateur qui la
    voit et l'a mise en favori (préparation avant achat)."""
    if not await restoration_repo.has_plan_access(pool, deal_id, uid):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")


async def _require_deal_visible(pool, deal_id: str, uid: str) -> None:
    if not await chat_repo.is_deal_visible(pool, deal_id, uid):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")


@app.get("/deals/{deal_id}/chat")
async def list_chat(deal_id: str, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_deal_visible(pool, deal_id, uid)
    rows = await chat_repo.list_messages(pool, deal_id)
    return [dict(r) for r in rows]


class ChatMessageCreate(BaseModel):
    role: str
    parts: Any
    displayText: Optional[str] = None
    attachedImagePartIndices: Optional[list[int]] = None
    restorationProposals: Optional[list[dict]] = None
    photoRecall: Optional[dict] = None
    isError: bool = False
    requalificationProposal: Optional[dict] = None


@app.post("/deals/{deal_id}/chat", status_code=status.HTTP_201_CREATED)
async def create_chat_message(deal_id: str, body: ChatMessageCreate, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_deal_visible(pool, deal_id, uid)
    message_id = await chat_repo.add_message(
        pool, deal_id, body.role, body.parts, body.displayText,
        body.attachedImagePartIndices, body.restorationProposals,
        body.photoRecall, body.isError, body.requalificationProposal,
    )
    return {"id": message_id}


class ChatMessageReplace(BaseModel):
    parts: Any
    displayText: Optional[str] = None
    restorationProposals: Optional[list[dict]] = None
    photoRecall: Optional[dict] = None
    isError: bool = False
    requalificationProposal: Optional[dict] = None


async def _require_chat_message_found(found: bool) -> None:
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message introuvable pour cette annonce.")


@app.patch("/deals/{deal_id}/chat/{message_id}")
async def replace_chat_message(deal_id: str, message_id: int, body: ChatMessageReplace, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_deal_visible(pool, deal_id, uid)
    found = await chat_repo.replace_message(
        pool, deal_id, message_id, body.parts, body.displayText,
        body.restorationProposals, body.photoRecall, body.isError, body.requalificationProposal,
    )
    await _require_chat_message_found(found)
    return {"status": "ok"}


class GalleryMarkBody(BaseModel):
    partIndex: int
    url: str


@app.patch("/deals/{deal_id}/chat/{message_id}/gallery")
async def mark_gallery(deal_id: str, message_id: int, body: GalleryMarkBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_deal_visible(pool, deal_id, uid)
    found = await chat_repo.mark_added_to_gallery(pool, deal_id, message_id, body.partIndex, body.url)
    await _require_chat_message_found(found)
    return {"status": "ok"}


class RestorationProposalStatusBody(BaseModel):
    proposalIndex: int
    status: str
    # L'id d'étape est un ENTIER depuis Postgres (BIGSERIAL, renvoyé tel quel par POST /restoration-plan) ;
    # `Optional[str]` rejetait ce que le front envoie (422) : l'étape était créée puis la proposition
    # restait « non appliquée » (erreur affichée, doublon à chaque nouveau clic).
    itemId: Optional[Union[int, str]] = None


@app.patch("/deals/{deal_id}/chat/{message_id}/restoration-proposal")
async def mark_restoration_proposal(deal_id: str, message_id: int, body: RestorationProposalStatusBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_deal_visible(pool, deal_id, uid)
    found = await chat_repo.mark_restoration_proposal_status(pool, deal_id, message_id, body.proposalIndex, body.status, body.itemId)
    await _require_chat_message_found(found)
    return {"status": "ok"}


class RequalificationStatusBody(BaseModel):
    status: str


@app.patch("/deals/{deal_id}/chat/{message_id}/requalification-proposal")
async def mark_requalification_proposal(deal_id: str, message_id: int, body: RequalificationStatusBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_deal_visible(pool, deal_id, uid)
    found = await chat_repo.mark_requalification_proposal_status(pool, deal_id, message_id, body.status)
    await _require_chat_message_found(found)
    return {"status": "ok"}


@app.websocket("/ws/deals/{deal_id}/chat")
async def ws_deal_chat(websocket: WebSocket, deal_id: str, token: str = Query(...)):
    try:
        uid = verify_token(token)
    except ValueError:
        await websocket.close(code=1008)
        return

    # Vérifié via une connexion à part (avant accept()) : le pool applicatif normal convient
    # ici, contrairement à listen_conn qui doit rester dédiée à LISTEN pour toute la durée du socket.
    # Visibilité (pas propriété/achat) : voir _require_deal_visible, même correctif 2026-09-27.
    pool = get_pool()
    if not await chat_repo.is_deal_visible(pool, deal_id, uid):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    listen_conn = await asyncpg.connect(DATABASE_URL)
    listener_added = False  # voir ws_deals : évite la fuite de connexion si accept/LISTEN échoue avant le try/finally
    try:
        loop = asyncio.get_running_loop()

        def _on_notify(connection, pid, channel, payload):
            data = json.loads(payload)
            if data.get("deal_id") != deal_id:
                return  # canal partagé entre toutes les annonces, filtré ici
            loop.create_task(websocket.send_json(data))

        await listen_conn.add_listener("chat_changes", _on_notify)
        listener_added = True
        await websocket.send_json({"type": "ready"})  # voir ws_deals : évite la course accept/LISTEN
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
    finally:
        if listener_added:
            await listen_conn.remove_listener("chat_changes", _on_notify)
        await listen_conn.close()


# --- Fiches techniques de restauration (lot C) -------------------------------------------------
# Lecture seule de la base commune marques/fiches (voir fiches_repo.py) ; chargement par
# backend/scripts/seed_guitar_fiches.py. Catalogue partagé : toute personne connectée peut lire les fiches.

@app.get("/fiches")
async def list_fiches(categorie: Optional[str] = None, uid: str = Depends(get_current_uid)):
    return await fiches_repo.list_fiches(get_pool(), categorie)


@app.get("/fiches/{slug}")
async def get_fiche(slug: str, uid: str = Depends(get_current_uid)):
    fiche = await fiches_repo.get_fiche(get_pool(), slug)
    if fiche is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fiche introuvable.")
    return fiche


class DealFichesSearch(BaseModel):
    q: Optional[str] = Field(None, max_length=2000)      # la question en cours dans le chat
    limit: int = Field(5, ge=1, le=20)


# POST et non GET : la QUESTION de la personne est dans le corps de la requête. Dans l'URL (`?q=…`) elle serait écrite en clair
# dans les journaux d'accès (uvicorn, Tailscale Funnel) ; un corps n'y figure pas. C'est une recherche, sans effet de bord.
@app.post("/deals/{deal_id}/fiches/search")
async def search_deal_fiches(deal_id: str, body: DealFichesSearch, uid: str = Depends(get_current_uid)):
    """Fiches utiles pour une annonce et la question `q` en cours dans le chat, classées par pertinence : voir
    `fiches_repo.fiches_for_deal`. Visible comme le chat (toute personne qui voit l'annonce) ; les fiches liées aux
    ÉTAPES du plan et leurs libellés ne sont prises en compte que pour qui a accès au plan (acheteur, ou favori) et ne
    portent que SES propres étapes (le plan est personnel). Appelée à chaque question (pas à chaque frappe : le client
    doit temporiser) ; trois lectures indépendantes en parallèle, puis le plan, puis une seule requête de métadonnées."""
    q, limit = body.q, body.limit
    pool = get_pool()
    visible, plan_access, deal_texts = await asyncio.gather(
        chat_repo.is_deal_visible(pool, deal_id, uid), restoration_repo.has_plan_access(pool, deal_id, uid),
        fiches_repo.deal_text(pool, deal_id))
    if not visible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")
    steps = await restoration_repo.list_step_refs(pool, deal_id, uid) if plan_access else []
    return await fiches_repo.fiches_for_deal(
        pool, q=q, step_slugs=[s["fiche_slug"] for s in steps if s["fiche_slug"]],
        step_labels=[s["label"] for s in steps if s["label"]], deal_texts=deal_texts, limit=limit)


# --- Plan de restauration (tranche 4) --------------------------------------------------------
# Remplace onRestorationPlanUpdate/addRestorationItem/updateRestorationItem/deleteRestorationItem/
# reorderRestorationItems/backfillRestorationOrder/addRestorationItemPhoto/removeRestorationItemPhoto
# (firestoreService.js). Même absence de user_id propre que deal_chat -> même vérification via
# _require_plan_access (acheteur ou favori, plan personnel par utilisateur — 2026-10-11).

@app.get("/deals/{deal_id}/restoration-plan")
async def list_restoration_plan(deal_id: str, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_plan_access(pool, deal_id, uid)
    items = [dict(r) for r in await restoration_repo.list_items(pool, deal_id, uid)]
    # Une fiche retirée de la base (`--prune`) laisse son slug sur l'étape : on ne renvoie jamais un lien mort.
    linked = {i["fiche_slug"] for i in items if i.get("fiche_slug")}
    if linked:
        known = await fiches_repo.existing_slugs(pool, linked)
        for item in items:
            if item.get("fiche_slug") and item["fiche_slug"] not in known:
                item["fiche_slug"] = None
    return items


class RestorationItemCreate(BaseModel):
    label: str
    category: Optional[str] = None
    estimatedCost: Optional[float] = None
    notes: Optional[str] = None
    source: str = "user"
    proposedByMessageId: Optional[int] = None
    order: Optional[int] = None
    ficheSlug: Optional[str] = None


async def _require_known_fiche(pool, slug: Optional[str]) -> None:
    """Un lien d'étape vers une fiche doit viser une fiche qui existe (`None` = pas de lien / effacer le lien)."""
    if slug is not None and slug not in await fiches_repo.existing_slugs(pool, [slug]):
        raise HTTPException(status_code=422, detail="Fiche technique inconnue.")


@app.post("/deals/{deal_id}/restoration-plan", status_code=status.HTTP_201_CREATED)
async def create_restoration_item(deal_id: str, body: RestorationItemCreate, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_plan_access(pool, deal_id, uid)
    await _require_known_fiche(pool, body.ficheSlug)
    item_id = await restoration_repo.add_item(
        pool, deal_id, uid, body.label, body.category, body.estimatedCost, body.notes,
        body.source, body.proposedByMessageId, body.order, body.ficheSlug,
    )
    return {"id": item_id}


class RestorationReorderBody(BaseModel):
    orderedItemIds: list[int]


# Enregistrée AVANT les routes /{item_id} ci-dessous : Starlette matche les routes dans leur
# ordre de déclaration, et "order" collerait sinon sur le pattern {item_id} (échouant la
# validation int -> 422) plutôt que sur cette route dédiée.
@app.patch("/deals/{deal_id}/restoration-plan/order")
async def reorder_restoration_items(deal_id: str, body: RestorationReorderBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_plan_access(pool, deal_id, uid)
    await restoration_repo.reorder_items(pool, deal_id, uid, body.orderedItemIds)
    return {"status": "ok"}


class RestorationItemPatch(BaseModel):
    label: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    estimatedCost: Optional[float] = None
    actualCost: Optional[float] = None
    notes: Optional[str] = None
    ficheSlug: Optional[str] = None


async def _require_restoration_item_found(found: bool) -> None:
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Étape introuvable pour cette annonce.")


@app.patch("/deals/{deal_id}/restoration-plan/{item_id}")
async def patch_restoration_item(deal_id: str, item_id: int, body: RestorationItemPatch, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_plan_access(pool, deal_id, uid)
    patch = body.model_dump(exclude_unset=True)
    if patch.get("ficheSlug") is not None:
        # L'étape d'abord : 404 si elle n'existe pas (un patch vide ne fait que vérifier), puis 422 si la fiche est inconnue.
        await _require_restoration_item_found(await restoration_repo.update_item(pool, deal_id, uid, item_id, {}))
        await _require_known_fiche(pool, patch["ficheSlug"])
    found = await restoration_repo.update_item(pool, deal_id, uid, item_id, patch)
    await _require_restoration_item_found(found)
    return {"status": "ok"}


@app.delete("/deals/{deal_id}/restoration-plan/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_restoration_item(deal_id: str, item_id: int, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_plan_access(pool, deal_id, uid)
    found = await restoration_repo.delete_item(pool, deal_id, uid, item_id)
    await _require_restoration_item_found(found)


class RestorationPhotoBody(BaseModel):
    url: str


@app.post("/deals/{deal_id}/restoration-plan/{item_id}/photos")
async def add_restoration_photo(deal_id: str, item_id: int, body: RestorationPhotoBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_plan_access(pool, deal_id, uid)
    found = await restoration_repo.add_photo(pool, deal_id, uid, item_id, body.url)
    await _require_restoration_item_found(found)
    return {"status": "ok"}


@app.delete("/deals/{deal_id}/restoration-plan/{item_id}/photos")
async def remove_restoration_photo(deal_id: str, item_id: int, body: RestorationPhotoBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_plan_access(pool, deal_id, uid)
    found = await restoration_repo.remove_photo(pool, deal_id, uid, item_id, body.url)
    await _require_restoration_item_found(found)
    return {"status": "ok"}


@app.websocket("/ws/deals/{deal_id}/restoration-plan")
async def ws_restoration_plan(websocket: WebSocket, deal_id: str, token: str = Query(...)):
    try:
        uid = verify_token(token)
    except ValueError:
        await websocket.close(code=1008)
        return

    pool = get_pool()
    if not await restoration_repo.has_plan_access(pool, deal_id, uid):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    listen_conn = await asyncpg.connect(DATABASE_URL)
    listener_added = False  # voir ws_deals : évite la fuite de connexion si accept/LISTEN échoue avant le try/finally
    try:
        loop = asyncio.get_running_loop()

        def _on_notify(connection, pid, channel, payload):
            data = json.loads(payload)
            if data.get("deal_id") != deal_id or data.get("user_id") != uid:
                return  # canal partagé entre toutes les annonces et tous les utilisateurs, filtré ici
            loop.create_task(websocket.send_json(data))

        await listen_conn.add_listener("restoration_plan_changes", _on_notify)
        listener_added = True
        await websocket.send_json({"type": "ready"})  # voir ws_deals : évite la course accept/LISTEN
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
    finally:
        if listener_added:
            await listen_conn.remove_listener("restoration_plan_changes", _on_notify)
        await listen_conn.close()


# --- Villes (tranche 5) -----------------------------------------------------------------------
# Remplace onCitiesUpdate/deleteCity/toggleCityScannable/setCityKijijiRadius (firestoreService.js).
# L'ajout d'une ville passe déjà par la commande ADD_CITY (tranche 1, table `commands`) — le
# catalogue partagé lui-même reste écrit par bot.py côté Firestore jusqu'à la bascule, rien à
# construire ici pour ce chemin (voir cities_repo.py).

@app.get("/cities")
async def list_cities(uid: str = Depends(get_current_uid)):
    pool = get_pool()
    rows = await cities_repo.list_cities_for_user(pool, uid)
    return [dict(r) for r in rows]


async def _require_city_exists(pool, city_id: str) -> None:
    if not await cities_repo.city_exists(pool, city_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ville introuvable dans le catalogue.")


@app.delete("/cities/{city_id}/pref", status_code=status.HTTP_204_NO_CONTENT)
async def delete_city_pref(city_id: str, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_city_exists(pool, city_id)
    await cities_repo.delete_city_pref(pool, uid, city_id)


@app.patch("/cities/{city_id}/scannable")
async def toggle_city_scannable(city_id: str, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_city_exists(pool, city_id)
    new_value = await cities_repo.toggle_scannable(pool, uid, city_id)
    return {"isScannable": new_value}


class KijijiRadiusBody(BaseModel):
    radiusKm: Optional[float] = None


@app.patch("/cities/{city_id}/kijiji-radius")
async def set_city_kijiji_radius(city_id: str, body: KijijiRadiusBody, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await _require_city_exists(pool, city_id)
    await cities_repo.set_kijiji_radius(pool, uid, city_id, body.radiusKm)
    return {"kijijiRadiusKm": body.radiusKm}


@app.websocket("/ws/cities")
async def ws_cities(websocket: WebSocket, token: str = Query(...)):
    try:
        uid = verify_token(token)
    except ValueError:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    listen_conn = await asyncpg.connect(DATABASE_URL)
    # Deux flags distincts (voir ws_deals pour le raisonnement) : chaque add_listener() peut
    # échouer indépendamment, remove_listener() ne doit être tenté que sur celui qui a réussi.
    pref_listener_added = False
    catalog_listener_added = False
    try:
        loop = asyncio.get_running_loop()

        def _on_pref_notify(connection, pid, channel, payload):
            data = json.loads(payload)
            if data.get("user_id") != uid:
                return  # canal partagé entre tous les utilisateurs, filtré ici
            loop.create_task(websocket.send_json({"type": "city_pref_changed", "cityId": data["city_id"]}))

        def _on_catalog_notify(connection, pid, channel, payload):
            data = json.loads(payload)
            # Catalogue partagé : diffusé à tous les clients connectés, pas de filtrage par uid.
            loop.create_task(websocket.send_json({"type": "catalog_changed", "cityId": data["city_id"]}))

        await listen_conn.add_listener("city_prefs_changes", _on_pref_notify)
        pref_listener_added = True
        await listen_conn.add_listener("cities_catalog_changes", _on_catalog_notify)
        catalog_listener_added = True
        await websocket.send_json({"type": "ready"})  # voir ws_deals : évite la course accept/LISTEN
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
    finally:
        if pref_listener_added:
            await listen_conn.remove_listener("city_prefs_changes", _on_pref_notify)
        if catalog_listener_added:
            await listen_conn.remove_listener("cities_catalog_changes", _on_catalog_notify)
        await listen_conn.close()


# --- Annonces partagées (tranche 6, dernière) -----------------------------------------------
# Remplace createSharedDeal/getSharedDeal (firestoreService.js). Pas de temps réel : SharedDealPage
# fait un getDoc ponctuel, jamais un onSnapshot — rien à répliquer côté WebSocket ici.
# Écriture réservée à un utilisateur authentifié QUELCONQUE (pas au propriétaire du deal — vérifié
# dans firestore.rules : `allow write: if request.auth != null`), lecture publique sans auth.

class SharedDealCreate(BaseModel):
    title: Optional[str] = None
    price: Optional[float] = None
    location: Optional[str] = None
    link: Optional[str] = None
    description: Optional[str] = None
    storageImageUrls: list[str] = []
    imageUrls: list[str] = []
    verdict: Optional[str] = None
    scores: dict = {}
    analysis: Optional[str] = None
    tier3_summary: Optional[str] = None
    # Analyse IA complète (résumé, fiche technique, raisonnement détaillé, valeur estimée…) :
    # la page partagée affiche le même rapport que la modale de l'app.
    aiAnalysis: dict = {}
    priceDropAmount: Optional[float] = None
    sharedAt: Optional[str] = None


@app.put("/shared-deals/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def upsert_shared_deal(deal_id: str, body: SharedDealCreate, uid: str = Depends(get_current_uid)):
    pool = get_pool()
    await shared_repo.upsert_shared_deal(pool, deal_id, body.model_dump())


@app.get("/shared-deals/{deal_id}")
async def get_shared_deal(deal_id: str):
    pool = get_pool()
    row = await shared_repo.get_shared_deal(pool, deal_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce partagée introuvable.")
    return row["snapshot"]
