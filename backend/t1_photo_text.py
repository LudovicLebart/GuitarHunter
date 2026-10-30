"""Lecture des photos par le Portier (2026-10-15) : le texte visible (marque, modèle, numéro de série) sert à CHERCHER des
fiches dans la base « univers des guitares », en plus du titre et de la description.

Pourquoi : la marque n'est souvent que sur la tête de manche ou l'étiquette, pas dans le titre de l'annonce. Avant ce
module, le Portier cherchait les fiches AVANT de voir les photos ; seul l'Expert (T3) lisait ce texte, trop tard.

Principe (source unique, partagée par la production — `llm_clients._t1_read_photo_text` — et par le rejeu
`backend/scripts/t1_kb_paired_replay.py`) :
  1. une passe courte du modèle local qui RECOPIE le texte lisible, sans juger ni deviner ;
  2. `parse_photo_text` nettoie la réponse (taille bornée, doublons, valeurs « vides ») ;
  3. le texte nettoyé n'est utilisé QUE pour chercher des fiches : il n'est jamais injecté tel quel dans le prompt du
     Portier (une lecture inventée ne doit pas se propager comme un fait).
Module pur (aucun réseau, aucune base) : testé sans Dell.
"""
import re

PHOTO_TEXT_PROMPT = (
    "Ces photos montrent un instrument de musique à vendre. Recopie UNIQUEMENT le texte que tu lis clairement sur "
    "l'instrument : logo ou marque (souvent sur la tête de manche), nom du modèle, étiquette, plaque, numéro de série, "
    "inscriptions sur les micros, l'ampli ou l'étui. Un élément par entrée, exactement comme écrit. N'invente rien, ne "
    "complète pas un mot à moitié lisible, n'ajoute ni description ni jugement ni prix. Si rien n'est lisible, renvoie "
    "une liste vide."
)

PHOTO_TEXT_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "t1_photo_text",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"visible_text": {"type": "array", "items": {"type": "string"}}},
            "required": ["visible_text"],
            "additionalProperties": False,
        },
    },
}

MAX_ITEMS = 20
MAX_ITEM_CHARS = 60
MAX_TOTAL_CHARS = 400
# Réponses « vides » que le modèle écrit parfois au lieu de renvoyer une liste vide.
_EMPTY_VALUES = {"n/a", "na", "none", "null", "aucun", "aucune", "rien", "unknown", "inconnu", "illisible",
                 "no text", "pas de texte", "-", "?"}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def parse_photo_text(result):
    """Texte visible nettoyé (chaîne, vide si rien d'exploitable) à partir de la réponse JSON du modèle.
    Tolère une réponse mal formée : ne lève jamais."""
    if not isinstance(result, dict):
        return ""
    raw = result.get("visible_text")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return ""
    items, seen, total = [], set(), 0
    for item in raw:
        if not isinstance(item, str):
            continue
        text = " ".join(_CONTROL.sub(" ", item).split())[:MAX_ITEM_CHARS].strip()
        key = text.casefold()
        if not text or key in _EMPTY_VALUES or key in seen or not re.search(r"[A-Za-z0-9À-ÿ]", text):
            continue
        if total + len(text) + 3 > MAX_TOTAL_CHARS or len(items) >= MAX_ITEMS:
            break
        seen.add(key)
        items.append(text)
        total += len(text) + 3
    return " ; ".join(items)
