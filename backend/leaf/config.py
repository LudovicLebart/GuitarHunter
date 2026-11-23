"""Configuration Leaf (`users.config.leafConfig`) : valeurs par défaut et bornes. Fonction PURE.

Double interrupteur : `LEAF_ENABLED` (variable d'environnement du serveur) ET `leafConfig.enabled` (par utilisateur,
faux par défaut). Un `leafConfig` absent = Leaf désactivé : le comportement du bot guitare ne change pas."""
import os
from typing import Any, Dict, Optional

from backend.leaf.filters import DEFAULT_CRITERIA

MIN_FREQUENCY_MIN = 60          # plancher de politesse : jamais plus d'un passage par heure
DEFAULT_FREQUENCY_MIN = 120
DEFAULT_RADIUS_KM = 150
AI_PROVIDERS = ("local", "gemini")           # chaîne d'analyse IA : Qwen local (Dell) puis Gemini Flash
DEFAULT_AI_MAX_CALLS = 30
DEFAULT_EXPERT_MAX_CALLS = 5
DEFAULT_PHOTO_MAX_CALLS = 20          # appels de lecture de photos (tri + lecture) par 24 h          # analyses approfondies (Sonnet 5.5) par 24 h
VALID_SOURCES = ("kijiji", "autohebdo", "facebook")
DEFAULT_SOURCES = ("kijiji", "autohebdo")     # Facebook (navigateur, expérimental) : à activer explicitement
# Ville de référence (décision utilisateur 2026-11-22) : Saint-Bruno-de-Montarville, coordonnées du catalogue
# `backend/resources/city_coordinates.json`. Remplaçable par `scanConfig.home` ({latitude, longitude}).
DEFAULT_HOME = {"name": "Saint-Bruno-de-Montarville", "latitude": 45.5333, "longitude": -73.3500}


def server_enabled() -> bool:
    return os.getenv("LEAF_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


def _num(value, default, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    if low is not None and value < low:
        return low
    if high is not None and value > high:
        return high
    return value


MAX_PROMPT_CHARS = 8000
PROMPT_KEYS = ("extract", "expert", "photo")


def normalize_prompts(raw: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """`leafConfig.prompts` -> {extract, expert, photo} : texte personnalisé, ou None = prompt par défaut du code. Un texte vide, trop long
    ou qui n'est pas une chaîne est ignoré (jamais d'exception)."""
    prompts = raw if isinstance(raw, dict) else {}
    out: Dict[str, Optional[str]] = {}
    for key in PROMPT_KEYS:
        value = prompts.get(key)
        out[key] = value.strip() if isinstance(value, str) and value.strip() and len(value) <= MAX_PROMPT_CHARS else None
    return out


def normalize_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """`leafConfig` brut -> configuration complète et bornée (jamais d'exception sur une valeur absurde)."""
    raw = raw if isinstance(raw, dict) else {}
    scan = raw.get("scanConfig") if isinstance(raw.get("scanConfig"), dict) else {}
    notify = raw.get("notify") if isinstance(raw.get("notify"), dict) else {}
    analysis = raw.get("analysisConfig") if isinstance(raw.get("analysisConfig"), dict) else {}
    providers = [p for p in (analysis.get("providers") or AI_PROVIDERS) if p in AI_PROVIDERS] or list(AI_PROVIDERS)
    d = DEFAULT_CRITERIA
    years = [y for y in (scan.get("years") or []) if isinstance(y, int) and not isinstance(y, bool) and 2010 <= y <= 2030]
    sources = [s for s in (scan.get("sources") or DEFAULT_SOURCES) if s in VALID_SOURCES] or list(DEFAULT_SOURCES)
    min_price = _num(scan.get("min_price"), d["min_price"], 0)
    max_price = max(_num(scan.get("max_price"), d["max_price"], 0), min_price)
    home = scan.get("home") if isinstance(scan.get("home"), dict) else {}
    lat, lon = home.get("latitude"), home.get("longitude")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lat, lon)):
        lat, lon = DEFAULT_HOME["latitude"], DEFAULT_HOME["longitude"]     # point de repère incomplet : ville par défaut
    return {
        "enabled": raw.get("enabled") is True,
        "scan": {
            "frequency": int(_num(scan.get("frequency"), DEFAULT_FREQUENCY_MIN, MIN_FREQUENCY_MIN, 24 * 60)),
            "years": years or list(d["years"]),
            "min_price": min_price,
            "max_price": max_price,
            "max_km": _num(scan.get("max_km"), d["max_km"], 1),
            "pages": int(_num(scan.get("pages"), 2, 1, 3)),
            "sources": sources,
            "read_details": scan.get("read_details") is not False,
            "home": {"latitude": lat, "longitude": lon,
                     "max_km": _num(scan.get("radius_km"), DEFAULT_RADIUS_KM, 1)},
        },
        # IA niveau 2 : ÉTEINTE par défaut (coût) ; `providers` = ordre d'essai.
        "analysis": {"enabled": analysis.get("enabled") is True,
                     "max_calls_per_day": int(_num(analysis.get("max_calls_per_day"), DEFAULT_AI_MAX_CALLS, 1, 500)),
                     "max_expert_per_day": int(_num(analysis.get("max_expert_per_day"), DEFAULT_EXPERT_MAX_CALLS, 1, 50)),
                     "photos": analysis.get("photos") is True,
                     "max_photo_calls_per_day": int(_num(analysis.get("max_photo_calls_per_day"), DEFAULT_PHOTO_MAX_CALLS, 1, 200)),
                     "providers": providers},
        "prompts": normalize_prompts(raw.get("prompts")),
        "notify": {"enabled": notify.get("enabled") is not False, "new": notify.get("new") is not False,
                   "price_drop": notify.get("price_drop") is not False},
    }
