"""
Tableau de bord de coût par poste — LECTURE SEULE, zéro appel IA, zéro credential (Chantier C-0).

Objectif : savoir où part la facture AVANT d'optimiser quoi que ce soit.

Sources
-------
1. **Fichiers de log serveur** (`logs/bot_*.log*`, y compris les `.gz` compressés par
   `log_retention.py`) : lignes `[tokens] model=... images=N in=... out=... cached=... total=...`
   émises par `analyzer.py::_call_gemini_json` (T1 miroir / T2 / T3) — et par
   `_call_openai_compatible_json` (Qwen/TokenRouter) une fois le patch fourni appliqué.
   `total - in - out` = tokens de raisonnement (facturés comme de la sortie, non logués à part).
2. **Optionnel : export CSV de facturation Google Cloud** (`--billing-csv`, Billing > Rapports >
   regrouper par Service puis SKU > Télécharger CSV, sur la MÊME période que `--days`).
   Donne le réel facturé ; la différence avec le coût reconstruit depuis les logs backend est
   attribuée au **chat** (dont l'usage n'est logué que dans la console du navigateur) + tout appel
   non instrumenté.

Usage (depuis la racine du dépôt, sur le serveur de prod — même cwd que le bot)
-------------------------------------------------------------------------------
    python backend/scripts/cost_dashboard.py # 14 derniers jours
    python backend/scripts/cost_dashboard.py --days 30
    python backend/scripts/cost_dashboard.py --days 30 --billing-csv facture_sept.csv
    python backend/scripts/cost_dashboard.py --json backend/benchmark/results/cost_dashboard.json
    python backend/scripts/cost_dashboard.py --log-dir /chemin/vers/logs --user abcd1234

Tarifs : table `PRICING` ci-dessous ($/1M tokens), à tenir à jour. Surcharge possible sans toucher
au code : `--pricing-json prix.json` au même format.
"""
import argparse
import csv
import glob
import gzip
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, date, timedelta

# ---------------------------------------------------------------------------
# Tarifs ($ par million de tokens). `cached` = facteur appliqué aux tokens lus depuis le cache
# implicite (ils sont INCLUS dans `in`). `from`/`until` = validité (date incluse).
# Sources : analyze_funnel_by_user.py (t1/t2), JOURNAL 2026-09-06 (3.7-flash), 2026-07-08 (3.1-pro),
# OpenRouter (qwen3.8-flash). À revérifier : tarif réel TokenRouter (endpoint /api/pricing).
# ---------------------------------------------------------------------------
PRICING = {
    "gemini-3.5-flash-lite": [{"in": 0.30, "out": 2.50, "cached": 0.10}],
    "gemini-3.7-flash": [
        {"in": 0.75, "out": 3.75, "cached": 0.10, "until": "2026-12-31"},
        {"in": 1.50, "out": 7.50, "cached": 0.10, "from": "2027-01-01"},
    ],
    "gemini-3.6-flash": [{"in": 1.50, "out": 7.50, "cached": 0.10}],
    "gemini-3.1-pro-preview": [{"in": 2.00, "out": 12.00, "cached": 0.25}],
    "qwen/qwen3.8-flash": [{"in": 0.15, "out": 0.47, "cached": 0.10}],
    "qwen3-vl:8b": [{"in": 0.0, "out": 0.0, "cached": 0.0}], # Ollama local (Dell)
    "qwen3-vl:4b": [{"in": 0.0, "out": 0.0, "cached": 0.0}],
}

# Libellé de poste par modèle (le même modèle peut changer de rôle : à ajuster si config.py bouge).
ROLE = {
    "qwen/qwen3.8-flash": "T1 Portier (Qwen)",
    "gemini-3.5-flash-lite": "T1 miroir / repli (Flash-Lite)",
    "gemini-3.7-flash": "T2 Analyste",
    "gemini-3.6-flash": "T2 Analyste (ancien)",
    "gemini-3.1-pro-preview": "T3 Expert Pro",
    "qwen3-vl:8b": "Local (Dell)",
    "qwen3-vl:4b": "Local (Dell)",
}

LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,.]\d+ - (?P<logger>.*?) - \w+ - .*?"
    r"\[tokens\] model=(?P<model>\S+) images=(?P<images>\d+) in=(?P<inp>\d+) "
    r"out=(?P<out>\d+) cached=(?P<cached>\d+) total=(?P<total>\d+)"
)

# Colonnes possibles d'un export CSV Google Cloud Billing (FR / EN).
BILLING_SERVICE_COLS = ("Service description", "Description du service", "Service", "service.description")
BILLING_SKU_COLS = ("SKU description", "Description du code SKU", "SKU", "sku.description")
BILLING_COST_COLS = ("Cost ($)", "Cost", "Coût ($)", "Coût", "Subtotal ($)", "Sous-total ($)", "cost")


def price_for(model, day, pricing):
    for tier in pricing.get(model, []):
        start = date.fromisoformat(tier["from"]) if "from" in tier else date.min
        end = date.fromisoformat(tier["until"]) if "until" in tier else date.max
        if start <= day <= end:
            return tier
    return None


def iter_log_lines(log_dir, user_prefix):
    base = f"bot_{user_prefix}" if user_prefix else "bot_"
    files = sorted(glob.glob(os.path.join(log_dir, f"{base}*.log*")))
    for path in files:
        opener = gzip.open if path.endswith(".gz") else open
        try:
            with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if "[tokens]" in line:
                        yield line
        except OSError as e:
            print(f"⚠️ Lecture impossible : {path} ({e})", file=sys.stderr)
    if not files:
        print(f"⚠️ Aucun fichier de log trouvé dans {log_dir} (motif {base}*.log*)", file=sys.stderr)


def parse_calls(log_dir, user_prefix, since):
    calls, unparsed = [], 0
    for line in iter_log_lines(log_dir, user_prefix):
        m = LINE_RE.search(line)
        if not m:
            unparsed += 1
            continue
        ts = datetime.strptime(m["ts"], "%Y-%m-%d %H:%M:%S")
        if ts < since:
            continue
        inp, out, total = int(m["inp"]), int(m["out"]), int(m["total"])
        calls.append({
            "ts": ts, "day": ts.date(), "model": m["model"], "images": int(m["images"]),
            "in": inp, "out": out, "cached": int(m["cached"]),
            "thoughts": max(0, total - inp - out),
        })
    return calls, unparsed


def cost_of(call, pricing, as_of=None):
    tier = price_for(call["model"], as_of or call["day"], pricing)
    if tier is None:
        return None
    uncached = call["in"] - call["cached"]
    return (uncached * tier["in"]
            + call["cached"] * tier["in"] * tier["cached"]
            + (call["out"] + call["thoughts"]) * tier["out"]) / 1e6


def fit_tokens_per_image(calls):
    """Moindres carrés in = a + b × images. b = coût réel d'une photo en tokens chez vous,
    a = bloc de prompt + texte d'annonce. None si les images ne varient pas assez."""
    pts = [(c["images"], c["in"]) for c in calls]
    n = len(pts)
    if n < 10:
        return None
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    if sxx < 1e-9:
        return None
    b = sum((x - mx) * (y - my) for x, y in pts) / sxx
    return {"prompt_tokens": my - b * mx, "tokens_per_image": b, "n": n}


def read_billing_csv(path):
    by_service, by_sku = defaultdict(float), defaultdict(float)
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        svc = next((c for c in BILLING_SERVICE_COLS if c in cols), None)
        sku = next((c for c in BILLING_SKU_COLS if c in cols), None)
        cost = next((c for c in BILLING_COST_COLS if c in cols), None)
        if not (svc and cost):
            raise SystemExit(f"CSV de facturation non reconnu. Colonnes trouvées : {cols}")
        for row in reader:
            raw = (row.get(cost) or "").replace("$", "").replace(" ", "").replace(" ", "").replace(",", ".")
            try:
                value = float(raw)
            except ValueError:
                continue
            by_service[row[svc]] += value
            if sku:
                by_sku[(row[svc], row[sku])] += value
    return by_service, by_sku


def fmt_money(x):
    return f"{x:8.2f} $" if x is not None else " n/d"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--log-dir", default=os.path.join(os.getcwd(), "logs"))
    ap.add_argument("--user", default=None, help="préfixe d'UID (8 caractères) pour un seul utilisateur")
    ap.add_argument("--billing-csv", default=None)
    ap.add_argument("--pricing-json", default=None)
    ap.add_argument("--json", default=None, help="écrit aussi le résumé en JSON à ce chemin")
    args = ap.parse_args()

    pricing = dict(PRICING)
    if args.pricing_json:
        with open(args.pricing_json, encoding="utf-8") as fh:
            pricing.update(json.load(fh))

    since = datetime.now() - timedelta(days=args.days)
    calls, unparsed = parse_calls(args.log_dir, args.user, since)
    if not calls:
        print("Aucun appel [tokens] sur la période. Vérifier --log-dir / --days.")
        return

    first_day, last_day = min(c["day"] for c in calls), max(c["day"] for c in calls)
    span_days = max(1, (last_day - first_day).days + 1)

    per_model = defaultdict(lambda: {"calls": 0, "images": 0, "in": 0, "cached": 0, "out": 0,
                                     "thoughts": 0, "cost": 0.0, "cost_2027": 0.0, "unpriced": 0})
    per_day = defaultdict(float)
    for c in calls:
        agg = per_model[c["model"]]
        for k in ("images", "in", "cached", "out", "thoughts"):
            agg[k] += c[k]
        agg["calls"] += 1
        cost = cost_of(c, pricing)
        cost_2027 = cost_of(c, pricing, as_of=date(2027, 1, 1))
        if cost is None:
            agg["unpriced"] += 1
            continue
        agg["cost"] += cost
        agg["cost_2027"] += cost_2027 or 0.0
        per_day[c["day"]] += cost

    backend_total = sum(a["cost"] for a in per_model.values())
    to_month = 30 / span_days

    print("=" * 96)
    print(f"COÛT PAR POSTE — logs backend du {first_day} au {last_day} ({span_days} j, {len(calls)} appels)")
    if unparsed:
        print(f"⚠️ {unparsed} ligne(s) [tokens] non reconnues (format différent : chat ? autre logger ?)")
    print("=" * 96)
    print(f"{'Poste':34s}{'appels':>8s}{'img/app':>8s}{'in moy':>9s}{'cache':>7s}{'raison.':>9s}"
          f"{'période':>10s}{'/mois':>10s}")
    for model, a in sorted(per_model.items(), key=lambda kv: -kv[1]["cost"]):
        label = ROLE.get(model, model)
        n = a["calls"]
        cache_pct = 100 * a["cached"] / a["in"] if a["in"] else 0
        out_total = a["out"] + a["thoughts"]
        think_pct = 100 * a["thoughts"] / out_total if out_total else 0
        print(f"{label[:33]:34s}{n:8d}{a['images'] / n:8.1f}{a['in'] / n:9.0f}{cache_pct:6.0f}%{think_pct:8.0f}%"
              f"{fmt_money(a['cost'] if not a['unpriced'] else None):>10s}{fmt_money(a['cost'] * to_month):>10s}")
        if a["unpriced"]:
            print(f" ↳ ⚠️ modèle absent de PRICING ({a['unpriced']} appels non chiffrés) : {model}")
    print("-" * 96)
    print(f"{'TOTAL backend (T1+miroir+T2+T3)':34s}{'':51s}{fmt_money(backend_total):>10s}"
          f"{fmt_money(backend_total * to_month):>10s}")

    # Projection 2027 (Gemini 3.7 Flash double de prix au 01/01/2027)
    total_2027 = sum(a["cost_2027"] for a in per_model.values())
    if abs(total_2027 - backend_total) > 1e-6:
        print(f"{' … même volume aux tarifs 2027':34s}{'':51s}{fmt_money(total_2027):>10s}"
              f"{fmt_money(total_2027 * to_month):>10s}")

    # Lecture : raisonnement et photos
    print("\nLECTURE")
    for model, a in per_model.items():
        out_total = a["out"] + a["thoughts"]
        if out_total and a["thoughts"] / out_total > 0.5:
            print(f"• {ROLE.get(model, model)} : {100 * a['thoughts'] / out_total:.0f}% de la sortie facturée est du "
                  f"RAISONNEMENT → régler thinking_budget avant de compresser la réponse.")
    for model in per_model:
        fit = fit_tokens_per_image([c for c in calls if c["model"] == model])
        if fit:
            print(f"• {ROLE.get(model, model)} : ≈ {fit['tokens_per_image']:.0f} tokens/photo, "
                  f"≈ {fit['prompt_tokens']:.0f} tokens de prompt+annonce (régression sur {fit['n']} appels).")

    # Jours les plus chers
    print("\nJOURS LES PLUS CHERS (backend)")
    for d, v in sorted(per_day.items(), key=lambda kv: -kv[1])[:5]:
        print(f" {d} {v:6.3f} $")

    # Facturation réelle
    billing = None
    if args.billing_csv:
        by_service, by_sku = read_billing_csv(args.billing_csv)
        billing = {"by_service": dict(by_service)}
        print("\n" + "=" * 96)
        print(f"FACTURE RÉELLE ({os.path.basename(args.billing_csv)}) — vérifier qu'elle couvre la même période")
        print("=" * 96)
        for s, v in sorted(by_service.items(), key=lambda kv: -kv[1]):
            if abs(v) >= 0.005:
                print(f" {s[:60]:60s}{v:10.2f} $")
        gemini = sum(v for s, v in by_service.items()
                     if any(k in s.lower() for k in ("gemini", "generative language", "vertex ai")))
        if gemini:
            # Seuls les modèles Gemini sont facturés par Google : Qwen (TokenRouter) et le local exclus.
            backend_gemini = sum(a["cost"] for m, a in per_model.items() if m.startswith("gemini"))
            residual = gemini - backend_gemini
            billing.update({"gemini_billed": gemini, "backend_gemini": backend_gemini,
                            "residual_chat_and_untracked": residual})
            print(f"\n Gemini facturé {gemini:10.2f} $")
            print(f" − Gemini reconstruit (logs backend) {backend_gemini:10.2f} $")
            print(f" = CHAT + non instrumenté {residual:10.2f} $ "
                  f"({100 * residual / gemini:.0f}% de la part Gemini)")
            if residual < 0:
                print(" ⚠️ Résidu négatif : période du CSV ≠ période des logs, ou tarifs PRICING trop hauts.")
        top_sku = sorted(by_sku.items(), key=lambda kv: -kv[1])[:8]
        if top_sku:
            print("\n SKU les plus chers :")
            for (s, k), v in top_sku:
                print(f" {v:8.2f} $ {s[:25]} / {k[:55]}")

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({
                "period": {"from": str(first_day), "to": str(last_day), "days": span_days},
                "per_model": {m: {**a, "role": ROLE.get(m, m)} for m, a in per_model.items()},
                "backend_total": backend_total,
                "backend_monthly_estimate": backend_total * to_month,
                "backend_monthly_estimate_2027": total_2027 * to_month,
                "billing": billing,
            }, fh, ensure_ascii=False, indent=2, default=str)
        print(f"\nRésumé JSON écrit : {args.json}")


if __name__ == "__main__":
    main()
