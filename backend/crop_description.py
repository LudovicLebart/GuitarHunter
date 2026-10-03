"""Contrat de description d'un crop (STRATEGIE_IA.md §4.3) — « les yeux » locaux de la cascade.

Qwen local décrit chaque crop (ou photo entière) **sans interpréter** : il transcrit ce qui est écrit et décrit ce
qui est visible, il ne déduit jamais une marque ou un modèle (c'est le rôle de l'Analyste). Sortie : un JSON strict,
à vocabulaire fermé, que les modèles texte exploitent ensuite sans revoir l'image.

Ce module ne contient que le contrat (schéma, prompt, validation) ; aucun appel modèle. Il n'est branché nulle part
en production : les crops n'existent qu'après l'entraînement du détecteur de parties
(PARTS_DETECTOR_AND_CROPS_PLAN.md). Les parties reprennent la taxonomie du détecteur (`CLASS_NAMES`).
"""
from backend.auto_annotation.config import CLASS_NAMES

# Vue d'ensemble de la photo ou nature du crop. Les parties du détecteur + les cadrages d'ensemble.
VUES = ["entiere_face", "entiere_dos", "entiere_profil", *CLASS_NAMES, "detail", "autre"]
QUALITES = ["nette", "floue", "sombre", "surexposee", "partielle"]
CONFIANCES = ["haute", "moyenne", "basse"]
GRAVITES = ["aucune", "legere", "moyenne", "grave"]
FINITIONS = ["vernie_brillante", "satinee", "vieillie", "naturelle", "peinte", "usee", "inconnue"]
# Zones d'état et éléments non visibles : mêmes parties que le détecteur, plus « ensemble ».
ZONES = [*CLASS_NAMES, "ensemble"]

DESCRIPTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["vue", "qualite", "texte_lu", "formes", "materiel_visible", "finition", "etat", "non_visible"],
    "properties": {
        "vue": {"type": "string", "enum": VUES},
        "qualite": {"type": "string", "enum": QUALITES},
        "texte_lu": {
            "type": "object", "additionalProperties": False, "required": ["transcription", "confiance"],
            "properties": {
                "transcription": {"type": "string", "maxLength": 200},   # exactement ce qui est lisible, "" si rien
                "confiance": {"type": "string", "enum": CONFIANCES},
            },
        },
        "formes": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 60}},
        "materiel_visible": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 60}},
        "finition": {"type": "string", "enum": FINITIONS},
        "etat": {
            "type": "array", "maxItems": 8,
            "items": {
                "type": "object", "additionalProperties": False, "required": ["observation", "gravite", "zone"],
                "properties": {
                    "observation": {"type": "string", "maxLength": 160},
                    "gravite": {"type": "string", "enum": GRAVITES},
                    "zone": {"type": "string", "enum": ZONES},
                },
            },
        },
        "non_visible": {"type": "array", "maxItems": len(ZONES), "items": {"type": "string", "enum": ZONES}},
    },
}

# Même enveloppe que T1_GATEKEEPER_OPENAI_JSON_SCHEMA (backend/llm_clients.py) pour les serveurs compatibles OpenAI.
DESCRIPTION_OPENAI_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {"name": "crop_description", "strict": True, "schema": DESCRIPTION_SCHEMA},
}

DESCRIPTION_PROMPT = (
    "Tu décris une photo (ou un crop) d'une annonce de guitare, de basse ou d'ampli. Décris UNIQUEMENT ce qui est "
    "visible, sans interpréter : ne déduis jamais une marque, un modèle, une année ou un prix. Si un texte est lisible "
    "(logo, plaque, étiquette, numéro de série), recopie-le exactement dans `texte_lu.transcription` avec ta "
    "confiance ; sinon laisse une chaîne vide. Signale dans `etat` chaque défaut ou usure visible (fissure, "
    "décollement, réparation, rouille, manque, déformation), avec une gravité et la zone concernée. Liste dans "
    "`non_visible` ce qui ne peut pas être jugé sur cette image. Réponds uniquement par le JSON demandé."
)


def validate_description(obj):
    """Erreurs de conformité d'une description (liste vide = valide). Vérifie les champs, les types et les
    vocabulaires fermés ; refuse les champs inconnus. Sans dépendance externe."""
    errors = []
    if not isinstance(obj, dict):
        return ["la description doit être un objet JSON"]
    schema = DESCRIPTION_SCHEMA
    for key in schema["required"]:
        if key not in obj:
            errors.append(f"champ manquant : {key}")
    for key in obj:
        if key not in schema["properties"]:
            errors.append(f"champ inconnu : {key}")
    _check_enum(obj, "vue", VUES, errors)
    _check_enum(obj, "qualite", QUALITES, errors)
    _check_enum(obj, "finition", FINITIONS, errors)

    texte = obj.get("texte_lu")
    if "texte_lu" in obj:
        if not isinstance(texte, dict):
            errors.append("texte_lu : objet attendu")
        else:
            if not isinstance(texte.get("transcription"), str):
                errors.append("texte_lu.transcription : chaîne attendue")
            elif len(texte["transcription"]) > 200:
                errors.append("texte_lu.transcription : 200 caractères maximum")
            _check_enum(texte, "confiance", CONFIANCES, errors, prefix="texte_lu.")
            errors += [f"texte_lu : champ inconnu : {k}" for k in texte if k not in ("transcription", "confiance")]

    for key in ("formes", "materiel_visible"):
        if key in obj:
            limit = schema["properties"][key]["maxItems"]
            if not isinstance(obj[key], list) or not all(isinstance(v, str) for v in obj[key]):
                errors.append(f"{key} : liste de chaînes attendue")
            elif len(obj[key]) > limit:
                errors.append(f"{key} : {limit} éléments maximum")

    if "etat" in obj:
        etat = obj["etat"]
        if not isinstance(etat, list):
            errors.append("etat : liste attendue")
        else:
            if len(etat) > schema["properties"]["etat"]["maxItems"]:
                errors.append("etat : trop d'observations")
            for i, item in enumerate(etat):
                if not isinstance(item, dict):
                    errors.append(f"etat[{i}] : objet attendu")
                    continue
                if not isinstance(item.get("observation"), str):
                    errors.append(f"etat[{i}].observation : chaîne attendue")
                _check_enum(item, "gravite", GRAVITES, errors, prefix=f"etat[{i}].")
                _check_enum(item, "zone", ZONES, errors, prefix=f"etat[{i}].")

    if "non_visible" in obj:
        nv = obj["non_visible"]
        if not isinstance(nv, list) or any(v not in ZONES for v in nv):
            errors.append(f"non_visible : liste de valeurs parmi {ZONES}")
    return errors


def _check_enum(container, key, allowed, errors, prefix=""):
    if key in container and container[key] not in allowed:
        errors.append(f"{prefix}{key} : « {container[key]} » hors vocabulaire {allowed}")
