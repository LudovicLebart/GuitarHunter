"""Logique pure de `replay_t3` (cohérence, dépouillement des jugements, coût) — aucun réseau ni base."""
from backend.scripts import replay_t3 as rp


def test_stability_identical_runs_and_gaps():
    a = {"verdict": "FAIR", "brand": "Yamaha", "classification": "g.a", "deal_score": 6, "estimated_value": 100}
    b = {"verdict": "FAIR", "brand": " yamaha", "classification": "g.a", "deal_score": 6, "estimated_value": 100}
    s = rp.stability([a, b])
    assert (s["verdict"], s["brand"], s["classification"], s["deal_score_gap"], s["value_gap_pct"]) == (1, 1, 1, 0, 0)


def test_stability_detects_disagreement():
    a = {"verdict": "PEPITE", "brand": "Aria", "classification": "x", "deal_score": 9, "estimated_value": 300}
    b = {"verdict": "BAD_DEAL", "brand": "Kay", "classification": "y", "deal_score": 3, "estimated_value": 100}
    s = rp.stability([a, b])
    assert s["verdict"] == 0 and s["brand"] == 0 and s["deal_score_gap"] == 6
    assert abs(s["value_gap_pct"] - 1.0) < 1e-9


def test_stability_needs_two_valid_runs():
    assert rp.stability([{"verdict": "FAIR"}]) is None
    assert rp.stability([{"verdict": "FAIR"}, None]) is None


def test_unblind_maps_letters_back_to_models():
    j = {"identification": "A", "etat": "B", "valeur": "tie", "hallucination": "b", "overall": "A",
         "errors_a": ["x"], "errors_b": ["y"]}
    u = rp.unblind(j, a_is="claude")
    assert (u["identification"], u["etat"], u["valeur"], u["hallucination"], u["overall"]) == \
        ("claude", "gemini", "tie", "gemini", "claude")
    assert u["errors"] == {"claude": ["x"], "gemini": ["y"]}
    assert rp.unblind({"overall": "n'importe quoi"}, "gemini")["overall"] == "tie"


def test_tally_counts_per_axis():
    js = [rp.unblind({"overall": "A", "etat": "B"}, "claude"), rp.unblind({"overall": "A"}, "gemini")]
    c = rp.tally(js)
    assert c["overall"] == {"gemini": 1, "claude": 1, "tie": 0}
    assert c["etat"]["gemini"] == 1


def test_cost_uses_cache_discount():
    pricing = {"m": [{"in": 2.0, "out": 10.0, "cached": 0.1}]}
    price_for = lambda model, day, p: p[model][0]
    rows = [{"model": "m", "input_tokens": 1_000_000, "cached_tokens": 500_000, "output_tokens": 100_000}]
    assert abs(rp.cost_usd(rows, pricing, price_for, None) - (0.5 * 2 + 0.5 * 2 * 0.1 + 0.1 * 10)) < 1e-9


def test_stored_result_merges_columns_over_raw_and_flags_edits():
    deal = {"ai_analysis_raw": {"analysis": "texte", "brand": "vieux"}, "brand": "Yamaha", "deal_score": 7,
            "manual_classification": "guitare.acoustique"}
    r = rp.stored_result(deal)
    assert r["brand"] == "Yamaha" and r["analysis"] == "texte" and r["deal_score"] == 7
    assert rp.was_edited_by_user(deal) and not rp.was_edited_by_user({"manual_analysis_overrides": {}})


def test_owner_block_dedups_nothing_but_limits_and_flattens():
    assert rp.owner_block([]).startswith("(aucun")
    assert "a b" in rp.owner_block(["a\n b"])


def test_stored_gemini_only_when_raw_expert_answer():
    raw = {"tier3_trigger": "Prix élevé"}
    assert rp.use_stored_gemini(raw)
    assert not rp.use_stored_gemini(raw, fresh_gemini=True)
    assert not rp.use_stored_gemini({})                                          # pas de réponse Expert stockée
    assert not rp.use_stored_gemini({**raw, "requal_applied": True})             # requalification acceptée : réponse corrigée
    assert not rp.use_stored_gemini({**raw, "manual_analysis_overrides": {"brand": "X"}})


def test_image_url_lists_order_and_cap():
    deal = {"storage_image_urls": ["s%d" % i for i in range(12)], "image_urls": ["f1"]}
    lists = rp.image_url_lists(deal)
    assert len(lists) == 2 and len(lists[0]) == 8 and lists[1] == ["f1"] and lists[0][0] == "s0"
    assert rp.image_url_lists({"storage_image_urls": [], "image_urls": None}) == []


def test_is_contested_and_digest_text():
    from backend.scripts import replay_t3_digest as dg
    agree = {"judgments": {"gemini": [{"overall": "claude"}, {"overall": "claude"}], "claude": [{"overall": "claude"}]}}
    order_flip = {"judgments": {"gemini": [{"overall": "claude"}, {"overall": "gemini"}]}}
    split = {"judgments": {"gemini": [{"overall": "gemini"}], "claude": [{"overall": "claude"}]}}
    assert not rp.is_contested(agree) and rp.is_contested(order_flip) and rp.is_contested(split)
    row = {"id": "x", "title": "T", "gemini_stored": True, **split,
           "runs": {"gemini": [{"result": {"brand": "Aria", "verdict": "FAIR"}}], "claude": [{"result": None}]}}
    row["judgments"]["claude"][0].update(errors={"gemini": ["a inventé une fissure"], "claude": []}, explanation="e")
    txt = dg.digest_row(row)
    assert "[LITIGIEUSE]" in txt and "(échec)" in txt and "déjà stockée" in txt and "a inventé une fissure" in txt


def test_links_file_text_keeps_order_and_flags_missing():
    from backend.scripts import replay_t3_links as lk
    rows = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]
    txt = lk.format_links(rows, {"a": ("Titre A", "https://x/a")})
    assert txt.index("Titre A") < txt.index("B") and "https://x/a" in txt and "introuvable" in txt
