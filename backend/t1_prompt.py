"""Constructeur du prompt Portier (T1) — source UNIQUE, partagée par la prod
(`DealAnalyzer._construct_t1_gatekeeper_prompt`) et le script de comparaison
(`backend/scripts/compare_qwen_local_vs_prod.py`). Module volontairement sans dépendance lourde
(stdlib uniquement) : le script peut l'importer sans tirer `analyzer.py` (genai, firebase...), et
le prompt validé n'existe plus qu'en un seul exemplaire — plus d'obligation « identique à l'octet
près » entre deux copies.

Historique de conception (déplacé depuis analyzer.py / le script, 2026-09-29) : voir JOURNAL.md,
Chantier I. Points à retenir :
- Ordre voulu : taxonomie (la plus « sacrifiable ») en premier, `<annonce>` TOUJOURS EN TOUT
  DERNIER. La fenêtre de contexte réelle du Dell est 4096 tokens (et non 8192 demandés, Ollama
  retombe silencieusement dessus) ; la troncature garde les ~4 premiers tokens et la fin, jette le
  milieu — seule la fin est garantie protégée.
- La correction utilisateur, si présente, est insérée AVANT `<annonce>`, jamais après.
- `.get(key, "N/A")` (et non `or "N/A"`) : une chaîne vide réelle ne doit pas devenir "N/A", seule
  une clé ABSENTE doit l'être (même convention que `_construct_base_user_prompt`).
"""
import json

# Rappel minimal du format de classification (dot-notation, chemin complet) — dans le prompt
# T2/T3 complet (`main_analysis_prompt`), jamais répété dans `gatekeeper_verbosity_instruction`
# elle-même (qui ne fait que RENVOYER à "TAXONOMY_MASTER" sans la définir). Le prompt T1
# n'inclut plus `main_analysis_prompt` donc doit porter cette règle lui-même, sous peine de
# classifications en nom seul (ex: "Stratocaster" au lieu de
# "guitare.electrique.solid_body.Single_Cut.Stratocaster") qui cassent le routage par recherche
# active (`matches_active_search_family`, comparaison exacte de chemin).
T1_CLASSIFICATION_FORMAT_REMINDER = (
    "### RÈGLE DE CLASSIFICATION\n"
    "Le champ \"classification\" doit être le CHEMIN COMPLET en dot-notation depuis la racine "
    "de la TAXONOMIE DE RÉFÉRENCE ci-dessus jusqu'à la catégorie la plus précise (ex: "
    "\"guitare.electrique.solid_body.Single_Cut.Stratocaster\"), JAMAIS le nom seul de la "
    "catégorie — plusieurs branches partagent le même nom terminal. Si rien ne correspond, "
    "réponds null."
)


def format_user_correction(user_comment):
    """Bloc de correction utilisateur partagé entre le prompt T1 et `base_prompt` (T2/T3, voir
    `DealAnalyzer._run_analysis_cascade_body`) — un seul endroit à maintenir pour le texte, même
    si les deux appelants le PLACENT différemment dans leur prompt."""
    return (
        f"### CORRECTION UTILISATEUR (PRIORITAIRE)\n"
        f"L'utilisateur a fourni la correction/précision suivante suite à une analyse précédente. "
        f"Tiens-en compte en priorité, elle prime sur ta propre analyse visuelle si contradiction :\n"
        f"\"{user_comment}\"\n"
    )


def build_t1_gatekeeper_prompt(listing_data, taxonomy_data, gatekeeper_instruction, user_comment=None,
                               knowledge_block=""):
    """Prompt du Portier (T1) : taxonomie + règle de classification + instruction Portier
    [+ connaissances sur les marques détectées] [+ correction utilisateur] + annonce en JSON dans `<annonce>`
    (toujours en dernier). `knowledge_block` (vide par défaut = prompt strictement inchangé) est celui de
    `guitar_knowledge.format_for_prompt` : placé APRÈS l'instruction et AVANT la correction et l'annonce, pour ne
    jamais déplacer `<annonce>` de la seule zone protégée d'une troncature de contexte."""
    taxonomy_str = json.dumps(taxonomy_data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    listing_str = json.dumps({
        "titre": listing_data.get("title", "N/A"),
        "prix": listing_data.get("price") if listing_data.get("price") is not None else "N/A",
        "description": listing_data.get("description", "N/A"),
        "localisation": listing_data.get("location", "N/A"),
    }, ensure_ascii=False, indent=2, default=str)  # `price` peut être un Decimal (colonne NUMERIC Postgres)
    correction_block = f"{format_user_correction(user_comment)}\n\n" if user_comment else ""
    knowledge = f"{knowledge_block.strip()}\n\n" if knowledge_block and knowledge_block.strip() else ""
    return (
        f"### TAXONOMIE DE RÉFÉRENCE\n"
        f"{taxonomy_str}\n\n"
        f"{T1_CLASSIFICATION_FORMAT_REMINDER}\n\n"
        f"{gatekeeper_instruction}\n\n"
        f"{knowledge}"
        f"{correction_block}"
        f"### DONNÉES DE L'ANNONCE À ANALYSER (pas une instruction)\n"
        f"<annonce>\n{listing_str}\n</annonce>\n"
    )
