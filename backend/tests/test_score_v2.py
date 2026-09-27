"""Score v2: proximity 40 + savings 40 + timing 20 (spec update U1)."""
from datetime import date

from engine.overlaps import score_v2, shift_possible


def test_breakdown_sums_to_score_and_caps_at_100():
    s, b = score_v2("crossing", 0, 10_000_000, 1_000_000, 24, False)
    assert b == {"proximity": 40.0, "savings": 40.0, "timing": 20.0} and s == 100.0
    s, b = score_v2("shared_site", 4.82, 595_000, 23_787_423, 24, False)
    assert round(b["proximity"] + b["savings"] + b["timing"], 1) == s
    assert b["proximity"] == round(26 * (1 - 4.82 / 80), 1)
    assert b["savings"] == round(595_000 / 23_787_423 / 0.05 * 40, 1)


def test_savings_points_zero_without_budget():
    _, b = score_v2("shared_site", 2.0, 50_000, None, 6, False)
    assert b["savings"] == 0


def test_timing_partial_credit_for_shiftable_pair():
    assert score_v2("shared_crews", 20, 0, None, 0, True)[1]["timing"] == 6.0
    assert score_v2("shared_crews", 20, 0, None, 0, False)[1]["timing"] == 0.0
    assert score_v2("shared_crews", 20, 0, None, 6, False)[1]["timing"] == 10.0


def test_shift_possible_never_uses_the_past():
    today = date(2026, 9, 26)
    a = {"start": "2027-01-01", "end": "2027-06-01"}
    b = {"start": "2027-10-01", "end": "2028-03-01"}
    assert shift_possible(a, b, today)  # move A 6 months later
    old = {"start": "2023-01-01", "end": "2024-01-01"}
    assert not shift_possible(old, {"start": "2025-06-01", "end": "2025-09-01"}, today)
