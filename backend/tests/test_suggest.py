"""Suggested inventory (GET /resources/suggested): needs -> own inventory -> other companies' listings -> coverage plan."""
from conftest import as_company

from services import needs as N
from services.state import STATE

A, B = as_company("CMP_A"), as_company("CMP_B")
HARDEEVILLE_LINE = [{"name": "Jasper", "lat": 32.3607, "lon": -81.1242}, {"name": "Hardeeville", "lat": 32.2871, "lon": -81.0790}]


def _project(client, who, name, endpoints, start="2027-06-01", end="2027-12-15", **extra):
    r = client.post("/projects", json={"name": name, "endpoints": endpoints, "start_date": start, "end_date": end,
                                       "voltage_kv": 230, **extra}, headers=who)
    assert r.status_code == 201, r.text
    return r.json()["project"]


def test_categories_and_crane_size():
    assert N.categorize("wire-stringing puller-tensioner set") == "puller_tensioner"
    assert N.categorize("Certified lineworkers") == "line_crew" and N.categorize("Bucket trucks with operators") == "bucket_truck"
    assert N.categorize("60-ton crane") == "crane" and N.tonnage("60-ton crane") == 60


def test_no_projects_gives_a_note(client):
    r = client.get("/resources/suggested", headers=A)
    assert r.status_code == 200 and r.json()["suggestions"] == [] and r.json()["note"]


def test_requires_a_company(client):
    assert client.get("/resources/suggested").status_code == 401


def test_typical_needs_own_inventory_first_then_partner_listings(client):
    mine = _project(client, A, "A new 230 kV tap line", HARDEEVILLE_LINE)
    _project(client, B, "B work next door", [{"name": "B site", "lat": 32.31, "lon": -81.09}])  # B becomes a partner
    c = client.get("/resources/suggested", params={"project_id": mine["id"]}, headers=A).json()
    needs = {n["category"]: n for n in c["needs"]}
    assert all(n["source"] == "typical" for n in c["needs"]) and "typical" in c["needs_basis"].lower()
    assert {"bucket_truck", "digger_derrick", "crane", "puller_tensioner", "line_crew"} <= set(needs)
    # own bucket trucks (demo listing of CMP_A) are applied before anything else
    assert any(o["category"] == "bucket_truck" and o["covers"] > 0 for o in c["own"])
    assert all(s["company_id"] != "CMP_A" for s in c["suggestions"])
    crew = next(s for s in c["suggestions"] if s["category"] == "line_crew")
    assert crew["company_id"] == "CMP_B" and crew["partner"] and crew["covers"] == 4 and crew["haul_saved_usd"] > 0
    crane = next(s for s in c["suggestions"] if s["category"] == "crane")
    assert crane["covers"] == 1 and "ton" in " ".join(crane["reasons"])
    assert needs["digger_derrick"]["missing"] == needs["digger_derrick"]["quantity"]  # nobody lists one
    assert any("digger" in m for m in c["missing"])
    # only needed categories qualify, and the ones that cover something come first
    assert [s["covers"] > 0 for s in c["suggestions"]] == sorted((s["covers"] > 0 for s in c["suggestions"]), reverse=True)


def test_needs_come_from_the_contract_when_there_is_one(client):
    STATE.db.contracts.insert_one({"id": "CTR_T1", "company_id": "CMP_A", "text_hash": "h1", "extracted": {
        "equipment": {"value": [{"type": "bucket trucks", "quantity": 3}, {"type": "60-ton crane", "quantity": 1}]},
        "crew_size": {"value": 12}}})
    p = _project(client, A, "Contract project", HARDEEVILLE_LINE, contract_text_hash="h1")
    c = client.get("/resources/suggested", params={"project_id": p["id"]}, headers=A).json()
    needs = {n["category"]: n for n in c["needs"]}
    assert set(needs) == {"bucket_truck", "crane", "line_crew"} and all(n["source"] == "contract" for n in c["needs"])
    assert needs["bucket_truck"]["quantity"] == 3 and needs["crane"]["tons"] == 60 and needs["line_crew"]["quantity"] == 12


def test_a_crane_too_small_for_the_job_is_rejected(client):
    STATE.db.contracts.insert_one({"id": "CTR_T2", "company_id": "CMP_A", "text_hash": "h2", "extracted": {
        "equipment": {"value": [{"type": "90-ton crane", "quantity": 1}]}}})
    p = _project(client, A, "Heavy lift", HARDEEVILLE_LINE, contract_text_hash="h2")
    c = client.get("/resources/suggested", params={"project_id": p["id"]}, headers=A).json()
    assert not any(s["category"] == "crane" for s in c["suggestions"])  # the demo 60-ton crane is too small
    assert c["needs"][0]["missing"] == 1


def test_suggestions_follow_the_selected_project(client):
    c = client.get("/resources/suggested", params={"project_id": "DESC_1"}, headers=A).json()
    assert c["project_id"] == "DESC_1" and c["needs"]
    assert all(s["for_project_id"] == "DESC_1" for s in c["suggestions"])
    assert client.get("/resources/suggested", params={"project_id": "NOPE"}, headers=A).status_code == 404
