"""Bornes et listes blanches des corps de requête de l'API (revue de l'API, 2026-11-07).

Les routes authentifiées acceptaient des corps libres : un compte pouvait écraser une annonce partagée, poster un
nombre illimité de commandes ou écrire des valeurs absurdes dans le catalogue commun. Chaque fonction lève `ValueError`
(message lisible, renvoyé en 422) ; aucune ne corrige en silence. Sans dépendance : testé sans base."""
import json
import math

from backend.url_guard import MAX_URL_LENGTH, is_listing_url

MAX_SHARED_BYTES = 200_000
MAX_SHARED_URLS = 20
MAX_COMMAND_PAYLOAD_BYTES = 20_000
MAX_PENDING_COMMANDS = 20            # commandes en attente par compte (au-delà : 429)
MAX_DEAL_IDS = 200                   # ids par lecture groupée (POST /deals/by-ids)
MAX_MONEY = 10_000_000
MAX_SHORT_TEXT = 500
MAX_LONG_TEXT = 5_000

# Mêmes types que les gestionnaires de `main.py` (le bot journalise et rejette un type inconnu : inutile de l'empiler).
COMMAND_TYPES = frozenset({
    "REFRESH", "CLEANUP", "REANALYZE_ALL", "SCAN_URL", "ADD_CITY", "ANALYZE_DEAL",
    "REEVALUATE_NOT_PROMOTED", "CLEAR_LOGS", "STOP_BOT", "STOP_SCAN", "START_BOT",
})

# Colonnes de score (smallint) corrigeables à la main : entiers de 0 à 10.
SCORE_COLUMNS = frozenset({
    "deal_score", "authenticity_score", "condition_score", "liquidity_score", "restoration_interest_score",
})


def _size(value) -> int:
    return len(json.dumps(value, default=str))


def is_finite_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check_money(value, name="montant"):
    """`None` accepté ; sinon un nombre fini entre 0 et `MAX_MONEY`."""
    if value is None:
        return
    if not is_finite_number(value) or not 0 <= value <= MAX_MONEY:
        raise ValueError(f"{name} doit être un nombre entre 0 et {MAX_MONEY}.")


def check_text(value, name, limit=MAX_LONG_TEXT):
    if value is not None and (not isinstance(value, str) or len(value) > limit):
        raise ValueError(f"{name} est trop long (maximum {limit} caractères).")


def validate_command(type_, payload):
    if type_ not in COMMAND_TYPES:
        raise ValueError("Type de commande inconnu.")
    if _size(payload) > MAX_COMMAND_PAYLOAD_BYTES:
        raise ValueError("Charge de la commande trop volumineuse.")


def validate_deal_ids(ids):
    if len(ids) > MAX_DEAL_IDS:
        raise ValueError(f"Au plus {MAX_DEAL_IDS} ids par lecture.")


def _check_https_urls(urls, name):
    if len(urls) > MAX_SHARED_URLS:
        raise ValueError(f"{name} : au plus {MAX_SHARED_URLS} adresses.")
    for u in urls:
        if not isinstance(u, str) or len(u) > MAX_URL_LENGTH or not u.startswith("https://"):
            raise ValueError(f"{name} : adresse https attendue.")


def validate_shared_snapshot(snapshot):
    """Instantané d'une annonce partagée, servi PUBLIQUEMENT : lien vers une annonce Facebook/Kijiji ou rien, photos en
    https, taille bornée."""
    if snapshot.get("link") is not None and not is_listing_url(snapshot["link"]):
        raise ValueError("Lien refusé : une annonce Facebook ou Kijiji en https est attendue.")
    _check_https_urls(snapshot.get("storageImageUrls") or [], "storageImageUrls")
    _check_https_urls(snapshot.get("imageUrls") or [], "imageUrls")
    check_money(snapshot.get("price"), "price")
    if _size(snapshot) > MAX_SHARED_BYTES:
        raise ValueError("Annonce partagée trop volumineuse.")


def validate_analysis_overrides(fields):
    """Corrections manuelles de l'analyse, GLOBALES (catalogue commun) : scalaires bornés, scores entiers de 0 à 10."""
    for key, value in fields.items():
        if value is None or isinstance(value, bool):
            continue
        if key in SCORE_COLUMNS:
            if not isinstance(value, int) or not 0 <= value <= 10:
                raise ValueError(f"{key} doit être un entier entre 0 et 10.")
        elif isinstance(value, str):
            if len(value) > MAX_SHORT_TEXT:
                raise ValueError(f"{key} est trop long.")
        elif is_finite_number(value):
            if abs(value) > MAX_MONEY:
                raise ValueError(f"{key} est hors bornes.")
        else:
            raise ValueError(f"{key} doit être un texte, un nombre ou un booléen.")


def validate_chat_extras(display_text, proposals, photo_recall, requalification):
    """Champs annexes d'un message de chat (le contenu `parts` a sa propre borne dans `main._check_chat_payload`)."""
    check_text(display_text, "displayText", 100_000)
    for name, value in (("restorationProposals", proposals), ("photoRecall", photo_recall),
                        ("requalificationProposal", requalification)):
        if value is not None and _size(value) > 100_000:
            raise ValueError(f"{name} est trop volumineux.")


def validate_restoration_item(label=None, category=None, notes=None, estimated_cost=None, actual_cost=None):
    check_text(label, "label", MAX_SHORT_TEXT)
    check_text(category, "category", 100)
    check_text(notes, "notes", MAX_LONG_TEXT)
    check_money(estimated_cost, "estimatedCost")
    check_money(actual_cost, "actualCost")
