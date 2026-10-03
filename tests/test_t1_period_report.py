"""Tests de la logique pure du rapport T1 par période (aucune base requise)."""
from datetime import datetime, timezone

from backend.scripts import t1_period_report as rep


def utc(text):
    return rep.parse_instant(text)


class TestPeriods:
    def test_parse_instant_accepts_z_suffix(self):
        assert utc("2026-10-02T13:00Z") == datetime(2026, 10, 2, 13, 0, tzinfo=timezone.utc)

    def test_boundaries_are_sorted_and_labels_aligned(self):
        boundaries, labels = rep.build_periods([("2026-10-02T21:17Z", "B"), ("2026-10-02T13:00Z", "A")])
        assert boundaries == [utc("2026-10-02T13:00Z"), utc("2026-10-02T21:17Z")]
        assert labels == [rep.FIRST_LABEL, "A", "B"]

    def test_period_label_picks_the_period_containing_the_instant(self):
        boundaries, labels = rep.build_periods(rep.DEFAULT_CUTS)
        assert rep.period_label(boundaries, labels, utc("2026-10-02T12:55Z")) == "ctx 4096"
        assert rep.period_label(boundaries, labels, utc("2026-10-02T13:00Z")) == "ctx 8192, ancien prompt"
        assert rep.period_label(boundaries, labels, utc("2026-10-02T21:17Z")) == "ctx 8192, nouveau prompt"

    def test_case_fragment_uses_parameters_not_interpolation(self):
        boundaries, labels = rep.build_periods(rep.DEFAULT_CUTS)
        sql, params = rep._case("created_at", boundaries, labels)
        assert sql.count("%s") == len(params) == 2 * len(boundaries) + 1
        assert "2026" not in sql and "prompt" not in sql

    def test_defaults_use_utc_not_local_time(self):
        # 17:17 heure de Montréal (EDT, UTC-4) = 21:17Z
        assert utc("2026-10-02T21:17Z").hour == 21
        assert dict(rep.DEFAULT_CUTS)["2026-10-02T21:17Z"] == "ctx 8192, nouveau prompt"


class TestFormatting:
    def test_pct(self):
        assert rep.pct(1, 4) == "25 %"
        assert rep.pct(0, 0) == "—"
