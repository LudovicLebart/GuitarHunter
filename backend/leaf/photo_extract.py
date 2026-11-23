"""Leaf — lecture des PHOTOS (captures d'écran LeafSpy, tableau de bord) : prompts, schémas, lecture de la réponse et GARDE-FOU. PUR.

Principe (même esprit que `backend/t1_photo_text.py` des guitares) : le modèle ne fait que RECOPIER le texte lisible sur l'image ; il ne juge pas,
ne devine pas et ne donne PAS de valeur. La valeur (SOH, Ah, km) est RECALCULÉE par le code à partir de la transcription ; une transcription qui ne
contient pas le format attendu est écartée. Un fait lu sur photo est toujours étiqueté `source: "photo"`, de confiance « faible », ne remplace JAMAIS
le texte de l'annonce ni une règle, et ne fait jamais rejeter une annonce : il peut seulement ALERTER (verdict `BATTERIE_DOUTEUSE`). L'humain
vérifie ensuite la photo (la page ouvre la galerie sur la photo citée)."""
import hashlib
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.leaf import normalize

PHOTO_VERSION = 1
MAX_SELECTED = 3                    # captures retenues par le tri
MAX_GEMINI_PHOTOS = 10              # lecture directe (sans tri) par le fournisseur de secours
MIN_TRANSCRIPT, MAX_TRANSCRIPT = 2, 80
SOH_RANGE = (50.0, 100.0)
AHR_RANGE = (30.0, 130.0)
KM_MISMATCH_RATIO = 0.05

TRIAGE_PROMPT = (
    "Voici les photos d'une annonce de voiture. Indique les NUMÉROS (en commençant à 0, dans l'ordre reçu) des photos qui montrent un ÉCRAN "
    "ou un tableau de bord avec des CHIFFRES lisibles : capture d'écran de téléphone (application LeafSpy ou autre), compteur kilométrique, "
    "écran de batterie. Ne retiens ni les photos de la carrosserie, ni de l'intérieur sans écran, ni du moteur. Au plus 3 numéros ; une liste vide "
    "si aucune photo ne convient. Ne décris rien."
)
# Éditable dans l'app (`leafConfig.prompts.photo`) : le schéma JSON strict (READ_JSON_SCHEMA) impose la forme de la réponse.
READ_PROMPT = (
    "Ces images sont des captures d'écran ou des tableaux de bord d'une voiture électrique à vendre. Pour chaque image, recopie UNIQUEMENT les "
    "textes et les chiffres que tu lis clairement (états de la batterie, SOH, pourcentages, Ah, kilométrage, barres), EXACTEMENT comme écrits, "
    "une courte transcription par image (80 caractères au plus). N'invente rien, ne complète pas un chiffre à moitié lisible, ne calcule rien, "
    "ne commente pas. Si rien n'est lisible sur une image, ne renvoie rien pour elle. Le champ « photo » est le numéro de l'image (à partir de 0, "
    "dans l'ordre reçu)."
)
TRIAGE_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {"name": "leaf_photo_triage", "strict": True, "schema": {
        "type": "object", "properties": {"indices": {"type": "array", "items": {"type": "integer"}}},
        "required": ["indices"], "additionalProperties": False}},
}
READ_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {"name": "leaf_photo_read", "strict": True, "schema": {
        "type": "object", "properties": {"readings": {"type": "array", "items": {
            "type": "object", "properties": {"photo": {"type": "integer"}, "transcript": {"type": "string"}},
            "required": ["photo", "transcript"], "additionalProperties": False}}},
        "required": ["readings"], "additionalProperties": False}},
}

_SIZE_PARAM_RE = re.compile(r"([?&]rule=kijijica-)\d+(-jpg)")
_AUTOSCOUT_SIZE_RE = re.compile(r"/\d+x\d+\.webp$")


def base_url(url: str) -> str:
    """Adresse d'une photo SANS sa taille (l'empreinte ne doit pas changer quand on demande une autre résolution)."""
    return _AUTOSCOUT_SIZE_RE.sub("", _SIZE_PARAM_RE.sub(r"\1_\2", str(url or "")))


def sized_url(url: str, size: str = "medium") -> str:
    """Copie Python de `leafImageUrl` (`src/utils/leaf.js`) : tailles `thumb` (200 / 360x270), `medium` (640 / 720x540), `large` (1600 / 1280x960)."""
    wanted = {"thumb": (200, "360x270"), "medium": (640, "720x540"), "large": (1600, "1280x960")}.get(size, (640, "720x540"))
    u = str(url or "")
    if "media.kijiji.ca" in u and _SIZE_PARAM_RE.search(u):
        return _SIZE_PARAM_RE.sub(rf"\g<1>{wanted[0]}\2", u)
    if "pictures.autoscout24.net" in u and _AUTOSCOUT_SIZE_RE.search(u):
        return _AUTOSCOUT_SIZE_RE.sub(f"/{wanted[1]}.webp", u)
    return u


def photo_urls(listing: Dict[str, Any], limit: int = 12) -> List[str]:
    """Adresses https des photos, sans doublon (l'ordre de la fiche est conservé)."""
    out: List[str] = []
    for u in listing.get("image_urls") or []:
        if isinstance(u, str) and u.startswith("https://") and u not in out:
            out.append(u)
    return out[:limit]


def fingerprint(urls: Sequence[str]) -> str:
    """Empreinte des PHOTOS (version + adresses sans taille) : une annonce dont les photos n'ont pas changé n'est jamais relue."""
    payload = f"{PHOTO_VERSION}|" + "|".join(base_url(u) for u in urls)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def parse_triage(raw: Any, count: int) -> List[int]:
    """Numéros valides (dans [0, count[), sans doublon, au plus MAX_SELECTED ; vide si la réponse est inutilisable."""
    if not isinstance(raw, dict) or not isinstance(raw.get("indices"), list):
        return []
    out: List[int] = []
    for i in raw["indices"]:
        if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < count and i not in out:
            out.append(i)
    return out[:MAX_SELECTED]


def parse_readings(raw: Any, count: int) -> List[Dict[str, Any]]:
    """[{photo, transcript}] valides : numéro de photo effectivement envoyée, transcription de 2 à 80 caractères."""
    if not isinstance(raw, dict) or not isinstance(raw.get("readings"), list):
        return []
    out = []
    for r in raw["readings"]:
        if not isinstance(r, dict) or not isinstance(r.get("photo"), int) or isinstance(r.get("photo"), bool) \
                or not 0 <= r["photo"] < count or not isinstance(r.get("transcript"), str):
            continue
        text = " ".join(r["transcript"].split())
        if MIN_TRANSCRIPT <= len(text) <= MAX_TRANSCRIPT:
            out.append({"photo": r["photo"], "transcript": text})
    return out


_AHR_RE = re.compile(r"\bahr\s*[:=]?\s*(\d{2,3}(?:[.,]\d+)?)|(\d{2,3}(?:[.,]\d+)?)\s*ahr\b")
_KM_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:[ .,]\d{3})+|\d{4,6})\s*km\b")


def apply_guardrails(readings: Sequence[Dict[str, Any]], numbering: Sequence[int], listing: Dict[str, Any]) -> Dict[str, Any]:
    """Faits ACCEPTÉS à partir des transcriptions. `numbering[k]` = numéro (à partir de 1) de la photo k dans la FICHE (pour l'affichage).
    Valeur recalculée PAR LE CODE depuis la transcription :
      - SOH : `normalize.extract_soh` (mot SOH / LeafSpy / état de santé + pourcentage), entre 50 et 100 ;
      - capacité en Ah : « 56,3 Ah », entre 30 et 130 ;
      - kilométrage : jamais un remplacement, seulement un drapeau `photo_km_mismatch` si l'écart avec la fiche dépasse 5 %.
    Les barres du tableau de bord ne sont PAS lues (compter n'est pas recopier)."""
    facts: Dict[str, Dict[str, Any]] = {}
    flags: List[str] = []
    for r in readings:
        text, shown = r["transcript"], numbering[r["photo"]] if r["photo"] < len(numbering) else r["photo"] + 1
        norm = normalize.normalize_text(text)
        soh = normalize.extract_soh(text)
        if soh and SOH_RANGE[0] <= soh[0] <= SOH_RANGE[1] and "soh_photo" not in facts:
            facts["soh_photo"] = {"value": soh[0], "evidence": text, "photo": shown, "source": "photo", "confidence": "low"}
        m = _AHR_RE.search(norm)
        if m and "ahr_photo" not in facts:
            value = float((m.group(1) or m.group(2)).replace(",", "."))
            if AHR_RANGE[0] <= value <= AHR_RANGE[1]:
                facts["ahr_photo"] = {"value": value, "evidence": text, "photo": shown, "source": "photo", "confidence": "low"}
        km = _KM_RE.search(norm)
        listing_km = listing.get("km")
        if km and isinstance(listing_km, (int, float)) and listing_km > 0 and "photo_km_mismatch" not in flags:
            seen = int(re.sub(r"[ .,]", "", km.group(1)))
            if 1000 <= seen <= 500_000 and abs(seen - listing_km) / listing_km > KM_MISMATCH_RATIO:
                flags.append("photo_km_mismatch")
    return {"facts": facts, "flags": flags}
