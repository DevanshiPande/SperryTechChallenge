"""Suggested inventory (GET /resources/suggested)."""
from conftest import as_company

A, B = as_company("CMP_A"), as_company("CMP_B")


def _project(client, who, name, lat, lon, start="2027-06-01", end="2027-12-15"):
    r = client.post("/projects", json={"name": name, "endpoints": [{"name": name, "lat": lat, "lon": lon}],
                                       "start_date": start, "end_date": end}, headers=who)
    assert r.status_code == 201, r.text
    return r.json()["project"]


def test_no_projects_gives_a_note(client):
    r = client.get("/resources/suggested", headers=A)
    assert r.status_code == 200 and r.json()["suggestions"] == [] and r.json()["note"]


def test_requires_a_company(client):
    assert client.get("/resources/suggested").status_code == 401


def test_partner_listing_ranks_first_and_own_listings_are_excluded(client):
    mine = _project(client, A, "A tap near Hardeeville", 32.30, -81.08)
    _project(client, B, "B work next door", 32.31, -81.07)  # Demo Contractor B becomes a coordination partner
    c = client.get("/resources/suggested", headers=A).json()
    s = c["suggestions"]
    assert s and all(x["company_id"] != "CMP_A" for x in s)
    top = s[0]
    assert top["company_id"] == "CMP_B" and top["partner"] and top["for_project_id"] == mine["id"]
    assert "coordination partner" in top["reasons"][0] and top["overlap_days"] > 0
    assert [x["score"] for x in s] == sorted((x["score"] for x in s), reverse=True)


def test_suggestions_follow_the_selected_project(client):
    _project(client, A, "A tap near Hardeeville", 32.30, -81.08)
    # A public project far from Hardeeville (Augusta area): scored against it, the Hardeeville listing ranks lower.
    near_aug = client.get("/resources/suggested", params={"project_id": "DESC_1"}, headers=A).json()
    assert near_aug["project_id"] == "DESC_1"
    assert all(s["for_project_id"] == "DESC_1" for s in near_aug["suggestions"])
    assert all("your " not in s["reasons"][-2] for s in near_aug["suggestions"])  # not your project
    assert client.get("/resources/suggested", params={"project_id": "NOPE"}, headers=A).status_code == 404
