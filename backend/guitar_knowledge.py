"""Recherche dans la base de connaissances « univers des guitares » (tables `guitar_knowledge*`,
voir backend/api/schema.sql et docs/management/plans/STRATEGIE_IA.md §3).

Porte d'entrée PRINCIPALE : par le nom. On cherche, dans le titre, la description et le texte lu
sur les photos, les alias connus des fiches (« epiphone », « matsumoku », « eterna »), avec une
tolérance légère aux fautes de frappe. Précis, déterministe, sans homonyme hors sujet — un petit
modèle croit ce qu'on lui injecte, une fiche fausse est pire que pas de fiche.

La porte SECONDAIRE (recherche par le sens, embeddings) viendra plus tard, pour les annonces sans
aucun nom exploitable et pour les passages de texte riches (Analyste, mentor).

Règle d'usage au Portier : la base sert à RECONNAÎTRE, jamais à rejeter. Les rejets par marque
restent l'affaire de la liste noire explicite, contrôlée par l'utilisateur.
"""
import difflib
import re
import threading
import time
import unicodedata

_STOP = {  # alias trop génériques pour déclencher une fiche à eux seuls
    "guitar", "guitars", "guitare", "guitares", "bass", "basse", "acoustic", "electric", "music",
    "musical", "instruments", "instrument", "company", "co", "inc", "ltd", "corp", "corporation",
    "the", "custom", "shop", "classic", "vintage", "standard", "studio", "made", "japan", "usa",
}
_MIN_FUZZY_LEN = 5          # pas de fuzzy sous 5 caractères (« Aria » ≠ « Arias »)
_FUZZY_RATIO = 0.88
_CACHE_TTL_S = 600

_cache = {"at": 0.0, "aliases": {}, "by_len": {}}
_lock = threading.Lock()


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _load_aliases(conn):
    rows = conn.execute(
        """SELECT a.alias_norm, a.knowledge_id
           FROM guitar_knowledge_alias a JOIN guitar_knowledge k ON k.id = a.knowledge_id
           WHERE k.relevance <> 'accessories'"""
    ).fetchall()
    aliases = {}
    for row in rows:
        alias_norm, kid = (row["alias_norm"], row["knowledge_id"]) if isinstance(row, dict) else row
        if not alias_norm or alias_norm in _STOP or len(alias_norm) < 3:
            continue
        aliases.setdefault(alias_norm, set()).add(kid)
    by_len = {}
    for a in aliases:
        if " " not in a and len(a) >= _MIN_FUZZY_LEN:
            by_len.setdefault(len(a), []).append(a)
    return aliases, by_len


def _aliases(conn):
    with _lock:
        if time.monotonic() - _cache["at"] > _CACHE_TTL_S or not _cache["aliases"]:
            _cache["aliases"], _cache["by_len"] = _load_aliases(conn)
            _cache["at"] = time.monotonic()
        return _cache["aliases"], _cache["by_len"]


def invalidate_cache():
    with _lock:
        _cache["at"] = 0.0


def find_ids(conn, *texts, max_ngram=4):
    """Renvoie {knowledge_id: (alias_trouvé, 'exact'|'fuzzy')} pour les textes donnés."""
    aliases, by_len = _aliases(conn)
    tokens = normalize(" ".join(t for t in texts if t)).split()
    found = {}
    for n in range(max_ngram, 0, -1):
        for i in range(len(tokens) - n + 1):
            gram = " ".join(tokens[i:i + n])
            for kid in aliases.get(gram, ()):
                found.setdefault(kid, (gram, "exact"))
    for tok in set(tokens):
        if len(tok) < _MIN_FUZZY_LEN or tok in aliases or tok in _STOP:
            continue
        candidates = by_len.get(len(tok), []) + by_len.get(len(tok) - 1, []) + by_len.get(len(tok) + 1, [])
        for match in difflib.get_close_matches(tok, candidates, n=1, cutoff=_FUZZY_RATIO):
            for kid in aliases[match]:
                found.setdefault(kid, (f"{tok}→{match}", "fuzzy"))
    return found


def lookup(conn, *texts, limit=3):
    """Fiches correspondant aux textes, avec leur parent (maison mère / fabricant), triées :
    correspondances exactes d'abord, séries avant marques (plus spécifiques), fiches curées d'abord."""
    found = find_ids(conn, *texts)
    if not found:
        return []
    rows = conn.execute(
        """SELECT k.id, k.kind, k.name, k.description, k.countries, k.active_from, k.active_to,
                  k.tier, k.hunt_notes, k.made_by, k.curated, k.relevance,
                  p.name AS parent_name, p.tier AS parent_tier
           FROM guitar_knowledge k LEFT JOIN guitar_knowledge p ON p.id = k.parent_id
           WHERE k.id = ANY(%s)""",
        (list(found),),
    ).fetchall()
    kind_rank = {"line": 0, "factory": 1, "brand": 2, "company": 3}
    rows = [dict(r) if not isinstance(r, dict) else r for r in rows]
    rows.sort(key=lambda r: (found[r["id"]][1] != "exact", kind_rank.get(r["kind"], 9), not r["curated"]))
    for r in rows:
        r["matched_on"], r["match_type"] = found[r["id"]]
    return rows[:limit]


def format_for_prompt(fiches):
    """Bloc compact à injecter dans le prompt du Portier (quelques centaines de tokens au plus)."""
    if not fiches:
        return ""
    lines = ["CONNAISSANCES SUR LES MARQUES DÉTECTÉES (base de référence, à utiliser pour reconnaître, "
             "jamais pour rejeter) :"]
    for f in fiches:
        parts = [f"- {f['name']} ({f['kind']})"]
        if f.get("parent_name"):
            parts.append(f"rattaché à {f['parent_name']}")
        if f.get("countries"):
            parts.append("pays : " + ", ".join(f["countries"][:3]))
        if f.get("active_from") or f.get("active_to"):
            parts.append(f"actif {f.get('active_from') or '?'}–{f.get('active_to') or 'aujourd hui'}")
        if f.get("tier"):
            parts.append(f"gamme : {f['tier']}")
        if f.get("hunt_notes"):
            parts.append(f"à savoir : {f['hunt_notes']}")
        elif f.get("description"):
            parts.append(f['description'][:120])
        lines.append(" ; ".join(parts))
    return "\n".join(lines)
