"""Effet de la base de connaissances sur le Portier T1 : compare deux rejeux du MÊME lot d'annonces
(STRATEGIE_IA.md §3.6, rejeu de non-régression) — sans base, puis avec base.

Lit seulement des fichiers JSON produits par `compare_qwen_local_vs_prod.py` : aucune base, aucun réseau, aucun
appel IA, 0 $. Le modèle local n'est PAS déterministe : deux rejeux SANS base donnent déjà quelques verdicts
différents. Pour ne pas prendre ce bruit pour un effet de la base, fournir un 2e rejeu sans base (`--baseline2`) :
seuls les changements qui dépassent ce bruit comptent.

    # 1. le Dell doit être allumé ; à lancer sur le serveur, même DATABASE_URL que le bot
    python -m backend.scripts.compare_qwen_local_vs_prod --simplified-prompt --limit 300 --out kb_sans_1.json
    python -m backend.scripts.compare_qwen_local_vs_prod --simplified-prompt --limit 300 --out kb_sans_2.json
    python -m backend.scripts.compare_qwen_local_vs_prod --simplified-prompt --limit 300 --with-knowledge --out kb_avec.json
    # 2. comparaison (aucun appel IA)
    python backend/scripts/compare_knowledge_effect.py --baseline backend/benchmark/results/kb_sans_1.json \\
        --baseline2 backend/benchmark/results/kb_sans_2.json --with-kb backend/benchmark/results/kb_avec.json

Critère de non-régression (rejeter à tort une pépite coûte plus cher que d'en laisser passer une à l'Analyste) :
parmi les annonces où la base a injecté des fiches, on compte les NOUVEAUX REJETS NUISIBLES = acceptés sans base,
rejetés avec base, ALORS QUE le verdict cloud ne les rejette pas. Un nouveau rejet que le cloud confirme n'est pas une
erreur (le Portier se rapproche du cloud). Avec `--baseline2`, le critère est « pas plus de rejets nuisibles que le
bruit du modèle sur ces mêmes annonces » (le modèle local n'est pas déterministe : exiger 0 serait inatteignable) ;
sans `--baseline2`, il faut 0. Chaque rejet nuisible est listé : à relire un par un pour savoir si une fiche précise
en est la cause. Si le critère est tenu, la commande pour valider la version est affichée.
"""
import argparse
import json
import sys

REJECTION_VERDICTS = {"BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE"}   # même liste que T1_REJECTION_VERDICTS


def is_rejected(verdict):
    return (verdict or "").upper() in REJECTION_VERDICTS


THINKING_TAG = "qwen3-vl:8b"      # variante Thinking : écrit son raisonnement, laisse `content` vide (réponses vides)
MAX_FAILURE_RATE = 0.10


def load(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if "per_listing" not in data:
        raise SystemExit(f"{path} : pas de « per_listing » — relancer compare_qwen_local_vs_prod avec la version à jour")
    if data.get("model") == THINKING_TAG:
        raise SystemExit(f"{path} : modèle « {THINKING_TAG} » = variante THINKING (réponses vides, latences > 100 s). "
                         f"Rejouer avec --model qwen3-vl:8b-instruct, le modèle de la prod.")
    n_ok, n_failed = len(data["per_listing"]), len(data.get("failed_calls") or [])
    if n_ok + n_failed and n_failed / (n_ok + n_failed) > MAX_FAILURE_RATE:
        raise SystemExit(f"{path} : {n_failed} appel(s) en échec sur {n_ok + n_failed} (> {int(MAX_FAILURE_RATE * 100)} %) — "
                         f"résultats inexploitables, vérifier le Dell (ollama ps, modèle chargé) avant de rejouer.")
    return data, {e["id"]: e for e in data["per_listing"]}


def flips(a, b):
    """Annonces communes dont la décision (rejet / non-rejet) diffère entre deux rejeux."""
    return [(i, a[i], b[i]) for i in sorted(set(a) & set(b)) if is_rejected(a[i]["local_verdict"]) != is_rejected(b[i]["local_verdict"])]


def analyze(baseline, with_kb, baseline2=None):
    """Compare les décisions. `baseline`, `with_kb`, `baseline2` : {id: entrée per_listing}."""
    common = sorted(set(baseline) & set(with_kb))
    injected = [i for i in common if with_kb[i].get("kb_ids")]
    injected_set = set(injected)
    new_rejections = [i for i in common if not is_rejected(baseline[i]["local_verdict"]) and is_rejected(with_kb[i]["local_verdict"])]
    lifted = [i for i in common if is_rejected(baseline[i]["local_verdict"]) and not is_rejected(with_kb[i]["local_verdict"])]

    def agreement(entries, ids):
        if not ids:
            return None
        return sum(1 for i in ids if is_rejected(entries[i]["cloud_verdict"]) == is_rejected(entries[i]["local_verdict"])) / len(ids)

    def cloud_rejects(i):
        return is_rejected(with_kb[i]["cloud_verdict"])

    new_injected = [i for i in new_rejections if i in injected_set]
    lifted_injected = [i for i in lifted if i in injected_set]
    harmful = [i for i in new_injected if not cloud_rejects(i)]        # rejeté à tort : le cloud ne rejette pas
    gains = [i for i in lifted_injected if not cloud_rejects(i)]       # rejet à tort levé : le cloud ne rejetait pas non plus

    noise = flips(baseline, baseline2) if baseline2 else None
    noise_harmful = None
    if baseline2:
        # même mesure que `harmful`, entre deux rejeux SANS base, sur les MÊMES annonces (celles où la base injecte)
        noise_harmful = [i for i in injected if i in baseline2
                         and not is_rejected(baseline[i]["local_verdict"]) and is_rejected(baseline2[i]["local_verdict"])
                         and not cloud_rejects(i)]
    report = {
        "n_common": len(common), "n_injected": len(injected),
        "new_rejections": new_rejections, "lifted_rejections": lifted,
        "new_rejections_injected": new_injected,
        "lifted_injected": lifted_injected,
        "harmful_new_injected": harmful, "neutral_new_injected": [i for i in new_injected if cloud_rejects(i)],
        "gains_injected": gains,
        "noise_harmful_injected": noise_harmful,
        "agreement_baseline_injected": agreement(baseline, injected),
        "agreement_with_kb_injected": agreement(with_kb, injected),
        "noise_flips": [i for i, _, _ in noise] if noise is not None else None,
        "n_noise_common": len(set(baseline) & set(baseline2)) if baseline2 else None,
    }
    allowed = len(noise_harmful) if noise_harmful is not None else 0
    report["passes"] = len(harmful) <= allowed
    return report


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.1f} %"


def print_report(report, baseline, with_kb, kb_version=None):
    print(f"Annonces comparables : {report['n_common']}   |   avec fiches injectées : {report['n_injected']}")
    if report["noise_flips"] is not None:
        print(f"Bruit du modèle (2 rejeux SANS base) : {len(report['noise_flips'])} décision(s) différente(s) sur "
              f"{report['n_noise_common']} — à retrancher de ce qui suit")
    print(f"\nNOUVEAUX REJETS (accepté sans base → rejeté avec) : {len(report['new_rejections'])}, dont "
          f"{len(report['new_rejections_injected'])} là où la base a injecté des fiches")
    print(f"   parmi ces derniers : {len(report['neutral_new_injected'])} confirmé(s) par le cloud (pas une erreur), "
          f"{len(report['harmful_new_injected'])} NUISIBLE(S) (le cloud ne rejette pas)")
    if report["noise_harmful_injected"] is not None:
        print(f"   même mesure entre 2 rejeux SANS base, sur ces mêmes annonces : {len(report['noise_harmful_injected'])} "
              f"← seuil toléré")
    else:
        print("   pas de 2e rejeu sans base (--baseline2) : seuil toléré = 0")
    print(f"REJETS LEVÉS (rejeté sans base → accepté avec)    : {len(report['lifted_rejections'])}, dont "
          f"{len(report['lifted_injected'])} là où la base a injecté des fiches "
          f"({len(report['gains_injected'])} où le cloud ne rejetait pas non plus : vrais gains)")
    print(f"Accord avec le verdict cloud sur les annonces avec fiches : {_pct(report['agreement_baseline_injected'])} "
          f"sans base → {_pct(report['agreement_with_kb_injected'])} avec")

    def detail(title, ids):
        if not ids:
            return
        print(f"\n== {title} ==")
        for i in ids:
            e0, e1 = baseline[i], with_kb[i]
            print(f"- {i} : {(e1.get('title') or '')[:70]}")
            print(f"    cloud={e1['cloud_verdict']} | sans base={e0['local_verdict']} | avec base={e1['local_verdict']}"
                  f" | fiches : {', '.join(e1.get('kb_names') or []) or '(aucune)'}")
            if e1.get("link"):
                print(f"    lien : {e1['link']}")
            if e1.get("local_reasoning"):
                print(f"    raisonnement (avec base) : {str(e1['local_reasoning'])[:240]}")

    detail("REJETS NUISIBLES AVEC FICHES — à relire un par un (la fiche est-elle en cause ?)", report["harmful_new_injected"])
    detail("NOUVEAUX REJETS CONFIRMÉS PAR LE CLOUD (avec fiches)", report["neutral_new_injected"])
    detail("NOUVEAUX REJETS SANS FICHE INJECTÉE (bruit du modèle)", [i for i in report["new_rejections"] if i not in report["new_rejections_injected"]])
    detail("REJETS LEVÉS (gain potentiel : marque obscure reconnue ?)", report["lifted_rejections"])

    print("\n" + "=" * 70)
    if report["passes"]:
        print("✅ Critère tenu : pas plus de rejets nuisibles avec fiches que le bruit du modèle."
              if report["noise_harmful_injected"] is not None else
              "✅ Critère tenu : aucun rejet nuisible là où la base a injecté des fiches.")
        if report["harmful_new_injected"]:
            print("   ⚠️ des rejets nuisibles subsistent (dans le bruit) : les relire avant de valider.")
        if report["n_injected"] < 100:
            print(f"   ⚠️ seulement {report['n_injected']} annonces avec fiches : un écart de 1-2 cas ne prouve rien, "
                  f"rejouer sur un lot plus grand avant de généraliser.")
        if kb_version:
            print(f"   Pour valider la version {kb_version} (le Portier ne l'utilise qu'ensuite) :")
            print(f"     psql \"$DATABASE_URL\" -c \"UPDATE guitar_knowledge_versions SET validated = true WHERE version = {kb_version};\"")
            print("   puis activer avec T1_KNOWLEDGE_ENABLED=true (variable d'environnement, sans redéploiement de code).")
    else:
        print("❌ Critère NON tenu : plus de rejets nuisibles avec fiches que le bruit du modèle. Ne pas valider la version ;")
        print("   relire les cas ci-dessus, corriger ou retirer les fiches en cause, puis rejouer.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", required=True, help="rejeu SANS la base (JSON de compare_qwen_local_vs_prod)")
    ap.add_argument("--with-kb", required=True, help="rejeu AVEC la base (--with-knowledge)")
    ap.add_argument("--baseline2", default=None, help="2e rejeu SANS la base, pour mesurer le bruit du modèle")
    args = ap.parse_args()

    base_meta, baseline = load(args.baseline)
    kb_meta, with_kb = load(args.with_kb)
    if not kb_meta.get("with_knowledge"):
        raise SystemExit(f"{args.with_kb} n'a pas été produit avec --with-knowledge")
    if base_meta.get("with_knowledge"):
        raise SystemExit(f"{args.baseline} a été produit AVEC la base : la référence doit être sans")
    if base_meta.get("model") != kb_meta.get("model"):
        print(f"⚠️ modèles différents ({base_meta.get('model')} vs {kb_meta.get('model')}) : la comparaison est faussée",
              file=sys.stderr)
    baseline2 = load(args.baseline2)[1] if args.baseline2 else None
    report = analyze(baseline, with_kb, baseline2)
    print_report(report, baseline, with_kb, kb_meta.get("kb_version"))
    return 0 if report["passes"] else 1


if __name__ == "__main__":
    sys.exit(main())
