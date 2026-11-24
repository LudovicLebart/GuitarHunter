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


# Prompts par DÉFAUT affichés dans l'éditeur (copie de `backend/leaf/ai_extract.py`, `expert.py`, `photo_extract.py` : l'API de production n'importe pas
# `backend/leaf/`). Le test de parité `backend/leaf/test_leaf_config_parity.py` vérifie qu'ils sont IDENTIQUES à ceux du bot.
MAX_PROMPT_CHARS = 8000
DEFAULT_PROMPTS = {
    "extract": 'Tu analyses l\'annonce d\'une Nissan Leaf d\'occasion. Extrais UNIQUEMENT ce que le TEXTE ci-dessous dit explicitement.\nRègles strictes :\n- Pour chaque fait, donne "evidence" : la phrase ou le morceau de phrase COPIÉ MOT POUR MOT du texte. Sans citation exacte, mets "value": null.\n- Ne déduis rien (ni de l\'année, ni du modèle, ni de ce qui est « habituel »). Si le texte ne le dit pas : "value": null.\n- "battery_replaced" concerne la batterie de TRACTION (haute tension), pas la batterie 12 V.\n- "accident_mentioned" = true seulement si le texte dit que la voiture a subi un accident ou un dommage ; false seulement si le texte le nie explicitement (« jamais accidentée », « aucun accident » = false).\n- Un fait NIÉ par le texte (« sans pompe à chaleur », « pas de CHAdeMO », « jamais accidentée ») vaut false, JAMAIS true : la citation d\'une négation ne prouve pas que le fait existe.\n- "soh_pct" : l\'état de santé de la batterie en pourcentage, seulement s\'il est écrit (SOH, état de santé, LeafSpy).\n- "confidence" : "high" si la citation est sans ambiguïté, "medium" ou "low" sinon.\n- "summary" : 2 à 3 phrases en français sur ce que dit (et ne dit pas) l\'annonce, sans rien inventer.\n- "attention" : jusqu\'à 5 points à vérifier, chacun avec sa citation exacte ("evidence").',
    "expert": 'Tu es un expert en achat de Nissan Leaf d\'occasion au Québec. L\'acheteur cherche une voiture pour environ 50 km par jour, hiver compris.\nOn te donne l\'annonce et des FAITS ÉTABLIS PAR LE CODE (scores, verdict, faits déjà prouvés par citation) : traite-les comme exacts, sans les refaire.\n\nRègles strictes :\n- N\'invente aucun fait sur la voiture. Ce que l\'annonce ne dit pas est « inconnu » : dis-le, et transforme-le en question pour le vendeur.\n- Chaque risque doit citer l\'annonce MOT POUR MOT ("evidence"). Sans citation exacte, ne le mentionne pas.\n- "price_ceiling" : le prix maximum raisonnable à payer, en dollars. Appuie-toi sur le prix de marché estimé s\'il est fourni ; sinon laisse "amount": null.\n- "worth_visiting" : "oui", "peut-etre" ou "non". Un SOH inconnu n\'est pas une raison de refuser : c\'est une mesure à faire.\n- Réponds en français.',
    "photo": "Ces images sont des captures d'écran ou des tableaux de bord d'une voiture électrique à vendre. Pour chaque image, recopie UNIQUEMENT les textes et les chiffres que tu lis clairement (états de la batterie, SOH, pourcentages, Ah, kilométrage, barres), EXACTEMENT comme écrits, une courte transcription par image (80 caractères au plus). N'invente rien, ne complète pas un chiffre à moitié lisible, ne calcule rien, ne commente pas. Si rien n'est lisible sur une image, ne renvoie rien pour elle. Le champ « photo » est le numéro de l'image (à partir de 0, dans l'ordre reçu).",
}


def normalize_prompts(raw: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Textes personnalisés (None = prompt par défaut), mêmes règles que `backend/leaf/config.py::normalize_prompts`."""
    prompts = raw if isinstance(raw, dict) else {}
    out: Dict[str, Optional[str]] = {}
    for key in DEFAULT_PROMPTS:
        value = prompts.get(key)
        out[key] = value.strip() if isinstance(value, str) and value.strip() and len(value) <= MAX_PROMPT_CHARS else None
    return out


class PromptsIn(BaseModel):
    """Corps de `PUT /leaf/prompts` : `null` ou texte vide = prompt par défaut ; au plus 8 000 caractères."""
    extract: Optional[str] = Field(None, max_length=MAX_PROMPT_CHARS)
    expert: Optional[str] = Field(None, max_length=MAX_PROMPT_CHARS)
    photo: Optional[str] = Field(None, max_length=MAX_PROMPT_CHARS)


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
        "prompts": normalize_prompts(raw.get("prompts")),
        "notify": {"enabled": notify.get("enabled") is not False, "new": notify.get("new") is not False,
                   "price_drop": notify.get("price_drop") is not False},
        "analysis": {"enabled": analysis.get("enabled") is True,
                     "max_calls_per_day": int(_num(analysis.get("max_calls_per_day"), DEFAULT_AI_MAX_CALLS, 1, 500)),
                     "max_expert_per_day": int(_num(analysis.get("max_expert_per_day"), DEFAULT_EXPERT_MAX_CALLS, 1, 50)),
                     "max_photo_calls_per_day": int(_num(analysis.get("max_photo_calls_per_day"), DEFAULT_PHOTO_MAX_CALLS, 1, 200)),
                     "providers": providers},
    }
