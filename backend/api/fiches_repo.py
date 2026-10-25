"""Accès SQL aux fiches techniques de restauration (`guitar_knowledge` kind 'fiche' + tables satellites).

Les fiches vivent dans la base COMMUNE avec les marques (voir backend/guitar_knowledge.py et schema.sql) : ce module
ne duplique rien de la recherche par alias — il charge l'index des alias de fiches avec asyncpg et réutilise les
fonctions PURES de `guitar_knowledge` (`build_alias_index`, `match_aliases`), donc les mêmes règles d'alias que le
chargeur et que la recherche synchrone. Seul le type `fiche` est lu ici (liste blanche `FICHE_KINDS`) : une marque
n'est jamais renvoyée par ces fonctions.

Les fiches sont chargées par `backend/scripts/seed_guitar_fiches.py` (commande manuelle) ; ce module est en lecture seule.
"""
import re
import time

import asyncpg

from backend import guitar_knowledge as gk

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")

_ALIAS_TTL_S = 600
# Index des alias de fiches en mémoire (même durée de vie que celui des marques). Deux requêtes concurrentes qui
# rechargent en même temps écrivent le même résultat : sans conséquence, donc pas de verrou.
_index = {"at": None, "aliases": {}, "by_len": {}}

_META_SQL = """
    SELECT k.id, k.name AS titre, k.description AS resume, k.confidence,
           f.categorie, f.difficulte, f.duree, f.statut, f.revision
    FROM guitar_knowledge k JOIN guitar_knowledge_fiche f ON f.knowledge_id = k.id
    WHERE k.kind = ANY($1)"""


def _meta(row) -> dict:
    d = dict(row)
    d["slug"] = gk.fiche_slug(d.pop("id"))
    return d


def valid_slug(slug) -> bool:
    return isinstance(slug, str) and bool(SLUG_RE.match(slug))


def invalidate_cache() -> None:
    _index["at"] = None


async def list_fiches(pool: asyncpg.Pool, categorie: str | None = None) -> list[dict]:
    sql, params = _META_SQL, [list(gk.FICHE_KINDS)]
    if categorie:
        sql += " AND f.categorie = $2"
        params.append(categorie)
    rows = await pool.fetch(sql + " ORDER BY f.categorie, k.name", *params)
    return [_meta(r) for r in rows]


async def get_fiche(pool: asyncpg.Pool, slug: str) -> dict | None:
    """Fiche complète (métadonnées, corps Markdown, sources, marques concernées) ou None."""
    if not valid_slug(slug):
        return None
    kid = gk.fiche_id(slug)
    row = await pool.fetchrow(_META_SQL + " AND k.id = $2", list(gk.FICHE_KINDS), kid)
    if row is None:
        return None
    fiche = _meta(row)
    fiche["body_md"] = await pool.fetchval("SELECT body_md FROM guitar_knowledge_fiche WHERE knowledge_id = $1", kid)
    fiche["sources"] = [dict(r) for r in await pool.fetch(
        """SELECT url, kind, title, publisher, lang, license, excerpt FROM guitar_knowledge_source
           WHERE knowledge_id = $1 ORDER BY (origin = 'manual') DESC, publisher, url""", kid)]
    fiche["concerne"] = [dict(r) for r in await pool.fetch(
        """SELECT b.id, b.name, b.kind FROM guitar_knowledge_link l JOIN guitar_knowledge b ON b.id = l.from_id
           WHERE l.to_id = $1 AND l.rel = 'fiche_pour' ORDER BY b.name""", kid)]
    return fiche


async def existing_slugs(pool: asyncpg.Pool, slugs) -> set[str]:
    """Parmi `slugs`, ceux qui sont des fiches existantes."""
    wanted = [gk.fiche_id(s) for s in set(slugs) if valid_slug(s)]
    if not wanted:
        return set()
    rows = await pool.fetch("SELECT id FROM guitar_knowledge WHERE id = ANY($1) AND kind = ANY($2)",
                            wanted, list(gk.FICHE_KINDS))
    return {gk.fiche_slug(r["id"]) for r in rows}


async def _alias_index(pool: asyncpg.Pool):
    if _index["at"] is not None and time.monotonic() - _index["at"] <= _ALIAS_TTL_S:
        return _index["aliases"], _index["by_len"]
    rows = await pool.fetch(
        """SELECT a.alias_norm, a.knowledge_id, k.kind FROM guitar_knowledge_alias a
           JOIN guitar_knowledge k ON k.id = a.knowledge_id WHERE k.kind = ANY($1)""", list(gk.FICHE_KINDS))
    aliases, by_len = gk.build_alias_index(rows)
    _index.update(at=time.monotonic(), aliases=aliases, by_len=by_len)
    return aliases, by_len


async def match_texts(pool: asyncpg.Pool, texts) -> dict[str, str]:
    """{slug: alias trouvé} pour les fiches dont un alias figure dans `texts`. Correspondance exacte seulement
    (pas de recherche floue pour les fiches, voir `guitar_knowledge.match_aliases`)."""
    aliases, by_len = await _alias_index(pool)
    found = gk.match_aliases(aliases, by_len, texts, gk.FICHE_KINDS)
    return {gk.fiche_slug(kid): alias for kid, (alias, _kind) in found.items()}


async def fiches_for_deal(pool: asyncpg.Pool, deal_id: str, *, step_slugs=(), step_labels=(), q: str | None = None,
                          limit: int = 5) -> list[dict]:
    """Fiches utiles pour une annonce : d'abord celles liées explicitement à une étape du plan de restauration
    (`step_slugs`, ordre du plan), puis celles dont un alias figure dans le texte (question `q`, libellés d'étapes,
    titre et description de l'annonce). Chaque fiche porte `reason` ('etape' | 'texte') et `matchedOn` (alias).
    Les marques ne sont pas consultées ici (liens marque → fiche : à brancher avec la reconnaissance de marque)."""
    deal = await pool.fetchrow("SELECT title, description FROM guitar_deals WHERE id = $1", deal_id)
    texts = [q or "", *step_labels, (deal["title"] if deal else "") or "", (deal["description"] if deal else "") or ""]
    reasons: dict[str, tuple[str, str | None]] = {}
    for slug in await _keep_existing(pool, step_slugs):
        reasons.setdefault(slug, ("etape", None))
    for slug, alias in (await match_texts(pool, texts)).items():
        reasons.setdefault(slug, ("texte", alias))
    ordered = list(reasons)[:max(1, limit)]
    if not ordered:
        return []
    by_slug = {m["slug"]: m for m in await _metas(pool, ordered)}
    return [{**by_slug[s], "reason": reasons[s][0], "matchedOn": reasons[s][1]} for s in ordered if s in by_slug]


async def _keep_existing(pool, slugs) -> list[str]:
    """`slugs` sans doublon, dans l'ordre, réduits aux fiches qui existent encore (un slug de fiche retirée est ignoré)."""
    ordered = list(dict.fromkeys(s for s in slugs if valid_slug(s)))
    known = await existing_slugs(pool, ordered)
    return [s for s in ordered if s in known]


async def _metas(pool, slugs) -> list[dict]:
    rows = await pool.fetch(_META_SQL + " AND k.id = ANY($2)", list(gk.FICHE_KINDS), [gk.fiche_id(s) for s in slugs])
    return [_meta(r) for r in rows]
