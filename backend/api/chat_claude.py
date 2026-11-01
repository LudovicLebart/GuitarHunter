"""Chat de l'annonce sur Claude (2026-11-01) : le navigateur envoie la conversation déjà au format Anthropic, ce module la
valide, appelle l'API Anthropic (la clé reste côté serveur) et renvoie le texte au fil de l'eau en SSE. Il enregistre lui-même
l'usage dans `llm_usage` (le coût du chat ne repose donc pas sur un chiffre déclaré par le navigateur) puis vérifie l'alerte.

Deux usages :
- `stream_chat`  : tour de conversation (Sonnet 5.5 par défaut, Opus 5.5 possible), outils fournis par le navigateur qui les
  exécute (propositions d'étapes, rappel de photo, requalification) ; cache de prompt sur le système et la fin de la conversation.
- `stream_consult` : consultation d'Opus. Il ne reçoit PAS la conversation : seulement un dossier autonome rédigé par Sonnet
  (jusqu'à 2 photos), sans outils, avec une réponse plafonnée et une consigne système fixée ici (Opus coûte cher).

Module autonome (n'importe que `llm_pricing`, `usage_repo`, `cost_alert`) : l'API de production ne recopie qu'une liste de
modules de `backend/`, mais tout `backend/api/` est déployé.
"""
import asyncio
import json
import logging
import os
import time

from backend.api import cost_alert, usage_repo

log = logging.getLogger("chat_claude")

SONNET = "claude-sonnet-5-5"
OPUS = "claude-opus-5-5"
ALLOWED_MODELS = (SONNET, OPUS)

# Bornes de validation : l'endpoint est authentifié mais il ne doit pas servir de passerelle Claude générique.
MAX_SYSTEM_CHARS = 40_000
MAX_TOOLS = 8
MAX_MESSAGES = 400
MAX_IMAGES = 40
MAX_IMAGE_B64_CHARS = 6_000_000  # un JPEG de 1024 px pèse ~150 ko ; 6 M caractères base64 ≈ 4,5 Mo
MAX_TOTAL_B64_CHARS = 30_000_000
MAX_TEXT_CHARS = 400_000
ALLOWED_BLOCK_TYPES = ("text", "image", "tool_use", "tool_result", "thinking", "redacted_thinking")
ALLOWED_IMAGE_MEDIA = ("image/jpeg", "image/png", "image/webp", "image/gif")

CHAT_MAX_TOKENS = int(os.getenv("CHAT_CLAUDE_MAX_TOKENS", 8000))  # la réflexion compte dans max_tokens
CHAT_EFFORT = os.getenv("CHAT_CLAUDE_EFFORT", "medium").strip().lower()
CHAT_TIMEOUT_S = int(os.getenv("CHAT_CLAUDE_TIMEOUT_SECONDS", 240))
CONSULT_MAX_TOKENS = int(os.getenv("CHAT_OPUS_MAX_TOKENS", 4000))
CONSULT_EFFORT = os.getenv("CHAT_OPUS_EFFORT", "medium").strip().lower()
MAX_BRIEF_CHARS = 14_000
MAX_CONSULT_IMAGES = 2
KEEPALIVE_S = 15

CONSULT_SYSTEM = (
    "Tu es Opus, consulté par l'assistant de Guitar Hunter AI (évaluation de guitares, amplis et matériel musical d'occasion, "
    "revente après restauration) sur un point que son propre avis ne tranche pas. Tu reçois un dossier autonome : la question, "
    "les faits de l'annonce, ce qui est déjà établi et ce qui reste incertain. Tu n'as pas la conversation complète. "
    "Réponds en français, de façon structurée et concise : ta conclusion d'abord, puis les raisons, puis ce qui resterait à "
    "vérifier. Cite tes sources quand tu t'appuies sur un fait précis (modèle, année, prix du marché, procédure) et dis "
    "clairement quand tu n'es pas sûr plutôt que de deviner. Si le dossier est insuffisant, dis exactement ce qu'il manque."
)


class ChatRequestError(ValueError):
    """Requête refusée avant tout appel à Claude (422 côté route)."""


def _clean_block(block: dict, counters: dict) -> dict:
    if not isinstance(block, dict) or block.get("type") not in ALLOWED_BLOCK_TYPES:
        raise ChatRequestError("Bloc de message non autorisé.")
    kind = block["type"]
    if kind == "text":
        text = str(block.get("text", ""))
        counters["text"] += len(text)
        return {"type": "text", "text": text}
    if kind == "image":
        src = block.get("source") or {}
        data = str(src.get("data", ""))
        if src.get("type") != "base64" or src.get("media_type") not in ALLOWED_IMAGE_MEDIA or not data \
                or len(data) > MAX_IMAGE_B64_CHARS:
            raise ChatRequestError("Image invalide ou trop lourde.")
        counters["images"] += 1
        counters["b64"] += len(data)
        return {"type": "image", "source": {"type": "base64", "media_type": src["media_type"], "data": data}}
    if kind == "tool_use":
        return {"type": "tool_use", "id": str(block.get("id", ""))[:80], "name": str(block.get("name", ""))[:80],
                "input": block.get("input") if isinstance(block.get("input"), dict) else {}}
    if kind == "tool_result":
        content = block.get("content", "")
        counters["text"] += len(str(content))
        return {"type": "tool_result", "tool_use_id": str(block.get("tool_use_id", ""))[:80], "content": str(content)}
    # thinking / redacted_thinking : à renvoyer TELS QUELS (signature) pendant la boucle d'outils d'un même tour.
    return dict(block)


def validate_chat(system: str, tools: list, messages: list, model: str) -> dict:
    """Valide et nettoie une requête de chat ; retourne les arguments prêts pour l'API, plus `images` (compte)."""
    if model not in ALLOWED_MODELS:
        raise ChatRequestError("Modèle non autorisé.")
    if not isinstance(system, str) or not system.strip() or len(system) > MAX_SYSTEM_CHARS:
        raise ChatRequestError("Consigne système invalide.")
    if not isinstance(tools, list) or len(tools) > MAX_TOOLS:
        raise ChatRequestError("Trop d'outils.")
    clean_tools = []
    for tool in tools:
        if not isinstance(tool, dict) or not tool.get("name") or not isinstance(tool.get("input_schema"), dict):
            raise ChatRequestError("Outil invalide.")
        clean_tools.append({"name": str(tool["name"])[:80], "description": str(tool.get("description", ""))[:4000],
                            "input_schema": tool["input_schema"]})
    if not isinstance(messages, list) or not messages or len(messages) > MAX_MESSAGES or messages[0].get("role") != "user":
        raise ChatRequestError("Conversation invalide.")
    counters = {"text": 0, "images": 0, "b64": 0}
    clean = []
    for msg in messages:
        if msg.get("role") not in ("user", "assistant"):
            raise ChatRequestError("Rôle de message invalide.")
        content = msg.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list) or not content:
            raise ChatRequestError("Message vide.")
        clean.append({"role": msg["role"], "content": [_clean_block(b, counters) for b in content]})
    if counters["images"] > MAX_IMAGES or counters["b64"] > MAX_TOTAL_B64_CHARS or counters["text"] > MAX_TEXT_CHARS:
        raise ChatRequestError("Conversation trop volumineuse.")
    return {"model": model, "system": system, "tools": clean_tools, "messages": clean, "images": counters["images"]}


def validate_consult(brief: str, images: list) -> dict:
    """Dossier d'une consultation d'Opus : texte borné, 2 photos au plus, aucun outil, consigne système fixée."""
    if not isinstance(brief, str) or not brief.strip() or len(brief) > MAX_BRIEF_CHARS:
        raise ChatRequestError("Dossier invalide ou trop long.")
    if not isinstance(images, list) or len(images) > MAX_CONSULT_IMAGES:
        raise ChatRequestError("Trop de photos jointes au dossier.")
    counters = {"text": 0, "images": 0, "b64": 0}
    content = [_clean_block(b, counters) for b in images] + [{"type": "text", "text": brief}]
    return {"model": OPUS, "system": CONSULT_SYSTEM, "tools": [], "messages": [{"role": "user", "content": content}],
            "images": counters["images"]}


def with_cache_breakpoints(system: str, messages: list) -> tuple:
    """Cache de prompt : un point d'arrêt sur la consigne système et un sur le DERNIER bloc de la conversation (les tours
    suivants relisent tout ce qui précède à 5 % du prix d'entrée)."""
    system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    out = [dict(m, content=list(m["content"])) for m in messages]
    last = out[-1]["content"]
    if last[-1]["type"] in ("text", "image", "tool_result"):
        last[-1] = dict(last[-1], cache_control={"type": "ephemeral"})
    return system_blocks, out


def _sse(event: dict) -> str:
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


def _usage_row(model: str, action: str, deal_id, images: int, usage, latency_ms: int, ok: bool, error_type=None) -> dict:
    fresh = getattr(usage, "input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return {"model": model, "action": action[:60], "deal_id": deal_id, "images": images,
            "input_tokens": fresh + read + write, "cached_tokens": read, "cache_write_tokens": write,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0, "thoughts_tokens": 0,
            "latency_ms": latency_ms, "ok": ok, "error_type": error_type}


def _client():
    import anthropic  # import tardif : l'API démarre même si le paquet manque (le chat Gemini n'en dépend pas)
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY n'est pas configurée sur le serveur.")
    return anthropic.AsyncAnthropic(api_key=key, timeout=CHAT_TIMEOUT_S)


async def _produce(queue: asyncio.Queue, pool, uid: str, deal_id: str, action: str, req: dict, max_tokens: int, effort: str,
                   use_cache: bool) -> None:
    """Appelle Claude et pousse les événements SSE dans `queue` ; enregistre l'usage (succès comme échec)."""
    started = time.monotonic()
    usage, ok, error_type = None, True, None
    try:
        client = _client()
        if use_cache:
            system, messages = with_cache_breakpoints(req["system"], req["messages"])
        else:
            system, messages = req["system"], req["messages"]
        args = dict(model=req["model"], max_tokens=max_tokens, system=system, messages=messages,
                    extra_body={"output_config": {"effort": effort}})
        if req["tools"]:
            args["tools"] = req["tools"]
        async with client.messages.stream(**args) as stream:
            async for text in stream.text_stream:
                await queue.put({"type": "text", "delta": text})
            final = await stream.get_final_message()
        usage = final.usage
        await queue.put({
            "type": "final", "stop_reason": final.stop_reason, "model": final.model,
            "content": [b.model_dump(mode="json", exclude_none=True) for b in final.content],
            "usage": {"input": getattr(usage, "input_tokens", 0) or 0,
                      "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
                      "cache_write": getattr(usage, "cache_creation_input_tokens", 0) or 0,
                      "output": getattr(usage, "output_tokens", 0) or 0}})
    except asyncio.CancelledError:
        ok, error_type = False, "cancelled"
        raise
    except Exception as e:
        ok = False
        status_code = getattr(e, "status_code", None)
        error_type = f"http_{status_code}" if status_code else type(e).__name__[:30]
        log.warning("[chat_claude] échec (%s) : %s", error_type, e)
        await queue.put({"type": "error", "status": status_code, "message": str(e)[:500]})
    finally:
        try:
            row = _usage_row(req["model"], action, deal_id, req["images"], usage, int((time.monotonic() - started) * 1000),
                             ok, error_type)
            await usage_repo.add_usage(pool, uid, row, provider="anthropic")
            today = await pool.fetchval("SELECT (now() AT TIME ZONE 'America/Toronto')::date::text")
            await cost_alert.maybe_alert(pool, today)
        except Exception as e:  # l'enregistrement ne doit jamais faire échouer la réponse
            log.warning("[chat_claude] enregistrement de l'usage impossible : %s", e)
        await queue.put(None)


async def event_stream(pool, uid: str, deal_id: str, action: str, req: dict, *, consult: bool = False):
    """Générateur SSE : événements `text` (deltas), un `final` (contenu complet, usage) ou un `error`, et des commentaires
    de maintien de connexion pendant les longues réflexions (le réseau coupe les connexions silencieuses, cf. llm_usage)."""
    queue: asyncio.Queue = asyncio.Queue()
    producer = asyncio.create_task(_produce(
        queue, pool, uid, deal_id, action, req,
        CONSULT_MAX_TOKENS if consult else CHAT_MAX_TOKENS, CONSULT_EFFORT if consult else CHAT_EFFORT, use_cache=not consult))
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_S)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if event is None:
                break
            yield _sse(event)
    finally:
        if not producer.done():
            producer.cancel()  # navigateur parti ou annulation : on arrête la génération (et la facturation)
