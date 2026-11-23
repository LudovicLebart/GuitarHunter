"""Leaf — niveau 3 (Expert, Claude Sonnet 5.5) : prompt, lecture de la réponse et garde-fous. Fonctions PURES.

L'Expert ne tourne qu'À LA DEMANDE (bouton « Analyse approfondie », commande `LEAF_ANALYZE`) : il reçoit les faits établis par le code
(scores, verdict, faits de l'IA niveau 2 déjà prouvés) et produit un avis argumenté, les questions à poser au vendeur, les points à inspecter
et un prix plafond. Rien n'est accepté sans garde-fou : les risques doivent citer l'annonce, le prix plafond reste dans une plage cohérente
avec le prix demandé et le marché estimé, et la question LeafSpy est ajoutée PAR LE CODE quand le SOH est inconnu."""
import json
from typing import Any, Dict, List, Optional

from backend.leaf import ai_extract, normalize

EXPERT_VERSION = 2          # 2 : photos jointes (observations)
WORTH = ("oui", "peut-etre", "non")
MAX_QUESTIONS = 8
MAX_POINTS = 8
MAX_RISKS = 5
MAX_PHOTO_NOTES = 5
MAX_EXPERT_PHOTOS = 4
LEAFSPY_QUESTION = "Pouvez-vous faire lire l'état de santé de la batterie (SOH) avec LeafSpy, ou me laisser le faire, avant que je me déplace ?"
BATTERY_PROOF_QUESTION = "Avez-vous la facture ou la garantie Nissan du remplacement de la batterie de traction (date, concessionnaire, numéro de série) ?"

# INSTRUCTIONS éditables dans l'app (`leafConfig.prompts.expert`) ; CONTRAT (forme JSON, règle des photos) toujours ajouté par le code.
DEFAULT_INSTRUCTIONS = """Tu es un expert en achat de Nissan Leaf d'occasion au Québec. L'acheteur cherche une voiture pour environ 50 km par jour, hiver compris.
On te donne l'annonce et des FAITS ÉTABLIS PAR LE CODE (scores, verdict, faits déjà prouvés par citation) : traite-les comme exacts, sans les refaire.

Règles strictes :
- N'invente aucun fait sur la voiture. Ce que l'annonce ne dit pas est « inconnu » : dis-le, et transforme-le en question pour le vendeur.
- Chaque risque doit citer l'annonce MOT POUR MOT ("evidence"). Sans citation exacte, ne le mentionne pas.
- "price_ceiling" : le prix maximum raisonnable à payer, en dollars. Appuie-toi sur le prix de marché estimé s'il est fourni ; sinon laisse "amount": null.
- "worth_visiting" : "oui", "peut-etre" ou "non". Un SOH inconnu n'est pas une raison de refuser : c'est une mesure à faire.
- Réponds en français."""

CONTRACT = """Réponds UNIQUEMENT avec un objet JSON :
{"opinion": "3 à 5 phrases argumentées", "worth_visiting": "oui|peut-etre|non", "seller_questions": ["..."], "inspection_points": ["..."],
 "price_ceiling": {"amount": null, "reasoning": "..."}, "risks": [{"text": "...", "evidence": "citation exacte"}],
 "photo_observations": [{"photo": 1, "text": "ce que montre la photo n°1, en une phrase"}]}

Si des PHOTOS sont jointes (« Image 1 », « Image 2 »…) : décris seulement ce qu'elles montrent de façon visible (état de la carrosserie, de l'intérieur, écran de batterie lisible), dans "photo_observations" ;
ce sont des observations à vérifier, pas des faits : ne les utilise pas comme preuve d'un risque. Sans photo jointe, laisse la liste vide.

"""

PROMPT = DEFAULT_INSTRUCTIONS + "\n\n" + CONTRACT


def row_to_listing(row: Dict[str, Any]) -> Dict[str, Any]:
    """Ligne `vehicle_deals` -> annonce au format du pipeline (champs lus par les scores, le verdict et le garde-fou)."""
    analysis = row.get("analysis") or {}
    flags = list(row.get("flags") or [])
    return {
        "id": row["id"], "title": row.get("title"), "description": row.get("description"),
        "price": float(row["price"]) if row.get("price") is not None else None,
        "year": row.get("year"), "km": row.get("km"), "trim": row.get("trim"), "location": row.get("location"),
        "seller_type": row.get("seller_type"), "battery_kwh_low": row.get("battery_kwh_low"),
        "battery_kwh_high": row.get("battery_kwh_high"), "battery_source": row.get("battery_source"),
        "soh_announced": float(row["soh_announced"]) if row.get("soh_announced") is not None else None,
        "soh_evidence": row.get("soh_evidence"), "flags": flags, "accident_flags": [f[9:] for f in flags if f.startswith("accident:")],
        "mentions": analysis.get("mentions") or {}, "winter_fit": analysis.get("winter_fit"), "equipment": analysis.get("equipment"),
        "price_fit": analysis.get("price_fit"), "verdict": row.get("verdict"), "verdict_reasons": analysis.get("verdict_reasons") or [],
        "ai": analysis.get("ai"), "photos": analysis.get("photos"), "equipment_list": [], "image_urls": list(row.get("image_urls") or []),
    }


def _battery_text(low: Any, high: Any) -> str:
    """Capacité de batterie lisible ; « inconnue » dès qu'une borne manque (jamais « None ou 24 » présenté comme un fait)."""
    if low is None or high is None:
        return "inconnue"
    return str(low) if low == high else f"{low} ou {high}"


def known_facts(listing: Dict[str, Any]) -> Dict[str, Any]:
    """Faits établis par le code, donnés à l'Expert comme exacts."""
    ai = listing.get("ai") or {}
    return {
        "annee": listing.get("year"), "version": listing.get("trim"), "km": listing.get("km"), "prix_demande": listing.get("price"),
        "ville": listing.get("location"), "vendeur": {"delr": "commerçant", "ownr": "particulier"}.get(listing.get("seller_type")),
        "batterie_kwh": _battery_text(listing.get("battery_kwh_low"), listing.get("battery_kwh_high")),
        "soh_annonce_pct": listing.get("soh_announced"), "autonomie_hiver": listing.get("winter_fit"),
        "equipement": listing.get("equipment"), "prix_marche_estime": listing.get("price_fit"),
        "verdict_du_code": listing.get("verdict"), "raisons_du_verdict": listing.get("verdict_reasons"),
        "drapeaux": listing.get("flags"),
        "faits_prouves_par_citation": {k: v.get("value") for k, v in (ai.get("facts") or {}).items()},
    }


def build_prompt(listing: Dict[str, Any], instructions: Optional[str] = None) -> str:
    return (((instructions or "").strip() or DEFAULT_INSTRUCTIONS).rstrip() + "\n\n" + CONTRACT + "FAITS ÉTABLIS PAR LE CODE :\n" + json.dumps(known_facts(listing), ensure_ascii=False, default=str)
            + "\n\nTEXTE DE L'ANNONCE :\n" + ai_extract.listing_text(listing))


def _strings(value: Any, limit: int, width: int = 220) -> List[str]:
    out: List[str] = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, str) and item.strip():
            text = item.strip()[:width]
            if text not in out:
                out.append(text)
    return out[:limit]


def apply_guardrails(raw: Any, listing: Dict[str, Any], photo_count: int = 0) -> Optional[Dict[str, Any]]:
    """Réponse brute -> avis de l'Expert ACCEPTÉ, ou None si inutilisable. Voir le docstring du module pour les garde-fous."""
    if not isinstance(raw, dict) or not isinstance(raw.get("opinion"), str) or not raw["opinion"].strip():
        return None
    norm_text = normalize.normalize_text(ai_extract.listing_text(listing))
    dropped = 0
    risks = []
    for r in raw.get("risks") if isinstance(raw.get("risks"), list) else []:
        if isinstance(r, dict) and isinstance(r.get("text"), str) and ai_extract._evidence_in_text(r.get("evidence"), norm_text):
            risks.append({"text": r["text"].strip()[:220], "evidence": r["evidence"].strip()})
        else:
            dropped += 1
    questions = _strings(raw.get("seller_questions"), MAX_QUESTIONS)
    if listing.get("soh_announced") is None and not any("leafspy" in q.lower() or "soh" in q.lower() for q in questions):
        questions = (questions[:MAX_QUESTIONS - 1]) + [LEAFSPY_QUESTION]           # garanti par le code, jamais laissé au modèle
    if listing.get("battery_kwh_low") == 24 and (listing.get("mentions") or {}).get("battery_replaced") \
            and not any("facture" in q.lower() or "garantie" in q.lower() for q in questions):
        questions = (questions[:MAX_QUESTIONS - 1]) + [BATTERY_PROOF_QUESTION]
    ceiling = raw.get("price_ceiling") if isinstance(raw.get("price_ceiling"), dict) else {}
    amount, price, fit = ceiling.get("amount"), listing.get("price"), listing.get("price_fit") or {}
    valid = isinstance(amount, (int, float)) and not isinstance(amount, bool) and isinstance(price, (int, float)) \
        and 0.4 * price <= amount <= 1.1 * price \
        and (not fit.get("expected") or amount <= 1.1 * fit["expected"])
    if isinstance(amount, (int, float)) and not valid:
        dropped += 1                                                                  # plafond incohérent : écarté, jamais affiché
    notes = []
    for n in raw.get("photo_observations") if isinstance(raw.get("photo_observations"), list) else []:
        # Une observation doit viser une photo RÉELLEMENT jointe (numéro de 1 à `photo_count`) ; sinon elle est écartée.
        if isinstance(n, dict) and isinstance(n.get("photo"), int) and not isinstance(n.get("photo"), bool) \
                and 1 <= n["photo"] <= photo_count and isinstance(n.get("text"), str) and n["text"].strip():
            notes.append({"photo": n["photo"], "text": n["text"].strip()[:200]})
        else:
            dropped += 1
    return {
        "photo_observations": notes[:MAX_PHOTO_NOTES],
        "opinion": raw["opinion"].strip()[:900],
        "worth_visiting": raw.get("worth_visiting") if raw.get("worth_visiting") in WORTH else "peut-etre",
        "seller_questions": questions,
        "inspection_points": _strings(raw.get("inspection_points"), MAX_POINTS),
        "price_ceiling": {"amount": round(amount), "basis": "marché estimé" if fit.get("expected") else "indicatif (marché insuffisant)",
                          "reasoning": str(ceiling.get("reasoning") or "")[:300]} if valid else None,
        "risks": risks[:MAX_RISKS], "dropped": dropped,
    }
