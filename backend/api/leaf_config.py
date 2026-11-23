"""Validation de `users.config.leafConfig` côté API : AUTONOME (n'importe rien d'autre de `backend/` : l'API de production ne reçoit
qu'une liste de modules). Les bornes DOIVENT rester celles de `backend/leaf/config.py::normalize_config` côté bot : le test de parité
`backend/leaf/test_leaf_config_parity.py` le vérifie. L'API REFUSE (422) une valeur hors bornes ; le bot, lui, la ramène aux bornes."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

MIN_FREQUENCY_MIN = 60
MAX_FREQUENCY_MIN = 24 * 60
VALID_SOURCES = ("kijiji", "autohebdo", "facebook")
DEFAULT_SOURCES = ("kijiji", "autohebdo")
DEFAULT_SCAN = {"frequency": 120, "min_price": 1500, "max_price": 7500, "max_km": 150_000, "pages": 2,
                "years": [2016, 2017, 2018], "sources": list(DEFAULT_SOURCES), "read_details": True}
DEFAULT_HOME = {"name": "Saint-Bruno-de-Montarville", "latitude": 45.5333, "longitude": -73.3500}
DEFAULT_RADIUS_KM = 150
AI_PROVIDERS = ("local", "gemini")
DEFAULT_AI_MAX_CALLS = 30
DEFAULT_EXPERT_MAX_CALLS = 5
DEFAULT_PHOTO_MAX_CALLS = 20          # appels de lecture de photos (tri + lecture) par 24 h


class HomeIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    name: Optional[str] = Field(None, max_length=80)


class ScanIn(BaseModel):
    frequency: int = Field(DEFAULT_SCAN["frequency"], ge=MIN_FREQUENCY_MIN, le=MAX_FREQUENCY_MIN)
    min_price: int = Field(DEFAULT_SCAN["min_price"], ge=0, le=1_000_000)
    max_price: int = Field(DEFAULT_SCAN["max_price"], ge=0, le=1_000_000)
    max_km: int = Field(DEFAULT_SCAN["max_km"], ge=1, le=1_000_000)
    pages: int = Field(DEFAULT_SCAN["pages"], ge=1, le=3)
    years: List[int] = Field(default_factory=lambda: list(DEFAULT_SCAN["years"]), min_length=1, max_length=12)
    sources: List[str] = Field(default_factory=lambda: list(DEFAULT_SOURCES), min_length=1)
    read_details: bool = True
    home: Optional[HomeIn] = None
    radius_km: int = Field(DEFAULT_RADIUS_KM, ge=1, le=2000)

    @model_validator(mode="after")
    def _coherent(self):
        if self.max_price < self.min_price:
            raise ValueError("Le prix maximum doit être au moins égal au prix minimum.")
        if any(not 2010 <= y <= 2030 for y in self.years):
            raise ValueError("Années hors de 2010-2030.")
        if any(s not in VALID_SOURCES for s in self.sources):
            raise ValueError(f"Sources valides : {', '.join(VALID_SOURCES)}.")
        return self


class NotifyIn(BaseModel):
    enabled: bool = True
    new: bool = True
    price_drop: bool = True


class AnalysisIn(BaseModel):
    enabled: bool = False
    max_calls_per_day: int = Field(DEFAULT_AI_MAX_CALLS, ge=1, le=500)
    max_expert_per_day: int = Field(DEFAULT_EXPERT_MAX_CALLS, ge=1, le=50)
    photos: bool = False
    max_photo_calls_per_day: int = Field(DEFAULT_PHOTO_MAX_CALLS, ge=1, le=200)
    providers: List[str] = Field(default_factory=lambda: list(AI_PROVIDERS), min_length=1)

    @model_validator(mode="after")
    def _valid_providers(self):
        if any(p not in AI_PROVIDERS for p in self.providers):
            raise ValueError(f"Fournisseurs valides : {', '.join(AI_PROVIDERS)}.")
        return self


class LeafConfigIn(BaseModel):
    enabled: bool = False
    scan: ScanIn = Field(default_factory=ScanIn)
    notify: NotifyIn = Field(default_factory=NotifyIn)
    analysis: AnalysisIn = Field(default_factory=AnalysisIn)


def to_stored(cfg: LeafConfigIn) -> Dict[str, Any]:
    """Forme écrite dans `users.config.leafConfig` (celle que lit `backend/leaf/config.py`, clé `scanConfig`)."""
    scan = cfg.scan.model_dump(exclude={"home"})
    if cfg.scan.home:
        scan["home"] = cfg.scan.home.model_dump(exclude_none=True)
    return {"enabled": cfg.enabled, "scanConfig": scan, "notify": cfg.notify.model_dump(), "analysisConfig": cfg.analysis.model_dump()}


def _num(value, default, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return min(max(value, low), high)


def effective(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """`leafConfig` stocké -> configuration complète (valeurs par défaut incluses) telle que l'affiche le panneau de réglages."""
    raw = raw if isinstance(raw, dict) else {}
    scan = raw.get("scanConfig") if isinstance(raw.get("scanConfig"), dict) else {}
    notify = raw.get("notify") if isinstance(raw.get("notify"), dict) else {}
    analysis = raw.get("analysisConfig") if isinstance(raw.get("analysisConfig"), dict) else {}
    providers = [p for p in (analysis.get("providers") or AI_PROVIDERS) if p in AI_PROVIDERS] or list(AI_PROVIDERS)
    years = [y for y in (scan.get("years") or []) if isinstance(y, int) and not isinstance(y, bool) and 2010 <= y <= 2030]
    sources = [s for s in (scan.get("sources") or DEFAULT_SOURCES) if s in VALID_SOURCES] or list(DEFAULT_SOURCES)
    min_price = _num(scan.get("min_price"), DEFAULT_SCAN["min_price"], 0, 10**9)
    home = scan.get("home") if isinstance(scan.get("home"), dict) else {}
    lat, lon = home.get("latitude"), home.get("longitude")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lat, lon)):
        lat, lon = DEFAULT_HOME["latitude"], DEFAULT_HOME["longitude"]
        name = DEFAULT_HOME["name"]
    else:
        name = home.get("name") if isinstance(home.get("name"), str) else None
    return {
        "enabled": raw.get("enabled") is True,
        "scan": {
            "frequency": int(_num(scan.get("frequency"), DEFAULT_SCAN["frequency"], MIN_FREQUENCY_MIN, MAX_FREQUENCY_MIN)),
            "years": years or list(DEFAULT_SCAN["years"]),
            "min_price": min_price,
            "max_price": max(_num(scan.get("max_price"), DEFAULT_SCAN["max_price"], 0, 10**9), min_price),
            "max_km": _num(scan.get("max_km"), DEFAULT_SCAN["max_km"], 1, 10**9),
            "pages": int(_num(scan.get("pages"), DEFAULT_SCAN["pages"], 1, 3)),
            "sources": sources,
            "read_details": scan.get("read_details") is not False,
            "home": {"latitude": lat, "longitude": lon, "name": name},
            "radius_km": _num(scan.get("radius_km"), DEFAULT_RADIUS_KM, 1, 10**9),
        },
        "notify": {"enabled": notify.get("enabled") is not False, "new": notify.get("new") is not False,
                   "price_drop": notify.get("price_drop") is not False},
        "analysis": {"enabled": analysis.get("enabled") is True,
                     "max_calls_per_day": int(_num(analysis.get("max_calls_per_day"), DEFAULT_AI_MAX_CALLS, 1, 500)),
                     "max_expert_per_day": int(_num(analysis.get("max_expert_per_day"), DEFAULT_EXPERT_MAX_CALLS, 1, 50)),
                     "photos": analysis.get("photos") is True,
                     "max_photo_calls_per_day": int(_num(analysis.get("max_photo_calls_per_day"), DEFAULT_PHOTO_MAX_CALLS, 1, 200)),
                     "providers": providers},
    }
