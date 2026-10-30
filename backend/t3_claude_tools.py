"""Outil `lookup_brand` et consignes propres à l'Expert Claude (Tier 3), actifs seulement si
`T3_PROVIDER="claude"` ET `T3_KNOWLEDGE_ENABLED=true` (éteint par défaut). Voir `JOURNAL.md` 2026-10-14.

Pourquoi un outil et pas une injection : la base ne trouvait rien quand la marque n'était pas dans le titre. Ici le
modèle LIT d'abord la tête de manche ou l'étiquette, puis interroge la base avec ce qu'il a lu.
"""
from backend import guitar_knowledge

MAX_QUERY_CHARS = 120
MAX_CALLS_PER_ANALYSIS = 4

LOOKUP_BRAND_TOOL = {
    "name": "lookup_brand",
    "description": (
        "Cherche une marque, une série ou une usine de guitares dans la base de référence. À appeler avec le nom TEL QUE "
        "LU sur les photos (tête de manche, logo, étiquette intérieure) ou dans l'annonce, même mal orthographié, "
        "une requête par nom. Renvoie des fiches avec le type de correspondance (exact, fuzzy, partiel), un score et "
        "l'indication « vérifiée » ou « NON VÉRIFIÉE ». Aucune fiche ne veut PAS dire marque de faible valeur."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Nom de marque, série ou usine, tel que lu."}},
        "required": ["query"],
    },
}

# Ajouté à la FIN du prompt T3 (après l'annonce) : la partie statique avant le marqueur reste celle qui est mise en cache.
CLAUDE_T3_ADDENDUM = """

CONSIGNES SUPPLÉMENTAIRES — LECTURE DES PHOTOS ET MARQUES :
1. Avant toute estimation, lis tout le texte visible sur les photos : tête de manche, logo, étiquette intérieure, plaque, numéro de série, tampon. Recopie-le dans `visual_inspection` en indiquant la photo. Si tu hésites, écris « lu avec doute : … » ou « illisible » plutôt que d'inventer ; n'affirme jamais un élément que tu ne vois pas nettement.
2. Dès qu'une marque, une série ou un modèle est lisible ou plausible — même absent du titre —, appelle l'outil `lookup_brand` avec le nom tel que lu (une requête par nom, trois au plus).
3. Une fiche « NON VÉRIFIÉE » est un indice, jamais un fait établi.
4. Marque absente de la base ≠ faible valeur. Si la marque est inconnue ou sans fiche : donne une fourchette de valeur LARGE, une confiance basse et écris « marque à vérifier » dans le résumé ; ne baisse pas ton estimation parce que tu ne connais pas la marque.
"""


def make_brand_tool(logger, trace):
    """Gestionnaire d'outil lié à une analyse. `trace` (liste) reçoit chaque requête et ses fiches, pour que le rejeu et
    l'audit voient ce que le modèle a demandé. Ne lève jamais vers le modèle : une base indisponible est un message."""
    calls = {"n": 0}

    def handler(name, arguments):
        if name != "lookup_brand":
            return f"Outil inconnu : {name}"
        query = str((arguments or {}).get("query", "")).strip()[:MAX_QUERY_CHARS]
        if not query:
            return "Requête vide : indique un nom de marque."
        calls["n"] += 1
        if calls["n"] > MAX_CALLS_PER_ANALYSIS:
            return "Limite de requêtes atteinte pour cette annonce : conclus avec ce que tu as."
        from backend import pg_db
        with pg_db.get_pool().connection(timeout=2.0) as conn:
            results = guitar_knowledge.search_brand(conn, query)
        trace.append({"query": query,
                      "fiches": [{"id": r["id"], "match": r["match_type"], "score": r["score"],
                                  "verified": not r["unverified_reasons"]} for r in results]})
        logger.info(f"   🔎 lookup_brand « {query} » → {len(results)} fiche(s)")
        return guitar_knowledge.format_brand_results(query, results)

    return handler
