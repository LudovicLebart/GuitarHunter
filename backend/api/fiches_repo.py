"""Accès SQL aux fiches techniques de restauration (`guitar_knowledge` kind 'fiche' + tables satellites).

Les fiches vivent dans la base COMMUNE avec les marques (voir backend/guitar_knowledge.py et schema.sql) : ce module
ne duplique rien de la recherche par alias — il charge l'index des alias de fiches avec asyncpg et réutilise les
fonctions PURES de `guitar_knowledge` (`build_alias_index`, `match_alias_index`, `valid_fiche_slug`), donc les mêmes règles
que le chargeur et que la recherche synchrone. Seul le type `fiche` est lu ici (liste blanche `FICHE_KINDS`) : une
marque n'est jamais renvoyée par ces fonctions.

Statut et confiance : TOUTES les fiches sont servies, brouillons compris (décision produit : le chat et le site citent
n'importe quelle fiche avec son statut visible). Chaque réponse porte donc `statut` et `confidence`, que le client
affiche (bandeau « brouillon », niveau de confiance) ; rien n'est caché ici.

Les fiches sont chargées par `backend/scripts/seed_guitar_fiches.py` (commande manuelle) ; ce module est en lecture seule.
"""
import time

import asyncpg

from backend import guitar_knowledge as gk

valid_slug = gk.valid_fiche_slug

# L'index des alias est revérifié au plus toutes les `_STAMP_CHECK_S` secondes par une requête d'empreinte (nombre de
# fiches, dernière modification, nombre d'alias) : un chargement ou un retrait fait par le script est vu en quelques
# secondes, sans reconstruire l'index tant que rien n'a changé. Pas de verrou : deux reconstructions concurrentes
# écrivent le même résultat, et elles n'arrivent qu'au moment d'un vrai changement.
_STAMP_CHECK_S = 30
_index = {"at": None, "stamp": None, "aliases": {}, "by_len": {}}
_STAMP_SQL = """
    SELECT (SELECT count(*) FROM guitar_knowledge WHERE kind = ANY($1)) AS fiches,
           (SELECT max(updated_at) FROM guitar_knowledge WHERE kind = ANY($1)) AS modifiee,
           (SELECT count(*) FROM guitar_knowledge_alias a JOIN guitar_knowledge k ON k.id = a.knowledge_id
             WHERE k.kind = ANY($1)) AS alias"""

MAX_CANDIDATES = 50      # fiches examinées avant de couper à `limit` (les identifiants périmés sont écartés ensuite)


def _meta_sql(with_body: bool = False, with_aliases: bool = False) -> str:
    # `aliases` : les expressions qui retrouvent la fiche (texte d'origine) ; le catalogue du client s'en sert pour chercher une fiche.
    aliases = (", ARRAY(SELECT a.alias FROM guitar_knowledge_alias a WHERE a.knowledge_id = k.id ORDER BY a.alias) AS aliases"
               if with_aliases else "")
    return f"""
    SELECT k.id, k.name AS titre, k.description AS resume, k.confidence,
           f.categorie, f.difficulte, f.duree, f.statut, f.revision{', f.body_md' if with_body else ''}{aliases}
    FROM guitar_knowledge k JOIN guitar_knowledge_fiche f ON f.knowledge_id = k.id
    WHERE k.kind = ANY($1)"""


def _meta(row) -> dict:
    d = dict(row)
    d["slug"] = gk.fiche_slug(d.pop("id"))
    return d


def invalidate_cache() -> None:
    _index["at"] = None
    _index["stamp"] = None


async def list_fiches(pool: asyncpg.Pool, categorie: str | None = None) -> list[dict]:
    sql, params = _meta_sql(with_aliases=True), [list(gk.FICHE_KINDS)]
    if categorie:
        sql += " AND f.categorie = $2"
        params.append(categorie)
    return [_meta(r) for r in await pool.fetch(sql + " ORDER BY f.categorie, k.name", *params)]


async def get_fiche(pool: asyncpg.Pool, slug: str) -> dict | None:
    """Fiche complète (métadonnées, corps Markdown, sources) ou None. Les trois lectures partagent
    UN instantané (transaction à lecture répétable) : un chargement qui réécrit la fiche entre-temps ne peut pas
    renvoyer des métadonnées d'une version, un corps et des sources d'une autre."""
    if not valid_slug(slug):
        return None
    kid = gk.fiche_id(slug)
    async with pool.acquire() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            row = await conn.fetchrow(_meta_sql(with_body=True) + " AND k.id = $2", list(gk.FICHE_KINDS), kid)
            if row is None:
                return None
            sources = await conn.fetch(
                """SELECT url, kind, title, publisher, lang, license, excerpt FROM guitar_knowledge_source
                   WHERE knowledge_id = $1 ORDER BY (origin = 'manual') DESC, publisher, url""", kid)
    fiche = _meta(row)
    fiche["sources"] = [dict(r) for r in sources]
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
    now = time.monotonic()
    if _index["at"] is not None and now - _index["at"] <= _STAMP_CHECK_S:
        return _index["aliases"], _index["by_len"]
    stamp = tuple(await pool.fetchrow(_STAMP_SQL, list(gk.FICHE_KINDS)))
    if _index["stamp"] == stamp:
        _index["at"] = now
        return _index["aliases"], _index["by_len"]
    rows = await pool.fetch(
        """SELECT a.alias_norm, a.knowledge_id, k.kind FROM guitar_knowledge_alias a
           JOIN guitar_knowledge k ON k.id = a.knowledge_id WHERE k.kind = ANY($1)""", list(gk.FICHE_KINDS))
    aliases, by_len = gk.build_alias_index(rows)      # lignes lues par nom : l'ordre des colonnes n'a pas d'effet
    _index.update(at=now, stamp=stamp, aliases=aliases, by_len=by_len)
    return aliases, by_len


async def match_texts(pool: asyncpg.Pool, texts) -> list[tuple[str, str]]:
    """[(slug, alias trouvé)] pour les fiches dont un alias figure dans `texts`, les plus spécifiques d'abord (alias le plus
    long), à égalité par slug. Correspondance exacte seulement (pas de recherche floue pour les fiches). Deux fiches qui
    partagent un alias sont toutes deux renvoyées : contrairement aux marques, il n'y a pas de « propriétaire d'un nom »."""
    aliases, by_len = await _alias_index(pool)
    found = gk.match_alias_index(aliases, by_len, texts, gk.FICHE_KINDS)
    pairs = [(gk.fiche_slug(kid), alias) for kid, (alias, _kind) in found.items()]
    return sorted(pairs, key=lambda p: (-len(p[1]), p[0]))


async def deal_text(pool: asyncpg.Pool, deal_id: str) -> list[str]:
    """Titre et description de l'annonce (textes dans lesquels chercher des alias)."""
    row = await pool.fetchrow("SELECT title, description FROM guitar_deals WHERE id = $1", deal_id)
    return [(row["title"] or ""), (row["description"] or "")] if row else []


async def fiches_for_deal(pool: asyncpg.Pool, *, q: str | None = None, step_slugs=(), step_labels=(), deal_texts=(),
                          limit: int = 5) -> list[dict]:
    """Fiches utiles pour une annonce, classées par pertinence décroissante :
    1. `question` : un alias figure dans la question en cours (`q`) — ce que la personne demande MAINTENANT ;
    2. `etape`    : fiche liée explicitement à une étape du plan (`step_slugs`, ordre du plan) ;
    3. `plan`     : un alias figure dans le libellé d'une étape ;
    4. `annonce`  : un alias figure dans le titre ou la description de l'annonce.
    Dans chaque groupe, l'alias le plus long (le plus spécifique) passe d'abord. Les fiches sont examinées (jusqu'à
    `MAX_CANDIDATES`) puis réduites à celles qui EXISTENT encore AVANT de couper à `limit` : un slug de fiche retirée
    (étape restée liée, index d'alias pas encore rafraîchi) ne prend jamais la place d'une fiche valide.
    Chaque résultat porte `reason` et `matchedOn` (alias, None pour `etape`). Les liens marque → fiche ne sont pas
    consultés ici (à brancher avec la reconnaissance de marque)."""
    candidates: dict[str, tuple[str, str | None]] = {}
    if q:
        for slug, alias in await match_texts(pool, [q]):
            candidates.setdefault(slug, ("question", alias))
    for slug in step_slugs:
        if valid_slug(slug):
            candidates.setdefault(slug, ("etape", None))
    if step_labels:
        for slug, alias in await match_texts(pool, list(step_labels)):
            candidates.setdefault(slug, ("plan", alias))
    if deal_texts:
        for slug, alias in await match_texts(pool, list(deal_texts)):
            candidates.setdefault(slug, ("annonce", alias))
    ordered = list(candidates)[:MAX_CANDIDATES]
    if not ordered:
        return []
    rows = await pool.fetch(_meta_sql() + " AND k.id = ANY($2)", list(gk.FICHE_KINDS), [gk.fiche_id(s) for s in ordered])
    metas = {m["slug"]: m for m in map(_meta, rows)}
    results = [{**metas[s], "reason": candidates[s][0], "matchedOn": candidates[s][1]} for s in ordered if s in metas]
    return results[:max(1, limit)]
