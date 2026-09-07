"""Contrat de perception (CHANTIER_B_PERCEPTION_RAISONNEMENT_PLAN.md §7, étape 10 / point "8.3").

Dérivé champ par champ du contrat JSON de production réel (`prompts.json`, schéma principal) —
pas du prompt d'extraction du candidat `hybrid` (`candidates.py::_EXTRACTION_PROMPT`), qui ne
couvrait que l'état physique général et le logo. Seuls les champs **purement perceptuels** du
schéma de prod sont couverts ici : `color`, `finish_application`, `finish_texture` (valeurs
fermées identiques à `prompts.json`), plus l'observation de l'état et la transcription logo/texte.
Les champs qui demandent une connaissance de lutherie (`brand`, `model_name`, `production_year`,
`country_of_origin`, `classification`, `neck_scale_length`) restent **hors de ce contrat** — ils
sont déduits par le raisonneur en aval à partir des observations brutes, jamais par la perception
elle-même. `visual_inspection` (champ mort, supprimé de `prompts.json`) n'a pas d'équivalent ici.

Garde-fou (§2, scope logo uniquement pour cette itération) : `logo_transcription` ne doit jamais
nommer ou interpréter une marque, seulement transcrire/décrire ce qui est lisible/visible — la
même règle que `candidates.py::_EXTRACTION_PROMPT`, mais appliquée à un contrat de sortie complet
plutôt qu'à un texte libre en deux parties. `unclear_or_hidden_areas` (champ de couverture,
absent de `hybrid`) permet au raisonneur de distinguer "non observable" de "non mentionné" plutôt
que de halluciner pour combler un vide — point explicitement soulevé lors de la consultation Opus
(passage 1, objection 8.3).

**Portée actuelle : outil de benchmark uniquement.** Ce module n'est PAS branché sur
`backend/analyzer.py` ni sur `prompts.json` de production — conformément à §7 étape 12 du plan,
l'implémentation en production n'a lieu qu'après un résultat favorable du benchmark sur l'axe
verrou (§0/§5). Utilisé ici uniquement par les candidats de benchmark
(`backend/benchmark/candidates.py::call_perception_reasoning_*`).
"""
import json

# Valeurs fermées identiques à prompts.json (schéma principal) — la perception doit choisir
# EXACTEMENT une de ces chaînes, jamais une variante, pour rester comparable au contrat de prod.
FINISH_APPLICATION_VALUES = ("Peinture opaque", "Vernis/Laque transparente", "Teinture", "Naturel/Brut", "Inconnue")
FINISH_TEXTURE_VALUES = ("Brillant", "Satiné/Soyeux", "Mat", "Inconnue")

# Valeurs neutres utilisées quand le modèle de perception ne renvoie pas un JSON exploitable —
# jamais une supposition, toujours un signal explicite d'échec de perception (cohérent avec le
# champ de couverture lui-même : mieux vaut "je ne sais pas" qu'une valeur inventée).
_FALLBACK_VALUES = {
    "color": "Inconnue",
    "finish_application": "Inconnue",
    "finish_texture": "Inconnue",
}

PERCEPTION_INSTRUCTION = (
    "Décris ce qui est visible sur ces photos d'un instrument de musique, sans répondre à "
    "aucune question et sans tirer aucune conclusion d'identification — un autre modèle "
    "utilisera ta description, seule (il ne verra jamais ces photos), pour identifier "
    "l'instrument et l'évaluer.\n\n"
    "Réponds UNIQUEMENT avec un objet JSON strict :\n"
    "{\n"
    "  \"visible_summary\": \"Description générale de ce qui est visible (type d'instrument, "
    "forme du corps/manche/tête, configuration de matériel visible — micros, cordes, "
    "mécaniques, chevalet — SANS nommer de marque ni de modèle).\",\n"
    "  \"logo_transcription\": \"Transcription EXACTE (lettre par lettre) de tout texte lisible "
    "(tête, corps, plaque, numéro de série), PLUS une description de la forme/police/couleurs de "
    "tout logo ou emblème visible — SANS jamais nommer ou déduire la marque associée. Réponds "
    "'Aucun texte/logo visible' si rien n'est lisible.\",\n"
    "  \"color\": \"Couleur générale dominante observée — UNIQUEMENT si au moins une photo "
    "montre l'instrument lui-même. Réponds 'Inconnue' sinon.\",\n"
    "  \"finish_application\": \"UNIQUEMENT une de ces valeurs exactes : 'Peinture opaque', "
    "'Vernis/Laque transparente', 'Teinture', 'Naturel/Brut', 'Inconnue'.\",\n"
    "  \"finish_texture\": \"UNIQUEMENT une de ces valeurs exactes : 'Brillant', "
    "'Satiné/Soyeux', 'Mat', 'Inconnue'.\",\n"
    "  \"condition_notes\": \"Liste factuelle des défauts/usure/dommages visibles (rayures, "
    "éclats, oxydation, jeu dans le manche, état des cordes/frettes, pièces manquantes ou "
    "remplacées) — décris ce que tu vois, ne conclus jamais un score ni un verdict.\",\n"
    "  \"unclear_or_hidden_areas\": \"Liste des zones qui ne sont PAS visibles ou pas assez "
    "nettes pour être décrites avec confiance (ex: 'tête hors cadre', 'logo illisible', 'dos non "
    "photographié') — pour que le modèle suivant sache ce qu'il ignore plutôt que de deviner.\"\n"
    "}\n\n"
    "Règle stricte sur logo_transcription : ne dis JAMAIS si une marque est \"connue\", "
    "\"budget\", \"artisanale\", \"OEM\" ou autre, et ne nomme jamais la marque elle-même — "
    "transcris et décris seulement ce que tu vois, l'identification revient entièrement à un "
    "autre modèle."
)

PERCEPTION_FIELDS = (
    "visible_summary", "logo_transcription", "color",
    "finish_application", "finish_texture", "condition_notes", "unclear_or_hidden_areas",
)


def parse_perception_json(raw_text: str) -> dict:
    """Parse la sortie JSON du modèle de perception. Filet de sécurité si le modèle ne respecte
    pas le format demandé : le texte brut devient `visible_summary` et le champ de couverture
    signale explicitement l'échec de structuration, plutôt que de faire échouer tout le candidat
    ou de deviner des valeurs pour les champs manquants."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text.strip())
    except json.JSONDecodeError:
        parsed = {}
        parsed["visible_summary"] = raw_text or ""
        parsed["unclear_or_hidden_areas"] = "Réponse non structurée du modèle de perception (JSON invalide)."

    result = {field: parsed.get(field, "") for field in PERCEPTION_FIELDS}
    for field, fallback in _FALLBACK_VALUES.items():
        if not result[field]:
            result[field] = fallback
    return result


def build_reasoning_prompt(question: str, perception: dict) -> str:
    """Construit le prompt du raisonneur à partir d'un rapport de perception déjà parsé
    (voir `parse_perception_json`). Le raisonneur ne voit jamais les photos — seulement ce
    texte — et doit dire explicitement quand une zone nécessaire n'a pas été décrite plutôt que
    de deviner (répond directement à l'objection Opus sur le champ de couverture, §7 8.3)."""
    return (
        "Un modèle de vision spécialisé a décrit ce qui est visible sur les photos d'une "
        "annonce (il n'a JAMAIS tenté d'identifier la marque, le modèle, ni conclu de score — "
        "c'est à toi de le faire à partir de ces observations brutes ; tu ne vois pas les "
        "photos toi-même) :\n\n"
        f"Description générale : {perception['visible_summary']}\n"
        f"Texte/logo transcrit : {perception['logo_transcription']}\n"
        f"Couleur observée : {perception['color']}\n"
        f"Type de finition : {perception['finish_application']}\n"
        f"Brillance : {perception['finish_texture']}\n"
        f"État observé : {perception['condition_notes']}\n"
        f"Zones non visibles ou peu claires : {perception['unclear_or_hidden_areas']}\n\n"
        f"Question : {question}\n\n"
        "En te basant sur tes propres connaissances des marques/luthiers/lutherie, identifie "
        "la marque, le modèle et l'origine probable de l'instrument à partir du texte/logo "
        "transcrit, puis réponds à la question en combinant cette identification avec l'état "
        "observé. Si une zone nécessaire à ta réponse n'a pas été décrite (voir 'zones non "
        "visibles'), dis-le explicitement plutôt que de deviner."
    )
