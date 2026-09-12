"""
Diagnostic one-off en lecture seule (aucune écriture Firestore, aucun redémarrage de service) —
répond à deux questions du bilan coûts (2026-09-12) restées ouvertes après le run #421 et la
mesure de cache du 2026-09-09 :

1. Cache Gemini réel (Chantier 0.b). La seule mesure existante (JOURNAL.md 2026-09-09) portait
   sur 78 appels seulement (Tier 1 à 0%, Tier 2 à 17,5%) — trop petit pour trancher si le
   correctif (`sort_keys=True` + réordonnancement du prompt T3, JOURNAL.md 2026-09-07) apporte un
   vrai gain. Ce script parse `journalctl -u guitare-hunter` (tout l'historique disponible sur le
   serveur) pour les lignes `[tokens]` déjà émises par `analyzer.py::_call_gemini_json`, sur un
   échantillon bien plus large. Ne touche jamais à la facture Gemini elle-même (contaminée par
   les runs de benchmark sur la même clé API, cf. Chantiers D/F) — uniquement les logs du service
   de production `guitare-hunter`, où les scripts de benchmark n'écrivent jamais (ils tournent en
   SSH dans un répertoire scratch séparé, jamais dans ce service systemd).

2. Volume/doublons (Chantier 0.a, run #421). Les 1377 "annonces" comptées dans la fenêtre de
   facturation (1-7 sept 2026) l'ont été via le champ `timestamp` — qui est réécrit à CHAQUE
   ré-analyse (`repository.py::update_deal_data_and_analysis`, "timestamp": SERVER_TIMESTAMP),
   pas seulement à la création (`create_new_deal`). Une annonce déjà connue dont le prix a baissé
   pendant la fenêtre compte donc comme "nouvelle" dans le comptage original. Ce script recompte
   la même fenêtre en isolant les documents portant `original_price`/`price_drop_amount` — un
   marqueur écrit UNIQUEMENT par `bot.py::handle_deal_found()` sur le chemin de ré-analyse par
   baisse de prix (jamais à la création, `bot.py` lignes ~371-373) — pour donner une borne basse
   du nombre de "fausses nouvelles annonces" dans le comptage original. Borne basse seulement :
   une ré-analyse manuelle (bouton "Ré-analyser", `update_deal_analysis()`) réécrit aussi
   `timestamp` sans laisser ce marqueur précis.

Usage : python -m backend.scripts.analyze_cache_and_volume
"""
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())

# Même fenêtre que run_once.py (run #421, JOURNAL.md 2026-09-07) — comparaison directe.
PERIOD_START = "2026-09-01T00:00:00+00:00"
PERIOD_END = "2026-09-07T00:00:00+00:00"

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "benchmark", "results")

TOKENS_LINE_RE = re.compile(
    r"\[tokens\] model=(?P<model>\S+) images=(?P<images>\d+) in=(?P<in>\d+) "
    r"out=(?P<out>\d+) cached=(?P<cached>\d+) total=(?P<total>\d+)"
)

# Pour étiqueter les modèles connus par Tier — informatif seulement, un modèle absent de cette
# liste (ex: un ancien modèle remplacé depuis) reste affiché tel quel, groupé séparément.
TIER_LABELS = {
    "gemini-3.5-flash-lite": "Tier 1 (Portier)",
    "gemini-3.7-flash": "Tier 2 (Analyste)",
    "gemini-3.6-flash": "Tier 2 (Analyste, ancien modèle)",
    "gemini-3.1-pro-preview": "Tier 3 (Expert Pro)",
}


def analyze_cache(service_name="guitare-hunter"):
    print(f"\n{'=' * 60}\nPartie A — cache Gemini réel (journalctl -u {service_name})\n{'=' * 60}")
    try:
        proc = subprocess.run(
            ["journalctl", "-u", service_name, "--no-pager"],
            capture_output=True, text=True, timeout=120,
        )
    except FileNotFoundError:
        print("❌ journalctl introuvable sur ce serveur — impossible d'analyser le cache.")
        return {"error": "journalctl introuvable"}

    if proc.returncode != 0:
        print(f"❌ journalctl a échoué (code {proc.returncode}) : {proc.stderr.strip()[:500]}")
        print("   Cause probable : l'utilisateur SSH n'a pas les droits de lecture du journal "
              "(groupe systemd-journal/adm). Vérifier manuellement sur le serveur.")
        return {"error": f"journalctl exit {proc.returncode}", "stderr": proc.stderr.strip()[:500]}

    stats = defaultdict(lambda: {"calls": 0, "cached_hits": 0, "sum_cached_ratio": 0.0})
    for line in proc.stdout.splitlines():
        m = TOKENS_LINE_RE.search(line)
        if not m:
            continue
        model = m.group("model")
        in_tokens = int(m.group("in"))
        cached = int(m.group("cached"))
        stats[model]["calls"] += 1
        if cached > 0:
            stats[model]["cached_hits"] += 1
            stats[model]["sum_cached_ratio"] += (cached / in_tokens) if in_tokens else 0.0

    if not stats:
        print("⚠️ Aucune ligne '[tokens]' trouvée dans le journal — service jamais loggé ainsi, "
              "ou historique du journal trop court.")
        return {"error": "aucune ligne [tokens] trouvée"}

    result = {}
    for model, s in sorted(stats.items(), key=lambda kv: -kv[1]["calls"]):
        calls = s["calls"]
        hits = s["cached_hits"]
        hit_rate = round(100 * hits / calls, 1) if calls else None
        avg_ratio = round(100 * s["sum_cached_ratio"] / hits, 1) if hits else None
        result[model] = {
            "label": TIER_LABELS.get(model, "modèle non cartographié"),
            "calls": calls,
            "cached_hits": hits,
            "hit_rate_pct": hit_rate,
            "avg_cached_ratio_when_hit_pct": avg_ratio,
        }
        print(f"  {model:28s} ({TIER_LABELS.get(model, '?'):28s}) : {calls:5d} appels, "
              f"{hits:5d} avec cache ({hit_rate}%), ratio moyen cached/in quand hit = {avg_ratio}%")

    return {"by_model": result, "total_calls_parsed": sum(s["calls"] for s in stats.values())}


def analyze_volume(app_id):
    print(f"\n{'=' * 60}\nPartie B — volume/doublons (fenêtre {PERIOD_START} → {PERIOD_END})\n{'=' * 60}")
    from backend.scripts.export_neck_reset_sample import setup_firebase

    db = setup_firebase()
    period_start = datetime.fromisoformat(PERIOD_START)
    period_end = datetime.fromisoformat(PERIOD_END)

    users_ref = db.collection('artifacts').document(app_id).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"   {len(user_ids)} utilisateur(s) trouvé(s).")

    total = 0
    price_drop_reanalysis = 0
    examples = []

    for uid in user_ids:
        deals_ref = (
            db.collection('artifacts').document(app_id)
            .collection('users').document(uid).collection('guitar_deals')
        )
        for doc in deals_ref.stream():
            deal = doc.to_dict()
            ts = deal.get('timestamp')
            if ts is None or ts < period_start or ts >= period_end:
                continue
            total += 1
            has_price_drop_marker = ('original_price' in deal) or ('price_drop_amount' in deal)
            if has_price_drop_marker:
                price_drop_reanalysis += 1
                if len(examples) < 5:
                    examples.append({
                        "id": doc.id,
                        "title": deal.get("title"),
                        "original_price": deal.get("original_price"),
                        "price_drop_amount": deal.get("price_drop_amount"),
                        "price": deal.get("price"),
                    })

    pct = round(100 * price_drop_reanalysis / total, 1) if total else None
    print(f"\n📦 {total} document(s) dans la fenêtre (même comptage que le run #421, "
          f"qui en avait trouvé 1377).")
    print(f"🔁 {price_drop_reanalysis} d'entre eux ({pct}%) portent un marqueur de ré-analyse "
          f"par baisse de prix (original_price/price_drop_amount) — donc PAS de nouvelles "
          f"annonces, malgré leur `timestamp` dans la fenêtre.")
    print(f"   Borne basse : une ré-analyse manuelle (bouton \"Ré-analyser\") réécrit aussi "
          f"`timestamp` sans laisser ce marqueur précis — le vrai nombre de non-nouvelles "
          f"annonces peut être plus élevé.")
    if examples:
        print("   Exemples :")
        for ex in examples:
            print(f"     - {ex['id']} : {ex['title']} — {ex['original_price']}$ -> {ex['price']}$ "
                  f"(baisse de {ex['price_drop_amount']}$)")

    return {
        "total_docs_in_window": total,
        "price_drop_reanalysis_count": price_drop_reanalysis,
        "price_drop_reanalysis_pct": pct,
        "examples": examples,
    }


def main():
    from config import APP_ID_TARGET

    cache_result = analyze_cache()
    volume_result = analyze_volume(APP_ID_TARGET) if APP_ID_TARGET else {"error": "APP_ID_TARGET manquant"}

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(
        RESULTS_DIR, f"cache_and_volume_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"cache": cache_result, "volume": volume_result}, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nRésultats détaillés sauvegardés dans : {out_path}")


if __name__ == "__main__":
    main()
