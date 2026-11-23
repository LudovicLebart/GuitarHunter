"""Normalisation d'une annonce Leaf : fonctions PURES, sans réseau ni base.

Tout le texte est comparé sous forme normalisée (minuscules, sans accents, espaces compactés) ; les
« preuves » (`soh_evidence`) sont des extraits de CETTE forme normalisée, ce qui permet de les
revalider plus tard par simple recherche de sous-chaîne (garde-fou contre les citations inventées).
"""
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

SOH_MIN, SOH_MAX = 30.0, 100.0
KM_MIN, KM_MAX = 1_000, 400_000
YEAR_MIN, YEAR_MAX = 2011, 2026


def normalize_text(text: Optional[str]) -> str:
    """Minuscules, sans accents, apostrophes unifiées, espaces compactés."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().replace("’", "'").replace(" ", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip()


def parse_year(text: Optional[str]) -> Optional[int]:
    for m in re.finditer(r"\b(20[12]\d)\b", normalize_text(text)):
        y = int(m.group(1))
        if YEAR_MIN <= y <= YEAR_MAX:
            return y
    return None


_KM_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:[ .,]\d{3})+|\d{4,6})\s*km\b")


def parse_km(text: Optional[str]) -> Optional[int]:
    m = _KM_RE.search(normalize_text(text))
    if not m:
        return None
    value = int(re.sub(r"[ .,]", "", m.group(1)))
    return value if KM_MIN <= value <= KM_MAX else None


def parse_trim(text: Optional[str]) -> Optional[str]:
    """S / SV / SL, sinon None (jamais « ? » : l'absence d'information reste explicite)."""
    t = normalize_text(text)
    m = re.search(r"\bleaf\s*[-/]?\s*(sl|sv|s)\b", t)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b(sl|sv)\b", t)
    if m:
        return m.group(1).upper()
    if re.search(r"\bmodele s\b", t):
        return "S"
    return None


def battery_info(year: Optional[int], trim: Optional[str], text: Optional[str] = None
                 ) -> Tuple[Optional[int], Optional[int], str]:
    """(kwh_bas, kwh_haut, source). source : 'stated' | 'inferred' | 'unknown'.
    2016 S (ou trim inconnu) : 24 ou 30 kWh possibles -> (24, 30)."""
    t = normalize_text(text)
    for m in re.finditer(r"\b(24|30|40|62)\s*kwh\b", t):
        if _NEGATION.search(t[max(0, m.start() - 30):m.start()]) or re.search(
                r"(?:contrairement|comparativement|versus|vs\.?|plutot que|au lieu)\s+(?:aux?\s+|a\s+la\s+|la\s+|les\s+)?$",
                t[max(0, m.start() - 30):m.start()]):
            continue
        k = int(m.group(1))
        return k, k, "stated"
    if year == 2018:
        return 40, 40, "inferred"
    if year == 2017:
        return 30, 30, "inferred"
    if year == 2016:
        return (30, 30, "inferred") if trim in ("SV", "SL") else (24, 30, "inferred")
    return None, None, "unknown"


_SOH_PATTERNS = [
    re.compile(r"(?:\bsoh\b|sante(?: de la)? batterie|etat(?: de sante)?(?: de la)? batterie|battery health|leaf ?spy)"
               r"[^0-9]{0,25}(\d{2,3}(?:[.,]\d)?)\s*%"),
    re.compile(r"(\d{2,3}(?:[.,]\d)?)\s*%\s*(?:de\s*)?(?:\bsoh\b|sante(?: de la)? batterie|battery health)"),
    # « ~50 % sur LeafSpy », « 87 % selon LeafSpy » : le pourcentage PRÉCÈDE la mention de l'outil
    re.compile(r"(\d{2,3}(?:[.,]\d)?)\s*%\s*(?:sur|selon|avec|par|d'apres|mesure[^a-z]{0,3}(?:sur|avec|par))\s*leaf ?spy"),
]


def extract_soh(text: Optional[str]) -> Optional[Tuple[float, str]]:
    """(pourcentage, preuve) si l'annonce donne explicitement l'état de santé de la batterie."""
    t = normalize_text(text)
    for pat in _SOH_PATTERNS:
        m = pat.search(t)
        if m:
            value = float(m.group(1).replace(",", "."))
            if SOH_MIN <= value <= SOH_MAX:
                return value, m.group(0)
    return None


def extract_capacity_bars(text: Optional[str]) -> Optional[Tuple[int, str]]:
    """(barres sur 12, preuve) : « 11/12 barres », « 10 sur 12 barres », « 6 barres sur 12 », « 6 barres / 12 »."""
    m = re.search(r"\b(\d{1,2})\s*(?:/|sur)\s*12\s*barres?|\b(\d{1,2})\s*barres?\s*(?:/|sur)\s*12\b", normalize_text(text))
    if m:
        bars = int(m.group(1) or m.group(2))
        if 1 <= bars <= 12:
            return bars, m.group(0)
    return None


_ACCIDENT_WORDS = ("accident", "reconstruit", "vgr", "salvage", "pour pieces", "a reparer",
                   "non roulante", "dommages importants")
_NEGATION = re.compile(r"\b(?:jamais|sans|aucun|aucune|rien|pas|non|ni|0|never|no)(?:['\s]+(?:\w+['\s]+){0,3}?)?$")


def accident_flags(text: Optional[str]) -> List[str]:
    """Mots d'alerte (accident, reconstruit, pièces...) HORS négations (« jamais accidentée »)."""
    t = normalize_text(text)
    found: List[str] = []
    for word in _ACCIDENT_WORDS:
        for m in re.finditer(r"\b" + re.escape(word), t):
            if _NEGATION.search(t[max(0, m.start() - 30):m.start()]):
                continue
            if word not in found:
                found.append(word)
            break
    return found


_MENTIONS = {
    "heat_pump": r"pompe a chaleur|heat pump",
    "winter_tires": r"pneus? (?:d'?)?hiver|winter tires?",
    "chademo": r"chademo|charge rapide|recharge rapide",
    "charging_cable": r"cable (?:de )?(?:charge|recharge)|chargeur (?:portable|220|240|120|110)|evse",
    "heated_seats": r"sieges? chauffants?|bancs? chauffants?|heated seats?",
    "heated_wheel": r"volant chauffant|heated (?:steering )?wheel",
    "carfax": r"carfax",
    "battery_replaced": r"batterie\s+(?!12\s*v)(?:(?!12\s*v)\S+\s+){0,3}?(?:neuve|remplacee|changee)"
                        r"|nouvelle batterie(?!\s*(?:de\s*)?12\s*v)"
                        r"|remplacement (?:de la |de )?batterie(?!\s*(?:de\s*)?12\s*v)"
                        r"|(?:battery|batt)\s+(?:was\s+)?replaced|replaced (?:the )?battery|new battery(?!\s*12\s*v)",
}


def detect_mentions(text: Optional[str]) -> Dict[str, bool]:
    t = normalize_text(text)
    return {k: bool(re.search(p, t)) for k, p in _MENTIONS.items()}


def normalize_listing(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Complète une annonce brute (sortie d'une source) : champs absents déduits du titre/description,
    plus les champs dérivés (batterie, SOH annoncé + preuve, drapeaux). Ne modifie pas `raw`."""
    listing = dict(raw)
    equipment = " ".join(raw.get("equipment") or [])
    text = f"{raw.get('title') or ''} {raw.get('description') or ''} {equipment}"
    listing["year"] = raw.get("year") or parse_year(raw.get("title")) or parse_year(text)
    listing["km"] = raw.get("km") if raw.get("km") is not None else parse_km(text)
    listing["trim"] = raw.get("trim") or parse_trim(text)
    low, high, source = battery_info(listing["year"], listing["trim"], text)
    listing["battery_kwh_low"], listing["battery_kwh_high"], listing["battery_source"] = low, high, source
    soh = extract_soh(text)
    listing["soh_announced"], listing["soh_evidence"] = (soh if soh else (None, None))
    bars = extract_capacity_bars(text)
    listing["capacity_bars"], listing["capacity_bars_evidence"] = (bars if bars else (None, None))
    listing["accident_flags"] = accident_flags(text)
    # Indicateurs STRUCTURÉS de la fiche (AutoHebdo) : seul `True` compte ; `None`/`False` = pas d'information fiable.
    if raw.get("had_accident") is True:
        listing["accident_flags"].append("declared_accident")
    if raw.get("currently_damaged") is True:
        listing["accident_flags"].append("declared_damage")
    listing["mentions"] = detect_mentions(text)
    return listing
