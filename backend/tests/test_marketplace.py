"""Mongo-backed features: identity, seed, events, user projects, resources, reservations, jobs, messages."""
from conftest import as_company

A, B, C = as_company("CMP_A"), as_company("CMP_B"), as_company("CMP_C")


def test_seed_and_identity(client):
    assert [c["id"] for c in client.get("/companies").json()] == ["CMP_A", "CMP_B", "CMP_C"]
    assert all("demo" in c["name"].lower() for c in client.get("/companies").json())
    me = client.get("/me", headers=A).json()
    assert me["kind"] == "company" and me["company"]["name"] == "Demo Contractor A"
    assert client.get("/me").json() == {"kind": "guest"}
    assert client.get("/me", headers={"X-Worker-Id": "WRK_1"}).json()["kind"] == "worker"
    assert len(client.get("/resources").json()) == 3
    assert len(client.get("/jobs").json()) == 3


def test_public_data_still_served_from_memory(client):
    assert len(client.get("/projects").json()) == 10
    assert len(client.get("/overlaps?kind=cross_utility").json()) == 6


def test_guest_writes_are_unauthorized(client):
    r = client.post("/resources", json={"name": "Crane", "type": "equipment", "quantity": 1})
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "UNAUTHORIZED", "message": "Select a company first"}}


def test_read_only_mode_marketplace_is_503(client_ro):
    r = client_ro.post("/resources", json={"name": "Crane", "type": "equipment", "quantity": 1}, headers=A)
    assert r.status_code == 503 and r.json()["error"]["code"] == "DB_UNAVAILABLE"
    assert client_ro.get("/resources").status_code == 503
    assert client_ro.get("/projects").status_code == 200  # Sperry core works without a DB


def test_user_project_creates_overlaps_and_events(client):
    body = {"name": "Corridor upgrade", "location_text": "Near Hardeeville, SC", "start_date": "2027-06-01",
            "end_date": "2027-12-15", "roads_affected": "US 17", "lane_closures": "Northbound lane",
            "work_hours": "21:00-05:00"}
    r = client.post("/projects", json=body, headers=B)
    assert r.status_code == 201, r.text
    out = r.json()
    p = out["project"]
    assert p["id"].startswith("USR_") and p["utility"] == "USER" and p["utility_name"] == "Demo Contractor B"
    assert p["source"]["type"] == "user" and p["roads_affected"] == ["US-17"]
    assert p["construction_window"] == {"start": "2027-06-01", "end": "2027-12-15", "source": "user"}
    partners = {o["project_b"] for o in out["overlaps"]}
    assert "DESC_3" in partners  # Jasper–Okatie is ~4 mi away
    assert all(o["kind"] == "user_project" and o["project_a"] == p["id"] for o in out["overlaps"])
    listed = client.get("/overlaps?kind=user_project").json()
    assert {o["id"] for o in listed} == {o["id"] for o in out["overlaps"]}
    assert sorted(o["rank"] for o in listed) == list(range(1, len(listed) + 1))
    # public projects expose them additively, Sperry's list is unchanged
    d3 = client.get("/projects/DESC_3").json()
    assert f"OVL_{p['id']}__DESC_3" in d3["user_overlap_ids"]
    assert len(client.get("/overlaps?kind=cross_utility").json()) == 6
    assert client.get("/projects?source=user").json()[0]["id"] == p["id"]
    ev = client.get("/events?since=0", headers=A).json()
    assert any(e["collection"] == "projects" and e["op"] == "insert" and e["doc_id"] == p["id"] for e in ev["events"])


def test_user_projects_of_different_companies_overlap_and_conflict(client):
    base = {"location_text": "Hardeeville", "start_date": "2027-06-01", "end_date": "2027-12-15",
            "roads_affected": "US-17", "work_hours": "9 PM - 5 AM"}
    pa = client.post("/projects", json={**base, "name": "A work"}, headers=A).json()["project"]
    same = client.post("/projects", json={**base, "name": "A other"}, headers=A).json()
    assert pa["id"] not in {o["project_b"] for o in same["overlaps"]}  # same company is not compared
    out = client.post("/projects", json={**base, "name": "B work"}, headers=B).json()
    assert pa["id"] in {o["project_b"] for o in out["overlaps"]}
    roads = {c["project_id"] for c in out["closure_conflicts"]}
    assert pa["id"] in roads and all(c["road"] == "US-17" for c in out["closure_conflicts"])
    w = client.post("/whatif", json={"name": "x", "location_text": "Hardeeville", "roads_affected": "US 17",
                                     "construction_window": {"start": "2027-07-01", "end": "2027-08-01"}}).json()
    assert w["closure_data_available"] is True and len(w["closure_conflicts"]) >= 2


def test_user_project_permissions(client):
    p = client.post("/projects", json={"name": "Mine", "location_text": "Savannah", "start_date": "2027-01-01",
                                       "end_date": "2027-06-01"}, headers=A).json()["project"]
    assert client.patch(f"/projects/{p['id']}", json={"name": "Hijack"}, headers=B).status_code == 403
    assert client.patch("/projects/DESC_3", json={"name": "x"}, headers=A).status_code == 403
    r = client.patch(f"/projects/{p['id']}", json={"end_date": "2027-09-01"}, headers=A)
    assert r.status_code == 200 and r.json()["project"]["in_service_date"] == "2027-09-01"
    assert client.delete(f"/projects/{p['id']}", headers=B).status_code == 403
    assert client.delete(f"/projects/{p['id']}", headers=A).status_code == 200
    assert client.get(f"/projects/{p['id']}").status_code == 404
    assert client.get("/overlaps?kind=user_project").json() == []


def test_bad_user_project_input(client):
    r = client.post("/projects", json={"name": "x", "location_text": "Atlantis", "start_date": "2027-01-01",
                                       "end_date": "2027-02-01"}, headers=A)
    assert r.status_code == 400 and "Could not locate" in r.json()["error"]["message"]
    r = client.post("/projects", json={"name": "x", "location_text": "Savannah", "start_date": "2027-03-01",
                                       "end_date": "2027-02-01"}, headers=A)
    assert r.status_code == 400


def _resource(client, headers, **kw):
    body = {"name": "Crane", "type": "equipment", "quantity": 2, "location_text": "Pooler",
            "available_from": "2027-06-01", "available_to": "2027-06-30", "daily_rate": 1250, **kw}
    r = client.post("/resources", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_resource_create_labels_and_nearby(client):
    r = _resource(client, C)
    assert r["date_label"] == "Jun 1–30, 2027" and r["rate_label"] == "$1,250/day per unit"
    assert "GPC_3" in r["nearby_project_ids"]  # Goshen–McIntosh is near Pooler
    yard = client.post("/resources", json={"name": "Lineworkers", "type": "crew", "quantity": 4}, headers=B).json()
    assert yard["location"]["label"] == "Hardeeville, SC" and yard["rate_label"] == "Rate on request"
    near = client.get("/resources?near=32.1155,-81.247&radius_km=5").json()
    assert r["id"] in {x["id"] for x in near if x["distance_km"] == 0.0}  # the demo crane is also in Pooler
    assert all(x["distance_km"] <= 5 for x in near)


def test_resource_owner_only(client):
    r = _resource(client, C)
    assert client.patch(f"/resources/{r['id']}", json={"quantity": 5}, headers=A).status_code == 403
    assert client.delete(f"/resources/{r['id']}", headers=A).status_code == 403
    assert client.patch(f"/resources/{r['id']}", json={"quantity": 5}, headers=C).json()["quantity"] == 5


def test_reservation_rules(client):
    r = _resource(client, C)  # 2 cranes, Jun 2027
    url = f"/resources/{r['id']}/reservations"
    assert client.post(url, json={"quantity": 1, "from": "2027-06-05", "to": "2027-06-10"}, headers=C).status_code == 400
    assert client.post(url, json={"quantity": 1, "from": "2027-05-30", "to": "2027-06-10"}, headers=A).status_code == 400
    r1 = client.post(url, json={"quantity": 2, "from": "2027-06-05", "to": "2027-06-10"}, headers=A).json()
    assert r1["status"] == "pending"
    r2 = client.post(url, json={"quantity": 1, "from": "2027-06-08", "to": "2027-06-12"}, headers=B).json()
    assert client.patch(f"/reservations/{r1['id']}", json={"status": "accepted"}, headers=A).status_code == 403
    assert client.patch(f"/reservations/{r1['id']}", json={"status": "accepted"}, headers=C).json()["status"] == "accepted"
    # both cranes are booked Jun 5-10: accepting B's overlapping request must fail, new requests too
    bad = client.patch(f"/reservations/{r2['id']}", json={"status": "accepted"}, headers=C)
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "INSUFFICIENT_QUANTITY"
    bad = client.post(url, json={"quantity": 1, "from": "2027-06-09", "to": "2027-06-09"}, headers=B)
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "INSUFFICIENT_QUANTITY"
    assert client.post(url, json={"quantity": 2, "from": "2027-06-20", "to": "2027-06-25"}, headers=B).status_code == 201
    assert [x["id"] for x in client.get("/reservations?role=incoming", headers=C).json()][-1] == r1["id"]
    assert client.patch(f"/reservations/{r1['id']}", json={"status": "cancelled"}, headers=A).json()["status"] == \
        "cancelled"


def test_events_visibility(client):
    r = _resource(client, C)
    rsv = client.post(f"/resources/{r['id']}/reservations", json={"quantity": 1, "from": "2027-06-05",
                                                                   "to": "2027-06-06"}, headers=A).json()

    def seen(h):
        return {(e["collection"], e["doc_id"]) for e in client.get("/events?since=0", headers=h).json()["events"]}
    assert ("resources", r["id"]) in seen(B)  # resources are public
    assert ("reservations", rsv["id"]) in seen(A) and ("reservations", rsv["id"]) in seen(C)
    assert ("reservations", rsv["id"]) not in seen(B)
    latest = client.get("/events?since=0", headers=A).json()["latest_seq"]
    assert client.get(f"/events?since={latest}", headers=A).json()["events"] == []


def test_jobs_and_applications(client):
    j = client.post("/jobs", json={"title": "Lineworker", "openings": 2, "location_text": "Savannah", "pay_min": 38,
                                   "pay_max": 46, "qualifications": ["CDL Class A"]}, headers=A).json()
    assert j["pay_label"] == "$38–$46/hr" and j["status"] == "open"
    W = {"X-Worker-Id": "WRK_1"}
    app = client.post(f"/jobs/{j['id']}/applications", json={"availability": "June"}, headers=W)
    assert app.status_code == 201
    assert client.post(f"/jobs/{j['id']}/applications", json={}, headers=W).status_code == 409
    assert client.get("/applications", headers=W).json()[0]["job_id"] == j["id"]
    assert client.get("/applications", headers=A).json()[0]["id"] == app.json()["id"]
    assert client.patch(f"/applications/{app.json()['id']}", json={"status": "accepted"}, headers=B).status_code == 403
    assert client.patch(f"/applications/{app.json()['id']}", json={"status": "reviewed"}, headers=A).status_code == 200
    assert client.patch(f"/jobs/{j['id']}", json={"status": "closed"}, headers=B).status_code == 403
    assert client.get("/jobs?qualification=cdl").json()[0]["id"] in {j["id"], "JOB_DEMO1", "JOB_DEMO3"}


def test_saved_jobs(client):
    W = {"X-Worker-Id": "WRK_1"}
    assert client.get("/saved-jobs", headers=A).status_code == 401
    assert client.post("/jobs/JOB_DEMO1/save", headers=A).status_code == 401
    assert client.post("/jobs/NOPE/save", headers=W).status_code == 404
    assert client.post("/jobs/JOB_DEMO1/save", headers=W).status_code == 201
    assert client.post("/jobs/JOB_DEMO1/save", headers=W).status_code == 201  # idempotent
    assert [j["id"] for j in client.get("/saved-jobs", headers=W).json()] == ["JOB_DEMO1"]
    assert client.delete("/jobs/JOB_DEMO1/save", headers=W).json() == {"status": "removed", "job_id": "JOB_DEMO1"}
    assert client.get("/saved-jobs", headers=W).json() == []


def test_messages(client):
    r = client.post("/conversations", json={"to_company_id": "CMP_C", "topic": "Crane", "text": "Hi",
                                            "overlap_id": "OVL_DESC_3__GPC_2",
                                            "attachment": {"type": "cost_scenario",
                                                           "overlap_id": "OVL_DESC_3__GPC_2"}}, headers=A)
    assert r.status_code == 201
    cid = r.json()["conversation"]["id"]
    assert r.json()["message"]["attachment"]["totals"]["separate"] == 46000
    assert client.get(f"/conversations/{cid}/messages", headers=B).status_code == 403
    assert client.post(f"/conversations/{cid}/messages", json={"text": "Sure"}, headers=C).status_code == 201
    assert len(client.get(f"/conversations/{cid}/messages", headers=A).json()) == 2
    assert client.get("/conversations", headers=A).json()[0]["id"] == cid
