"""Enregistrement best-effort de l'usage LLM dans Postgres (`llm_usage`, voir backend/api/schema.sql)
— Chantier C-0.

Règles :
- Ne lève JAMAIS : une panne Postgres ne doit ni bloquer ni ralentir une analyse. Échec → une
  ligne WARNING au plus toutes les 10 minutes, puis silence.
- Contexte d'annonce (`deal_id`, `user_ref`) porté par des ContextVar, posées une fois par
  `analyzer.analyze_deal*()`, plutôt que passées en paramètre à chaque appel. ATTENTION : un
  `threading.Thread` ne copie PAS le contexte — lancer les threads avec
  `contextvars.copy_context().run` (fait pour l'observation miroir T1).
- Hors du bot (scripts lancés sans `init_pool()`), tente d'initialiser le pool une fois ; si la
  base est injoignable, désactive silencieusement l'enregistrement pour le reste du processus.
"""
import contextvars
import logging
import time

current_deal_id = contextvars.ContextVar("llm_usage_deal_id", default=None)
current_user_ref = contextvars.ContextVar("llm_usage_user_ref", default=None)

_logger = logging.getLogger("llm_usage")
_disabled = False
_last_warning = 0.0

_INSERT = """
INSERT INTO llm_usage (source, provider, model, action, deal_id, user_ref, images,
                       input_tokens, cached_tokens, output_tokens, thoughts_tokens, latency_ms, ok)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


# Délais courts : un enregistrement d'usage ne doit JAMAIS ralentir une analyse. Sans eux, une base
# injoignable bloquait 30 s (délai par défaut de psycopg_pool) à chaque appel — mesuré en test.
_CONNECT_TIMEOUT_S = 2
_POOL_WAIT_S = 1.0


def _pool():
    global _disabled
    from backend import pg_db
    try:
        return pg_db.get_pool()
    except RuntimeError:
        # Hors bot (script lancé sans init_pool) : vérifier vite que la base répond avant de
        # créer un pool, sinon désactiver pour tout le processus.
        try:
            import psycopg
            psycopg.connect(pg_db.DATABASE_URL, connect_timeout=_CONNECT_TIMEOUT_S).close()
            return pg_db.init_pool()
        except Exception:
            _disabled = True
            return None


def record(*, provider, model, action, images=0, input_tokens=0, cached_tokens=0,
           output_tokens=0, thoughts_tokens=0, latency_ms=None, ok=True,
           deal_id=None, user_ref=None, source="backend"):
    global _last_warning
    if _disabled:
        return
    try:
        pool = _pool()
        if pool is None:
            return
        with pool.connection(timeout=_POOL_WAIT_S) as conn:
            conn.execute(_INSERT, (
                source, provider, model, action or "unknown",
                deal_id if deal_id is not None else current_deal_id.get(),
                user_ref if user_ref is not None else current_user_ref.get(),
                int(images or 0), int(input_tokens or 0), int(cached_tokens or 0),
                int(output_tokens or 0), int(thoughts_tokens or 0),
                int(latency_ms) if latency_ms is not None else None, bool(ok),
            ))
    except Exception as e:  # jamais bloquant
        now = time.monotonic()
        if now - _last_warning > 600:
            _last_warning = now
            _logger.warning(f"[llm_usage] enregistrement impossible (ignoré) : {e}")
