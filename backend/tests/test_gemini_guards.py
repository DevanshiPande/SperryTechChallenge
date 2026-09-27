"""Guards on Gemini output."""
from ai import gemini
from ai.validate import id_check, number_check

OV = "OVL_DESC_3__GPC_2"


def test_number_check_units():
    facts = {"center_distance_mi": 5.65, "savings": 17000, "window": {"start": "2024-01-01"}, "pct": 36.95652}
    assert number_check("They are 5.65 miles apart and save $17,000 (37.0%) starting 2024-01-01.", facts) == []
    assert number_check("They save 36.96 percent.", facts) == []  # rounded to 2 decimals
    assert number_check("They are 6 miles apart.", facts) == []  # 5.65 rounded to 0 decimals
    assert number_check("They are 8 miles apart.", facts) == [8.0]
    assert number_check("Crews save $20,000.", facts) == [20000.0]


def test_id_check():
    assert id_check("See OVL_DESC_3__GPC_2 and DESC_3.", {"OVL_DESC_3__GPC_2", "DESC_3"}) == []
    assert id_check("See GPC_99.", {"DESC_3"}) == ["GPC_99"]


def test_brief_number_guard_triggers_fallback(client_ro):
    gemini.fake_push("These projects are 3 miles apart and would save $999,999.")
    r = client_ro.post(f"/overlaps/{OV}/brief", json={"mode": "summary", "refresh": True}).json()
    assert r["source"] == "fallback"
    assert "999,999" not in r["brief"] and "5.65 miles apart" in r["brief"]


def test_brief_passes_guard_and_caches(client_ro):
    text = "Jasper–Okatie and McIntosh–Purrysburg are 5.65 miles apart and overlap for 19 months."
    gemini.fake_push(text)
    r = client_ro.post(f"/overlaps/{OV}/brief", json={"mode": "summary", "refresh": True}).json()
    assert (r["source"], r["brief"], r["cached"]) == ("gemini", text, False)
    again = client_ro.post(f"/overlaps/{OV}/brief", json={"mode": "summary"}).json()
    assert again["cached"] is True and again["brief"] == text
    assert client_ro.get(f"/overlaps/{OV}").json()["brief"] == text


def test_brief_plan_allows_step_numbers(client_ro):
    text = "1) Confirm windows. 2) Share crews for 19 months. 3) Share a laydown yard. 4) Exchange contacts."
    gemini.fake_push(text)
    r = client_ro.post(f"/overlaps/{OV}/brief", json={"mode": "plan", "refresh": True}).json()
    assert r["source"] == "gemini"


def test_brief_gemini_error_falls_back(client_ro):
    gemini.fake_push(gemini.GeminiUnavailable("down"))
    r = client_ro.post(f"/overlaps/{OV}/brief", json={"mode": "risks", "refresh": True}).json()
    assert r["source"] == "fallback" and r["brief"].startswith("Risks for")


def test_draft_keeps_user_fields_and_validates(client_ro):
    gemini.fake_push({
        "name": {"value": "Gemini name", "confidence": "high"},
        "description": {"value": None, "confidence": None},
        "location": {"value": "Hardeeville, SC", "confidence": "high"},
        "start_date": {"value": "2027-02-30", "confidence": "high"},  # invalid date -> null
        "end_date": {"value": "2027-12-31", "confidence": "high"},
        "work_type": {"value": None, "confidence": None},
        "lane_closures": {"value": None, "confidence": None},
        "work_hours": {"value": None, "confidence": None},
        "roads_affected": {"value": "us 17", "confidence": "medium"},
        "follow_up_questions": ["q1", "q2", "q3", "q4"],
    })
    r = client_ro.post("/draft", json={"kind": "project", "text": "something", "draft": {"name": "My name"}}).json()
    f = r["fields"]
    assert f["name"] == {"value": "My name", "confidence": "user"}
    assert f["start_date"] == {"value": None, "confidence": None}
    assert f["roads_affected"]["value"] == "US-17"
    assert r["location_point"] == {"lat": 32.2871, "lon": -81.079, "label": "Hardeeville, SC"}
    assert set(r["missing"]) == {"description", "start_date", "work_type", "lane_closures", "work_hours"}
    assert r["ready"] is False and len(r["follow_up_questions"]) == 3


def test_draft_no_gemini_is_503(client_ro, monkeypatch):
    monkeypatch.setenv("FAKE_GEMINI", "0")
    r = client_ro.post("/draft", json={"kind": "project", "text": "x"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "GEMINI_UNAVAILABLE"


def test_scenario_rejects_unknown_paths_and_clamps(client_ro):
    gemini.fake_push({"changes": [
        {"path": "totals.savings", "value": 999999, "label": "cheat"},
        {"path": "coordinated.laydown_sites", "value": 50, "label": "many yards"},
        {"path": "coordinated.shared_truck_days", "value": 10, "label": "10 truck-days"},
    ], "note": "Saves 90% guaranteed."})
    r = client_ro.post("/scenario/assist", json={"overlap_id": OV, "message": "go wild"}).json()
    assert [c["path"] for c in r["suggested_changes"]] == ["coordinated.laydown_sites", "coordinated.shared_truck_days"]
    assert r["suggested_changes"][0]["value"] == 10  # clamped to 1..10
    t = r["preview_totals"]
    assert t["coordinated"] == 6000 + 10 * 1500 + 10 * 5000 and t["separate"] == 46000
    assert "90%" not in r["reply"]  # a note with digits is dropped
    assert r["reply"].startswith("Applying these changes gives separate work at $46,000")


def test_scenario_uses_given_scenario(client_ro):
    sc = client_ro.get(f"/overlaps/{OV}").json()["cost_scenario"]
    sc["unit_rates"]["bucket_truck_per_day"] = 2000
    gemini.fake_push({"changes": [{"path": "coordinated.shared_truck_days", "value": 10, "label": "x"}], "note": ""})
    r = client_ro.post("/scenario/assist", json={"overlap_id": OV, "message": "x", "scenario": sc}).json()
    assert r["preview_totals"]["separate"] == 2 * (3000 + 10 * 2000 + 5000)
