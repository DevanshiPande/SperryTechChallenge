"""Predicted congestion around a project (GET /projects/{id}/congestion)."""
from pathlib import Path

import pytest

from services.state import STATE


@pytest.fixture(scope="module", autouse=True)
def traffic_index():
    from services import traffic
    if STATE.traffic is None:
        STATE.traffic = traffic.load(str(Path(__file__).resolve().parents[1] / "data" / "traffic"))
    if STATE.traffic is None:
        pytest.skip("no traffic data")


@pytest.fixture(autouse=True)
def fresh_cache():
    from services import congestion
    congestion._results.clear()
    if STATE.db is not None:
        STATE.db.congestion_cache.delete_many({})
    yield
    congestion._results.clear()


def test_busy_crossed_road_is_heavy_with_a_night_window(client):
    r = client.get("/projects/DESC_3/congestion")
    assert r.status_code == 200
    c = r.json()
    i95 = next(x for x in c["roads"] if x["road"] == "I-95")
    assert i95["role"] == "crossed" and i95["level"] == "heavy" and i95["lines"]
    assert i95["recommended_window"] == "7 PM–3 AM"  # 12-hour clock, from the queue model
    assert "I-95" in i95["popup"] and "Heavy congestion" in i95["popup"]
    quiet = [x for x in c["roads"] if x["role"] == "crossed" and x["level"] == "light"]
    assert quiet and all(x["recommended_window"] == "any time of day" for x in quiet)
    assert c["roads"][0]["level"] == "heavy"  # worst first
    assert c["summary"] and c["best_time"]["headline"]


def test_summary_falls_back_when_gemini_invents_a_road_or_number(client, monkeypatch):
    from ai import gemini
    monkeypatch.setattr(gemini, "available", lambda: True)
    monkeypatch.setattr(gemini, "generate_text", lambda *a, **k: "Expect congestion on I-16 from 5 PM, about 99,999 cars.")
    c = client.get("/projects/DESC_3/congestion").json()
    assert c["summary_source"] == "template" and "I-16" not in c["summary"] and "I-95" in c["summary"]


def test_summary_from_gemini_is_kept_when_it_uses_only_facts(client, monkeypatch):
    from ai import gemini
    monkeypatch.setattr(gemini, "available", lambda: True)
    monkeypatch.setattr(gemini, "generate_text", lambda *a, **k: "Expect heavy congestion on I-95 7 AM–3 PM; work 7 PM–3 AM.")
    c = client.get("/projects/DESC_3/congestion").json()
    assert c["summary_source"] == "gemini" and c["summary"].startswith("Expect heavy congestion on I-95")


def test_unknown_project_is_404(client):
    assert client.get("/projects/NOPE_1/congestion").status_code == 404


def test_results_are_cached_until_the_project_changes(client):
    from services import congestion
    first = client.get("/projects/DESC_3/congestion").json()
    calls = []
    real = congestion._compute
    congestion._compute = lambda *a, **k: calls.append(1) or real(*a, **k)
    try:
        again = client.get("/projects/DESC_3/congestion").json()
        assert calls == [] and again == first  # served from the cache
    finally:
        congestion._compute = real


def test_warm_all_fills_the_cache(client):
    from services import congestion
    congestion._results.clear()
    congestion.warm_all(pause_s=0)
    assert congestion.cached_count() >= 6


def test_project_is_described_and_crossings_say_where(client):
    c = client.get("/projects/DESC_3/congestion").json()
    d = c["project"]
    assert d["kind"] == "line" and d["text"].startswith("Power line from Jasper Substation to Okatie Substation")
    assert len(d["line"]) == 2 and len(d["sites"]) == 2
    assert c["crossings"] and all(x["where"] and x["point"] for x in c["crossings"])
    i95 = next(r for r in c["roads"] if r["road"] == "I-95")
    assert "mi from" in i95["where"] or "reaches" in i95["where"]
    assert i95["where"] in i95["popup"]


def test_site_names():
    from services.congestion import site_name
    assert site_name("Okatie") == "Okatie Substation" and site_name("Jasper Substation") == "Jasper Substation"
    assert site_name("proposed Hardeeville Tap Station") == "proposed Hardeeville Tap Station"


def test_results_are_stored_in_the_database_and_reused(client):
    from services import congestion
    first = client.get("/projects/DESC_3/congestion").json()
    assert STATE.db.congestion_cache.count_documents({"project_id": "DESC_3"}) == 1
    congestion._results.clear()  # e.g. a restart: memory is empty, the database still has it
    calls = []
    real = congestion._compute
    congestion._compute = lambda *a, **k: calls.append(1) or real(*a, **k)
    try:
        assert client.get("/projects/DESC_3/congestion").json() == first and calls == []
    finally:
        congestion._compute = real


def test_a_new_project_gets_its_congestion_computed_in_the_background(client):
    import time
    from conftest import as_company
    r = client.post("/projects", json={"name": "Background test", "endpoints": [{"name": "a", "lat": 32.3, "lon": -81.1},
                                       {"name": "b", "lat": 32.34, "lon": -81.03}], "start_date": "2027-01-01",
                                       "end_date": "2027-09-01"}, headers=as_company("CMP_A"))
    pid = r.json()["project"]["id"]
    for _ in range(50):
        if STATE.db.congestion_cache.count_documents({"project_id": pid}):
            break
        time.sleep(0.1)
    assert STATE.db.congestion_cache.count_documents({"project_id": pid}) == 1
