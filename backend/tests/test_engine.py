"""Windows, cost, what-if, closures, score."""
from datetime import date

from engine import closures, cost, windows
from engine.overlaps import potential_for
from engine.whatif import suggest_shift, whatif


# ---------- windows ----------
def test_overlap_months():
    a = {"start": "2024-01-01", "end": "2025-12-31"}
    b = {"start": "2024-01-01", "end": "2026-06-01"}
    assert windows.overlap_months(a, b) == 24
    assert windows.overlap_months(a, {"start": "2026-01-01", "end": "2027-01-01"}) == 0
    assert windows.overlap_months(a, {"start": "2025-06-01", "end": "2027-01-01"}) == 7


def test_desc_window_from_spend_years():
    cost_prev = {"by_year": {"previous": 10, "2024": 0}}
    w, _ = windows.desc_window(cost_prev, "2025-12-31", "line")
    assert w == {"start": "2023-01-01", "end": "2025-12-31", "source": "desc_spend_years"}
    w, _ = windows.desc_window({"by_year": {"previous": 0, "2024": 0, "2025": 5}}, "2027-12-31", "line")
    assert w["start"] == "2025-01-01"


def test_estimated_and_invalid_windows():
    w, _ = windows.estimated_window("2026-06-01", "line")
    assert w == {"start": "2024-06-01", "end": "2026-06-01", "source": "estimated"}
    w, _ = windows.estimated_window("2026-06-01", "substation")
    assert w["start"] == "2024-12-01"
    w, flags = windows.gpc_window("2027-01-01", "2026-06-01", "line")
    assert flags == ["WINDOW_INVALID"] and w["start"] == "2025-06-01"


# ---------- cost ----------
def test_scenario_concurrent_and_close():
    sc = cost.cost_scenario(24, 4.82, "2024-01-01", "2024-01-01")
    t = sc["totals"]
    assert (t["separate"], t["coordinated"], t["savings"]) == (46000, 29000, 17000)
    assert t["savings_pct"] == 37.0
    assert t["coordinated_by_project"] == {"a": 14500, "b": 14500}
    assert sc["illustrative"] is True
    assert "(yes for this pair)" in sc["assumptions"][1] and "(yes for this pair)" in sc["assumptions"][2]


def test_scenario_not_concurrent_and_far():
    sc = cost.cost_scenario(0, 11.0, "2024-01-01", "2031-06-01")
    t = sc["totals"]
    assert (t["separate"], t["coordinated"], t["savings"]) == (46000, 46000, 0)
    assert "(no for this pair)" in sc["assumptions"][1] and "(no for this pair)" in sc["assumptions"][2]


def test_apply_changes_recomputes():
    sc = cost.cost_scenario(24, 4.82, "2024-01-01", "2024-01-01")
    nxt = cost.apply_changes(sc, [{"path": "coordinated.shared_truck_days", "value": 10}])
    assert nxt["totals"]["coordinated"] == 26000 and nxt["totals"]["savings_pct"] == 43.5
    assert sc["totals"]["coordinated"] == 29000  # original untouched


def test_shared_row_acres_only_for_close_lines():
    a = {"project_type": "line", "voltage_kv": 230, "endpoints": [{"lat": 32.0, "lon": -81.0}, {"lat": 32.1, "lon": -81.0}]}
    b = {"project_type": "line", "voltage_kv": 115, "endpoints": [{"lat": 32.0, "lon": -81.005}, {"lat": 32.1, "lon": -81.005}]}
    acres, width = cost.shared_row_acres(a, b, "shared_land")
    assert width == 150 and acres > 0
    assert cost.shared_row_acres(a, b, "shared_site") == (None, None)


# ---------- score ----------
def test_potential_thresholds():
    assert potential_for(60) == "high" and potential_for(35) == "moderate" and potential_for(34.9) == "lower"


# ---------- what-if ----------
def _proj(pid, lat, lon, start, end, utility="GPC"):
    return {"id": pid, "name": pid, "short_name": pid, "utility": utility, "utility_name": utility,
            "center": {"lat": lat, "lon": lon}, "endpoints": [{"lat": lat, "lon": lon}],
            "construction_window": {"start": start, "end": end, "source": "estimated"}}


def test_whatif_never_suggests_past_start():
    today = date(2026, 9, 26)
    projects = [_proj("P1", 32.30, -81.10, "2025-01-01", "2027-03-01")]
    s = suggest_shift({"start": "2027-06-01", "end": "2027-12-15"}, [
        {"construction_window": projects[0]["construction_window"]}], 24, today)
    start = windows.add_months("2027-06-01", s["shift_months"])
    assert start >= today.isoformat()
    assert s["suggested_window"]["start"] == start
    assert s["window_overlap_months_after"] >= s["window_overlap_months_before"]


def test_whatif_shift_tie_break_prefers_smallest_shift():
    today = date(2020, 1, 1)
    # Nearby project runs for 10 years: any shift inside keeps the same overlap, so shift must stay 0.
    found = [{"construction_window": {"start": "2020-01-01", "end": "2030-01-01"}}]
    s = suggest_shift({"start": "2024-01-01", "end": "2025-01-01"}, found, 24, today)
    assert s["shift_months"] == 0
    assert s["explanation"] == "The current window already gives the most shared construction time with nearby projects."


def test_whatif_filters_same_utility_and_distance():
    projects = [_proj("NEAR", 32.30, -81.10, "2027-01-01", "2028-01-01", "GPC"),
                _proj("SAME", 32.30, -81.10, "2027-01-01", "2028-01-01", "DESC"),
                _proj("FAR", 34.0, -84.0, "2027-01-01", "2028-01-01", "GPC")]
    r = whatif("x", [{"name": "Hardeeville", "lat": 32.2866, "lon": -81.0801}],
               {"start": "2027-06-01", "end": "2027-12-15"}, projects, utility="DESC", today=date(2026, 9, 26))
    assert [o["project_id"] for o in r["overlaps"]] == ["NEAR"]
    assert r["closure_data_available"] is False and r["closure_conflicts"] == []


def test_whatif_no_nearby_explanation():
    r = whatif("x", [{"name": "n", "lat": 30.0, "lon": -85.0}], {"start": "2027-06-01", "end": "2027-12-15"}, [],
               today=date(2026, 9, 26))
    assert r["suggestion"]["explanation"] == "No projects from the other utility are within 25 miles, so no shift is needed."


# ---------- closures ----------
def test_road_normalization():
    assert closures.normalize_road("US 17") == "US-17"
    assert closures.normalize_road("us17") == "US-17"
    assert closures.normalize_roads("I 95, SC-170") == ["I-95", "SC-170"]


def test_hours_cross_midnight():
    assert closures.hours_overlap("21:00-05:00", "04:00-06:00")
    assert not closures.hours_overlap("21:00-05:00", "08:00-16:00")
    assert closures.hours_overlap("9 PM – 5 AM", None)


def test_closure_conflict():
    a = {"id": "A", "roads_affected": "US 17", "work_hours": "21:00-05:00",
         "construction_window": {"start": "2027-06-01", "end": "2027-12-31"}, "center": {"lat": 32.28, "lon": -81.08}}
    b = {"id": "B", "short_name": "B", "roads_affected": ["US-17"], "work_hours": "22:00-04:00",
         "construction_window": {"start": "2027-09-01", "end": "2028-03-01"}, "center": {"lat": 32.30, "lon": -81.07}}
    far = dict(b, id="C", center={"lat": 33.5, "lon": -82.0})
    out = closures.conflicts(a, [b, far])
    assert out == [{"project_id": "B", "short_name": "B", "road": "US-17", "overlap_start": "2027-09-01",
                    "overlap_end": "2027-12-31", "hours": "22:00-04:00", "severity": "requires_review"}]
