"""Traffic management (spec update U3)."""
import pytest

from engine import traffic as T


def test_queue_model_toy_case():
    demand = [0.0] * 24
    demand[0] = demand[1] = 2000.0
    delay, affected, queue = T.queue_delay(demand, 1600, 1900, 0, 2)
    assert queue[0] == 400 and queue[1] == 800
    # drain at 1900/h with no new demand: 800 -> 0 in hour 2
    assert delay == (0 + 400) / 2 + (400 + 800) / 2 + (800 + 0) / 2
    assert affected == 4000


def test_recommended_window_is_at_night_on_a_busy_road():
    p = T.plan(aadt=60000, lanes=2, oneway=True, hours=8)
    start = p["recommended_start_hour"]
    assert start >= 18 or start <= 1  # an overnight window
    assert p["delay_veh_hours"] < p["worst_delay_veh_hours"]
    assert len(p["hourly"]) == 24 and p["worst_delay_veh_hours"] > 1000


def test_flagging_on_two_lane_roads():
    assert T.closure_type(2, False) == "flagging" and T.closure_type(None, False) == "flagging"
    assert T.closure_type(4, False) == "lane_closure" and T.closure_type(2, True) == "lane_closure"


@pytest.fixture(scope="module")
def index():
    from pathlib import Path
    from services import traffic
    idx = traffic.load(str(Path(__file__).resolve().parents[1] / "data" / "traffic"))
    if idx is None:
        pytest.skip("no traffic data")
    return idx


def _user(pid, company, lat, lon, start, end, roads="US-17"):
    return {"id": pid, "name": pid, "short_name": pid, "source": {"type": "user"}, "company_id": company, "utility": "USER",
            "project_type": "substation", "endpoints": [{"name": pid, "lat": lat, "lon": lon}], "center": {"lat": lat, "lon": lon},
            "construction_window": {"start": start, "end": end}, "roads_affected": roads}


def test_conflict_same_road_close_and_overlapping(index):
    a = _user("A", "CMP_A", 32.287, -81.079, "2027-06-01", "2027-12-15")
    b = _user("B", "CMP_B", 32.297, -81.075, "2027-09-01", "2028-03-01")
    cs = index.conflicts_between(a, b)
    assert len(cs) == 1 and cs[0]["road_ref"] == "US-17" and cs[0]["closures_avoided"] == 1
    assert "traffic_delay_avoided_veh_hours" in cs[0]


def test_no_conflict_when_windows_do_not_overlap(index):
    a = _user("A", "CMP_A", 32.287, -81.079, "2027-06-01", "2027-08-01")
    b = _user("B", "CMP_B", 32.297, -81.075, "2027-09-01", "2028-03-01")
    assert index.conflicts_between(a, b) == []


def test_no_conflict_for_the_same_owner_or_far_apart(index):
    a = _user("A", "CMP_A", 32.287, -81.079, "2027-06-01", "2027-12-15")
    assert index.conflicts_between(a, _user("B", "CMP_A", 32.297, -81.075, "2027-06-01", "2027-12-15")) == []
    assert index.conflicts_between(a, _user("C", "CMP_B", 32.45, -81.0, "2027-06-01", "2027-12-15")) == []


def test_line_crossings_have_plans(index):
    line = {"id": "L", "name": "L", "source": {"type": "public_filing"}, "utility": "DESC", "project_type": "line",
            "endpoints": [{"name": "Jasper", "lat": 32.360699, "lon": -81.124152}, {"name": "Okatie", "lat": 32.333758, "lon": -81.032495}],
            "construction_window": {"start": "2027-01-01", "end": "2027-12-31"}}
    xs = index.crossings(line)
    i95 = [x for x in xs if x["road_ref"] == "I-95"]
    assert i95 and i95[0]["aadt"] > 20000 and i95[0]["recommended_window"] and i95[0]["point_approximate"]


def test_traffic_endpoints(client_ro):
    s = client_ro.get("/traffic/summary").json()
    assert s["crossings_count"] >= 1
    xs = client_ro.get("/traffic/crossings", params={"min_aadt": 20000}).json()
    assert all(x["aadt"] >= 20000 for x in xs)
    one = client_ro.get(f"/traffic/crossings/{xs[0]['id']}").json()
    assert len(one["plan"]["hourly"]) == 24
    plan = client_ro.post("/traffic/plan", json={"point": {"lat": 32.287, "lon": -81.079}, "road_ref": "US-17",
                                                 "closure_hours": 6}).json()
    assert plan["closure_hours"] == 6 and plan["road"]["road_ref"] == "US-17"
    assert client_ro.post("/traffic/plan", json={}).status_code == 400
    b = client_ro.post(f"/traffic/crossings/{xs[0]['id']}/brief", json={}).json()
    assert b["brief"] and b["source"] in ("gemini", "fallback")
