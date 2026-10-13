"""Tests de la logique pure de `truth_candidates` (notation et tri) — aucune base requise."""
from datetime import datetime, timezone

from backend.scripts import truth_candidates as tc


def row(**kw):
    base = {"id": "d1", "status": "analyzed", "verdict": "FAIR", "initial_verdict": "FAIR", "tier3_trigger": None,
            "manual_analysis_overrides": None, "manual_classification": None, "is_purchased": False,
            "user_msgs": 0, "requal_applied": False, "favorite": False,
            "timestamp": datetime(2026, 10, 1, tzinfo=timezone.utc)}
    base.update(kw)
    return base


class TestScore:
    def test_no_human_trace_scores_zero(self):
        assert tc.score_signals(row()) == (0, [])

    def test_manual_override_is_the_strongest_signal(self):
        assert tc.score_signals(row(manual_analysis_overrides={"brand": "Guerrilla"})) == (5, ["override"])
        assert tc.score_signals(row(manual_classification="guitare.electrique"))[1] == ["override"]

    def test_empty_override_object_is_not_a_signal(self):
        assert tc.score_signals(row(manual_analysis_overrides={})) == (0, [])

    def test_applied_requalification_purchase_and_favorite(self):
        score, signals = tc.score_signals(row(requal_applied=True, is_purchased=True, favorite=True))
        assert signals == ["requal", "purchased", "favorite"]
        assert score == 4 + 3 + 1

    def test_rescued_means_rejected_by_gatekeeper_but_analyzed_anyway(self):
        assert tc.score_signals(row(initial_verdict="REJECTED_ITEM", status="analyzed"))[1] == ["rescued"]
        assert tc.score_signals(row(initial_verdict="REJECTED_ITEM", status="rejected")) == (0, [])
        # BAD_DEAL n'est pas un vrai rejet de fond (voir CLAUDE.md) : ne compte pas.
        assert tc.score_signals(row(initial_verdict="BAD_DEAL", status="analyzed")) == (0, [])

    def test_chat_weight_grows_with_the_number_of_user_messages(self):
        assert tc.score_signals(row(user_msgs=1)) == (1, ["chat"])
        assert tc.score_signals(row(user_msgs=2)) == (1, ["chat"])
        assert tc.score_signals(row(user_msgs=3)) == (2, ["chat"])

    def test_signals_come_back_in_display_order(self):
        _, signals = tc.score_signals(row(favorite=True, user_msgs=5, is_purchased=True, requal_applied=True))
        assert signals == ["requal", "purchased", "chat", "favorite"]


class TestRank:
    def test_sorted_by_score_then_expert_then_recency(self):
        rows = [
            row(id="faible", favorite=True),
            row(id="fort", manual_classification="x"),
            row(id="egal_sans_t3", is_purchased=True, timestamp=datetime(2026, 10, 9, tzinfo=timezone.utc)),
            row(id="egal_avec_t3", is_purchased=True, tier3_trigger="Prix élevé"),
            row(id="rien"),
        ]
        assert [r["id"] for r in tc.rank(rows, limit=10)] == ["fort", "egal_avec_t3", "egal_sans_t3", "faible"]

    def test_limit_and_t3_only(self):
        rows = [row(id="a", is_purchased=True, tier3_trigger="x"), row(id="b", is_purchased=True),
                row(id="c", manual_classification="y", tier3_trigger="x")]
        assert [r["id"] for r in tc.rank(rows, limit=1)] == ["c"]
        assert [r["id"] for r in tc.rank(rows, limit=10, t3_only=True)] == ["c", "a"]

    def test_summarize_counts_signals_and_expert_overlap(self):
        counts, with_t3 = tc.summarize([row(is_purchased=True, tier3_trigger="x"), row(is_purchased=True), row()])
        assert counts["purchased"] == 2
        assert with_t3["purchased"] == 1
