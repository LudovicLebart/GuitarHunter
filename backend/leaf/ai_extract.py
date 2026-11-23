"""Leaf — niveau 2 (IA) : prompt, lecture de la réponse et GARDE-FOU DES PREUVES. Fonctions PURES (aucun appel réseau, aucun modèle).

Principe du projet : le code calcule, l'IA ne fait qu'EXTRAIRE de l'annonce des faits que les expressions régulières ratent, chacun
avec la citation exacte qui le justifie. Une citation qui n'est pas retrouvée MOT POUR MOT dans le texte de l'annonce invalide le
fait (jamais accepté « sur parole »). Si l'IA et les règles se contredisent, les règles gagnent. Aucune déduction par photo ici
(texte seulement). Le résumé est un texte libre de l'IA : affiché comme tel, jamais utilisé dans un calcul."""
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.leaf import normalize

AI_VERSION = 1                      # change quand le prompt ou le garde-fou change : les analyses stockées sont alors refaites
MAX_TEXT_CHARS = 3500
MAX_SUMMARY_CHARS = 500
MAX_ATTENTION = 5
MIN_EVIDENCE_CHARS = 4

# champ -> (libellé, type). `soh_pct` : nombre ; les autres : booléens.
FACT_FIELDS: Dict[str, Tuple[str, str]] = {
    "soh_pct": ("SOH annoncé (%)", "number"),
    "battery_replaced": ("Batterie de traction remplacée", "bool"),
    "accident_mentioned": ("Accident ou dommage mentionné", "bool"),
    "heat_pump": ("Pompe à chaleur", "bool"),
    "winter_tires": ("Pneus d'hiver inclus", "bool"),
    "chademo": ("Charge rapide CHAdeMO", "bool"),
    "charging_cable": ("Câble de recharge fourni", "bool"),
}
CONFIDENCES = ("high", "medium", "low")

# Les INSTRUCTIONS (règles de lecture) sont éditables dans l'app (`leafConfig.prompts.extract`) ; le CONTRAT (forme JSON attendue) est toujours
# ajouté par le code : un prompt modifié ne peut pas changer le format de la réponse ni contourner le garde-fou des preuves (appliqué après).
DEFAULT_INSTRUCTIONS = """Tu analyses l'annonce d'une Nissan Leaf d'occasion. Extrais UNIQUEMENT ce que le TEXTE ci-dessous dit explicitement.
Règles strictes :
- Pour chaque fait, donne "evidence" : la phrase ou le morceau de phrase COPIÉ MOT POUR MOT du texte. Sans citation exacte, mets "value": null.
- Ne déduis rien (ni de l'année, ni du modèle, ni de ce qui est « habituel »). Si le texte ne le dit pas : "value": null.
- "battery_replaced" concerne la batterie de TRACTION (haute tension), pas la batterie 12 V.
- "accident_mentioned" = true seulement si le texte dit que la voiture a subi un accident ou un dommage ; false seulement si le texte le nie explicitement.
- "soh_pct" : l'état de santé de la batterie en pourcentage, seulement s'il est écrit (SOH, état de santé, LeafSpy).
- "confidence" : "high" si la citation est sans ambiguïté, "medium" ou "low" sinon.
- "summary" : 2 à 3 phrases en français sur ce que dit (et ne dit pas) l'annonce, sans rien inventer.
- "attention" : jusqu'à 5 points à vérifier, chacun avec sa citation exacte ("evidence")."""

CONTRACT = """Réponds UNIQUEMENT avec un objet JSON de cette forme :
{"summary": "...", "facts": {"soh_pct": {"value": null, "evidence": null, "confidence": "low"}, "battery_replaced": {...}, "accident_mentioned": {...}, "heat_pump": {...}, "winter_tires": {...}, "chademo": {...}, "charging_cable": {...}}, "attention": [{"text": "...", "evidence": "..."}]}

TEXTE DE L'ANNONCE :
"""

PROMPT = DEFAULT_INSTRUCTIONS + "\n\n" + CONTRACT      # prompt par défaut complet
MAX_PROMPT_CHARS = 8000


def listing_text(listing: Dict[str, Any]) -> str:
    """Texte analysé : titre, description et équipement structuré de la fiche (le même que celui des règles)."""
    equipment = " ".join(listing.get("equipment_list") or [])
    text = f"{listing.get('title') or ''}\n{listing.get('description') or ''}\n{equipment}".strip()
    return text[:MAX_TEXT_CHARS]


def build_prompt(listing: Dict[str, Any], instructions: Optional[str] = None) -> str:
    return (((instructions or "").strip() or DEFAULT_INSTRUCTIONS).rstrip() + "\n\n" + CONTRACT) + listing_text(listing)


def fingerprint(listing: Dict[str, Any], instructions: Optional[str] = None) -> str:
    """Empreinte de ce que l'IA lit (texte, équipement, prix arrondi, version du garde-fou) : l'analyse n'est refaite que si elle change."""
    price = listing.get("price")
    payload = {"v": AI_VERSION, "t": listing_text(listing), "p": round(price) if isinstance(price, (int, float)) else None}
    if instructions and instructions.strip() != DEFAULT_INSTRUCTIONS.strip():       # prompt personnalisé : une modification relance l'analyse (sous le plafond)
        payload["i"] = hashlib.sha1(instructions.strip().encode("utf-8")).hexdigest()[:8]
    return hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def parse_response(obj: Any) -> Optional[Dict[str, Any]]:
    """Réponse brute du modèle -> {'summary', 'facts', 'attention'} typés, ou None si inutilisable (le fournisseur suivant est alors essayé)."""
    if not isinstance(obj, dict) or not isinstance(obj.get("facts"), dict):
        return None
    facts: Dict[str, Dict[str, Any]] = {}
    for key, (_, kind) in FACT_FIELDS.items():
        raw = obj["facts"].get(key)
        if not isinstance(raw, dict):
            continue
        value = raw.get("value")
        if kind == "bool" and not isinstance(value, bool):
            value = None
        if kind == "number":
            value = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), str) else None
        conf = raw.get("confidence") if raw.get("confidence") in CONFIDENCES else "low"
        facts[key] = {"value": value, "evidence": evidence, "confidence": conf}
    attention = []
    for item in obj.get("attention") if isinstance(obj.get("attention"), list) else []:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            attention.append({"text": item["text"].strip()[:200],
                              "evidence": item.get("evidence") if isinstance(item.get("evidence"), str) else None})
    summary = obj.get("summary") if isinstance(obj.get("summary"), str) else ""
    return {"summary": summary.strip()[:MAX_SUMMARY_CHARS], "facts": facts, "attention": attention}


def _evidence_in_text(evidence: Optional[str], norm_text: str) -> bool:
    ev = normalize.normalize_text(evidence or "")
    return len(ev) >= MIN_EVIDENCE_CHARS and ev in norm_text


def regex_facts(listing: Dict[str, Any]) -> Dict[str, Any]:
    """Ce que les règles ont déjà établi (référence en cas de contradiction). Absent = les règles n'ont rien vu (≠ « faux »)."""
    m = listing.get("mentions") or {}
    facts: Dict[str, Any] = {}
    if listing.get("soh_announced") is not None and listing.get("soh_source") != "ai":
        facts["soh_pct"] = float(listing["soh_announced"])
    for key in ("battery_replaced", "heat_pump", "winter_tires", "chademo", "charging_cable"):
        if m.get(key):
            facts[key] = True
    if listing.get("accident_flags"):
        facts["accident_mentioned"] = True
    return facts


def apply_guardrails(parsed: Dict[str, Any], listing: Dict[str, Any]) -> Dict[str, Any]:
    """Ne garde que les faits PROUVÉS par le texte. Retour : {'summary', 'facts' (acceptés seulement), 'attention' (avec preuve seulement),
    'flags' (ai_unsupported_claim, ai_conflict), 'rejected' (nombre de faits écartés)}."""
    norm_text = normalize.normalize_text(listing_text(listing))
    reference = regex_facts(listing)
    accepted: Dict[str, Dict[str, Any]] = {}
    flags: List[str] = []
    rejected = 0
    for key, fact in parsed["facts"].items():
        value = fact["value"]
        if value is None:
            continue
        if not _evidence_in_text(fact["evidence"], norm_text):
            rejected += 1                                       # citation absente du texte : « inconnu », jamais accepté
            if "ai_unsupported_claim" not in flags:
                flags.append("ai_unsupported_claim")
            continue
        if key == "soh_pct":
            if not 50 <= value <= 100 or not re.search(r"\b" + re.escape(str(int(value))) + r"\b", fact["evidence"].replace(",", ".")):
                rejected += 1                                   # le nombre doit figurer dans la citation, dans une plage plausible
                if "ai_unsupported_claim" not in flags:
                    flags.append("ai_unsupported_claim")
                continue
        ref = reference.get(key)
        if ref is not None and (ref != value if key != "soh_pct" else abs(ref - value) > 1.0):
            if "ai_conflict" not in flags:                      # les règles gagnent : le fait de l'IA n'est pas retenu
                flags.append("ai_conflict")
            continue
        accepted[key] = {"value": value, "evidence": fact["evidence"].strip(), "confidence": fact["confidence"]}
    attention = [a for a in parsed["attention"] if _evidence_in_text(a["evidence"], norm_text)][:MAX_ATTENTION]
    return {"summary": parsed["summary"], "facts": accepted, "attention": attention, "flags": flags, "rejected": rejected}


def apply_to_listing(listing: Dict[str, Any], ai: Dict[str, Any]) -> Dict[str, Any]:
    """Annonce enrichie par les faits ACCEPTÉS (copie ; l'entrée n'est pas modifiée). Les scores doivent ensuite être recalculés."""
    out = dict(listing)
    mentions = dict(out.get("mentions") or {})
    flags = list(out.get("flags") or [])
    facts = ai.get("facts") or {}
    soh = facts.get("soh_pct")
    if soh and out.get("soh_announced") is None:
        out["soh_announced"], out["soh_evidence"], out["soh_source"] = soh["value"], soh["evidence"], "ai"
        flags = [f for f in flags if f != "soh_unknown"]
    for key in ("battery_replaced", "heat_pump", "winter_tires", "chademo", "charging_cable"):
        if facts.get(key, {}).get("value") is True:
            mentions[key] = True
    if facts.get("accident_mentioned", {}).get("value") is True and "ai_accident_mentioned" not in flags:
        flags.append("ai_accident_mentioned")
    for f in ai.get("flags") or []:
        if f not in flags:
            flags.append(f)
    out["mentions"], out["flags"] = mentions, flags
    return out
