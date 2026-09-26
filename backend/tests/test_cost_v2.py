"""Sourced cost model v2 (spec update U2)."""
from engine import budget, cost


def proj(pid, lat, lon, lat2=None, lon2=None, **kw):
    eps = [{"name": "A", "lat": lat, "lon": lon}] + ([{"name": "B", "lat": lat2, "lon": lon2}] if lat2 is not None else [])
    return {"id": pid, "short_name": pid, "endpoints": eps, "project_type": "line" if lat2 is not None else "substation",
            "state": "SC", **kw}


def test_mobilization_uses_the_real_desc_budget():
    a = budget.attach(proj("DESC_23", 32.36, -81.12, 32.33, -81.03, utility="DESC", cost={"total": 23_787_423}))
    b = proj("GPC_X", 32.35, -81.17, utility="GPC", work_type_label="Equipment upgrade (reactors)")
    budget.attach(b)
    assert a["budget_source"] == "filing" and b["budget_usd"] is None
    e = cost.cost_estimate_v2(a, b, "shared_site", 4.89, 5.66, 24, False)
    m = e["components"]["mobilization"]
    assert m["applies"] and m["point"] == round(23_787_423 * 0.05 * 0.50)
    assert m["low"] == round(23_787_423 * 0.04 * 0.25) and m["high"] == round(23_787_423 * 0.10 * 0.50)
    assert e["reference_budget_usd"] == 23_787_423 and e["reference_budget_source"] == "filing"
    assert any("Dominion" in s["name"] for s in e["sources"]) and any("MoDOT" in s["name"] for s in e["sources"])


def test_gpc_budget_is_a_labeled_miso_estimate():
    g = budget.attach(proj("GPC_Y", 32.25, -81.21, 32.35, -81.18, utility="GPC", voltage_kv=115,
                           description="Rebuild approximately 6.7 miles of line", work_type_label="Line rebuild"))
    assert g["budget_source"] == "estimated_miso" and g["budget_usd"] == 6.7 * 2_200_000
    assert "Estimate" in g["budget_note"]


def test_logistics_turn_negative_when_far_apart():
    a = proj("A", 32.0, -81.0, cost={"total": 1_000_000}, utility="DESC")
    budget.attach(a)
    near = cost.cost_estimate_v2(a, proj("B", 32.01, -81.0), "shared_site", 1, 1, 6, False)["components"]["logistics"]
    far = cost.cost_estimate_v2(a, proj("B", 32.3, -81.0), "shared_crews", 30, 24, 6, False)["components"]["logistics"]
    # With a base 25-100 mi from site, the site-to-site haul (24 mi x 1.2) beats the low-end base haul: the range goes negative.
    assert near["low"] > 0 and far["low"] < 0 and far["point"] < near["point"]


def test_land_only_for_close_lines():
    a = proj("A", 32.0, -81.0, 32.1, -81.0, voltage_kv=230)
    b = proj("B", 32.0, -81.005, 32.1, -81.005, voltage_kv=115)
    assert cost.cost_estimate_v2(a, b, "shared_land", 0.5, 0.3, 6, False)["components"]["shared_land"]["applies"]
    assert not cost.cost_estimate_v2(a, b, "shared_site", 3, 2, 6, False)["components"]["shared_land"]["applies"]
    sub = proj("S", 32.0, -81.005)
    assert not cost.cost_estimate_v2(a, sub, "shared_land", 0.5, 0.3, 6, False)["components"]["shared_land"]["applies"]


def test_no_land_savings_without_overlapping_construction():
    a = proj("A", 32.0, -81.0, 32.1, -81.0, voltage_kv=230)
    b = proj("B", 32.0, -81.005, 32.1, -81.005, voltage_kv=115)
    e = cost.cost_estimate_v2(a, b, "crossing", 0.0, 0.3, 0, False)
    assert not e["components"]["shared_land"]["applies"] and e["total_estimated_savings_usd"] == 0
    assert e["components"]["mobilization"]["reason"] != "projects more than 40 km apart"  # 0 km is not "missing"


def test_low_total_never_below_zero():
    a = proj("A", 32.0, -81.0)
    e = cost.cost_estimate_v2(a, proj("B", 32.3, -81.0), "shared_crews", 30, 24, 6, False)
    assert e["range_usd"][0] >= 0 and e["total_estimated_savings_usd"] >= 0


def test_no_savings_when_windows_cannot_meet():
    a = budget.attach(proj("A", 32.0, -81.0, cost={"total": 5_000_000}, utility="DESC"))
    e = cost.cost_estimate_v2(a, proj("B", 32.01, -81.0), "shared_site", 1, 1, 0, False)
    assert e["total_estimated_savings_usd"] == 0 and not e["components"]["mobilization"]["applies"]
