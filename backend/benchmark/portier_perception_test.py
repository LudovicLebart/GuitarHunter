"""Test ciblé du Chantier B (CHANTIER_B_PERCEPTION_RAISONNEMENT_PLAN.md §5 point 5) : sur les
annonces réellement rejetées par le Portier de production (strate `rejet_t1` du dataset, 13
items), le Bras B (perception Qwen substituée à `_prepare_visual_parts()`, cascade de production
réelle sinon inchangée) est-il d'accord avec le Bras A (photos réelles) sur le verdict du Portier
(Tier 1) ? C'est l'axe verrou le plus à risque de l'option large retenue (§1) — le Portier filtre
aujourd'hui ~70% du volume en s'appuyant sur l'examen visuel direct du logo/de la plaque
(`prompts.json:331`), donc son comportement sous perception est ce qui compte le plus, pas le
raisonnement du Tier 3 (déjà testé par les candidats `perception_qwen`/`perception_flash_lite`).

Comparaison au verdict FRAIS de Bras A rejoué dans ce script, PAS au label de strate lui-même :
la strate reflète un rejet passé (au moment de l'échantillonnage), et rejouer `analyzer_prod`
aujourd'hui ne reproduit pas forcément le même verdict (dérive de modèle, non-déterminisme malgré
`temperature=0.1`, config par défaut différente de celle en place lors du scan initial) — comparer
Bras B au label de strate aurait mesuré cette dérive, pas un vrai désaccord Bras A/B. Les deux bras
tournent donc côte à côte, sur le même item, dans le même script.

Substitution fidèle à la prod (§1, point d'insertion technique) : `_PerceptionSubstitutedAnalyzer`
override UNIQUEMENT `_prepare_visual_parts()` (déjà extrait dans `analyzer.py` pour cet usage
exact) pour renvoyer le rapport de perception comme part texte au lieu des photos — aucun autre
changement à la cascade, aucun drapeau ajouté à `analyzer.py`.

2 paliers de longueur de consigne de perception (souple, jamais de coupe dure — §5) : mesure la
longueur réellement produite (tokens de sortie Qwen) comme covariable observée, pas la longueur
nominale demandée.

Usage :
    python -m backend.benchmark.portier_perception_test
"""
import json
import os
import time
from datetime import datetime, timezone

from backend.analyzer import DealAnalyzer
from backend.benchmark.candidates import (
    QWEN_MODEL,
    TOKENROUTER_API_KEY,
    TOKENROUTER_BASE_URL,
    _call_openai_compatible,
    _get_analyzer,
)
from backend.benchmark.perception_contract import PERCEPTION_INSTRUCTION, parse_perception_json
from backend.benchmark.run_benchmark import load_dataset

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Consignes souples (§5) : n'imposent jamais de coupe dure, seulement une orientation de
# verbosité — la longueur réellement produite (tokens de sortie Qwen) est mesurée après coup,
# jamais supposée égale à la consigne.
LENGTH_TIERS = {
    "court": (
        "\n\nConsigne de longueur : réponds de façon brève et concise pour chaque champ "
        "(l'essentiel en quelques mots), sans détailler au-delà du nécessaire."
    ),
    "long": (
        "\n\nConsigne de longueur : réponds de façon exhaustive et détaillée pour chaque champ "
        "(plusieurs phrases si utile), ne néglige aucun détail observable."
    ),
}


class _PerceptionSubstitutedAnalyzer(DealAnalyzer):
    """Bras B (§5) : cascade de production réelle (`analyze_deal()`), mais `_prepare_visual_parts()`
    substitué par un rapport de perception textuel au lieu des vraies photos — seul point de
    substitution du plan (§1), zéro autre changement à `analyzer.py`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._perception_text = None

    def _prepare_visual_parts(self, listing_data):
        return [self._perception_text] if self._perception_text else []


_bras_b_analyzer = None


def _get_bras_b_analyzer():
    global _bras_b_analyzer
    if _bras_b_analyzer is None:
        _bras_b_analyzer = _PerceptionSubstitutedAnalyzer()
    return _bras_b_analyzer


def _get_perception_text(item, tier_suffix):
    instruction = PERCEPTION_INSTRUCTION + tier_suffix
    raw, usage, latency_s = _call_openai_compatible(
        instruction, item.get("image_urls", []), QWEN_MODEL, TOKENROUTER_API_KEY,
        base_url=TOKENROUTER_BASE_URL,
    )
    perception = parse_perception_json(raw)
    text = json.dumps(perception, ensure_ascii=False, sort_keys=True)
    return text, usage, latency_s


def _listing_data_for(item):
    return {
        "title": item.get("title", ""),
        "price": item.get("price", ""),
        "imageUrls": item.get("image_urls", []),
    }


def _is_rejected(verdict):
    return str(verdict or "").startswith("REJECTED")


def main():
    dataset = load_dataset()
    rejet_items = [i for i in dataset if i.get("stratum") == "rejet_t1"]
    print(f"Items strate rejet_t1 : {len(rejet_items)}")

    analyzer_a = _get_analyzer()
    analyzer_b = _get_bras_b_analyzer()

    results = []
    for item in rejet_items:
        listing_data = _listing_data_for(item)

        # Bras A rejoué maintenant (photos réelles) — l'étalon de comparaison de ce script,
        # jamais le label de strate (voir docstring).
        t0 = time.monotonic()
        result_a = analyzer_a.analyze_deal(listing_data, user_email=None)
        latency_a = time.monotonic() - t0
        verdict_a = str(result_a.get("verdict") or "")
        rejected_a = _is_rejected(verdict_a)
        print(f"  [{item['id']}] Bras A : verdict={verdict_a!r} rejeté={rejected_a} ({latency_a:.1f}s)")

        for tier_name, tier_suffix in LENGTH_TIERS.items():
            perception_text, p_usage, p_latency = _get_perception_text(item, tier_suffix)

            analyzer_b._perception_text = perception_text
            t0 = time.monotonic()
            try:
                result_b = analyzer_b.analyze_deal(listing_data, user_email=None)
                latency_b = time.monotonic() - t0
            finally:
                analyzer_b._perception_text = None  # jamais réutilisé sur un appel suivant par erreur

            verdict_b = str(result_b.get("verdict") or "")
            rejected_b = _is_rejected(verdict_b)
            agree = rejected_a == rejected_b
            perception_tokens_out = (p_usage or {}).get("output_tokens")

            print(
                f"    [{tier_name}] Bras B : verdict={verdict_b!r} rejeté={rejected_b} "
                f"accord={agree} (perception {perception_tokens_out} tok, {p_latency:.1f}s ; "
                f"cascade {latency_b:.1f}s)"
            )

            results.append({
                "id": item["id"],
                "tier": tier_name,
                "verdict_a": verdict_a,
                "rejected_a": rejected_a,
                "verdict_b": verdict_b,
                "rejected_b": rejected_b,
                "agree": agree,
                "perception_tokens_out": perception_tokens_out,
                "perception_chars": len(perception_text),
                "latency_a_s": round(latency_a, 2),
                "latency_b_s": round(latency_b, 2),
                "perception_latency_s": round(p_latency, 2),
            })

    print("\n" + "=" * 60)
    print("RÉSUMÉ — accord Bras A / Bras B sur le verdict du Portier, par palier")
    print("=" * 60)
    for tier_name in LENGTH_TIERS:
        tier_results = [r for r in results if r["tier"] == tier_name]
        n = len(tier_results)
        n_agree = sum(1 for r in tier_results if r["agree"])
        toks = [r["perception_tokens_out"] for r in tier_results if r["perception_tokens_out"] is not None]
        mean_tok = round(sum(toks) / len(toks), 1) if toks else None
        print(f"\n{tier_name} (n={n}) :")
        print(f"   accord Portier : {n_agree}/{n} ({100 * n_agree / n:.1f}%)" if n else "   n/a")
        print(f"   tokens perception (moy.) : {mean_tok}")
        disagreements = [r for r in tier_results if not r["agree"]]
        for r in disagreements:
            print(f"   ⚠ désaccord {r['id']} : A={r['verdict_a']!r} rejeté={r['rejected_a']} | B={r['verdict_b']!r} rejeté={r['rejected_b']}")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, f"portier_perception_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, ensure_ascii=False, indent=2)
    print(f"\nRésultats détaillés sauvegardés dans : {out_path}")


if __name__ == "__main__":
    main()
