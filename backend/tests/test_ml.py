"""ML integration (ml/ML_README.md step U6)."""
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from conftest import as_company
from engine import cost
from services import ml

DATA = Path(__file__).resolve().parents[1] / "data"
A = as_company("CMP_A")
TODAY = date.today()

pytestmark = pytest.mark.skipif(not ml.available(), reason="ML models not loadable")


@pytest.fixture(scope="module")
def built():
    return {p["id"]: p for p in json.loads((DATA / "projects.json").read_text(encoding="utf-8"))}


def test_predictions_are_labeled_with_ranges():
    w = ml.predicted_window({"name": "Jasper - Okatie 230 kV #2: Construct", "in_service_date": "2027-12-31"})
    p = w["prediction"]
    assert p["label"] == "predicted" and p["low"] <= p["months"] <= p["high"]
    b = ml.predicted_budget({"name": "MITCHELL - NORTH TIFTON 230KV RECONDUCTOR", "description": "Reconductor 25 miles"})
    assert b["budget_source"].startswith("predicted") and b["budget_prediction"]["label"] == "predicted"
    assert b["budget_range_usd"][0] <= b["budget_usd"] <= b["budget_range_usd"][1]


def test_desc_windows_predicted_in_pipeline(built):
    desc = [p for p in built.values() if p["utility"] == "DESC" and p.get("in_service_date")]
    assert desc and all(p["construction_window"]["source"] == "predicted" for p in desc)
    for p in desc:
        w = p["construction_window"]
        assert w["end"] == p["in_service_date"]  # the filed date is never replaced
        assert w["start"] < w["end"] and w["prediction"]["label"] == "predicted"


def test_gpc_line_budgets_predicted_and_filing_budgets_kept(built):
    gpc_lines = [p for p in built.values() if p["utility"] == "GPC" and p["project_type"] == "line"]
    assert gpc_lines and all(p["budget_source"] == ml.BUDGET_SOURCE for p in gpc_lines)
    assert all(p["budget_range_usd"][0] <= p["budget_usd"] <= p["budget_range_usd"][1] for p in gpc_lines)
    assert all(p["budget_usd"] is None for p in built.values() if p["utility"] == "GPC" and p["project_type"] != "line")
    desc = [p for p in built.values() if p["utility"] == "DESC"]
    assert all(p["budget_source"] == "filing" and p["budget_usd"] == p["cost"]["total"] for p in desc if p.get("cost"))


def test_savings_range_uses_predicted_budget_range():
    a = {"id": "A", "short_name": "A", "project_type": "line", "state": "GA", "budget_usd": 10_000_000,
         "budget_source": ml.BUDGET_SOURCE, "budget_range_usd": [6_000_000, 15_000_000],
         "endpoints": [{"lat": 32.0, "lon": -81.0}, {"lat": 32.1, "lon": -81.0}]}
    b = {"id": "B", "short_name": "B", "project_type": "substation", "state": "GA", "endpoints": [{"lat": 32.05, "lon": -81.01}]}
    m = cost.cost_estimate_v2(a, b, "shared_site", 2.0, 1.0, 6, False)["components"]["mobilization"]
    assert m["low"] == round(6_000_000 * 0.04 * 0.25) and m["point"] == round(10_000_000 * 0.05 * 0.5)
    assert m["high"] == round(15_000_000 * 0.10 * 0.5)


def test_document_dates_and_budgets_are_never_replaced(client):
    body = {"name": "Given dates", "location_text": "Savannah", "start_date": "2027-01-01", "end_date": "2027-09-01",
            "voltage_kv": 115, "budget_usd": 4_000_000}
    p = client.post("/projects", json=body, headers=A).json()["project"]
    assert p["construction_window"] == {"start": "2027-01-01", "end": "2027-09-01", "source": "user"}
    assert p["budget_usd"] == 4_000_000 and p["budget_source"] == "user" and "budget_range_usd" not in p


def test_missing_start_is_predicted_and_clamped_to_today(client):
    soon = (TODAY + timedelta(days=150)).isoformat()
    p = client.post("/projects", json={"name": "230 kV tap line", "location_text": "Savannah", "end_date": soon,
                                       "voltage_kv": 230}, headers=A).json()["project"]
    w = p["construction_window"]
    assert w["source"] == "predicted" and w["prediction"]["label"] == "predicted"
    assert w["start"] == TODAY.isoformat()  # model says ~2-3 years, which would be in the past
    assert any(f["code"] == "PREDICTED_START_CLAMPED_TO_TODAY" for f in p["quality_flags"])
    assert p["budget_source"] == ml.BUDGET_SOURCE  # transmission work with no budget: predicted


def test_road_work_gets_no_predicted_budget(client):
    p = client.post("/projects", json={"name": "Corridor upgrade", "location_text": "Hardeeville", "start_date": "2027-06-01",
                                       "end_date": "2027-12-15"}, headers=A).json()["project"]
    assert p["budget_usd"] is None and p["budget_source"] is None


def test_end_date_still_required(client):
    r = client.post("/projects", json={"name": "x", "location_text": "Savannah", "voltage_kv": 115}, headers=A)
    assert r.status_code == 400


def test_contract_without_start_or_budget_is_predicted(client):
    from services.contracts import contract_project
    fields = {"project_name": {"value": "Jasper 230 kV tap line"}, "location_text": {"value": "Hardeeville, SC"},
              "voltage_kv": {"value": 230}, "end_date": {"value": (TODAY + timedelta(days=900)).isoformat()}}
    p = contract_project("CTR_T", {"id": "CMP_A", "name": "A"}, fields)
    assert p["construction_window"]["source"] == "predicted" and p["construction_window"]["start"] >= TODAY.isoformat()
    assert p["budget_source"] == ml.BUDGET_SOURCE
    fields["start_date"] = {"value": "2027-01-15"}
    fields["budget_usd"] = {"value": 9_850_000}
    p = contract_project("CTR_T", {"id": "CMP_A", "name": "A"}, fields)
    assert p["construction_window"]["start"] == "2027-01-15" and p["construction_window"]["source"] == "contract"
    assert p["budget_usd"] == 9_850_000 and p["budget_source"] == "contract"


def test_ml_status_and_feedback(client):
    s = client.get("/ml/status").json()
    assert s["models_loaded"] and s["duration"]["rows_used"] == 205 and s["cost"]["rows_used"] == 44
    assert s["ranking_model"].startswith("not trained") and s["learning_curves"]
    oid = client.get("/overlaps").json()[0]["id"]
    r = client.post(f"/overlaps/{oid}/feedback", json={"useful": True, "contacted": False, "note": "good pair"}, headers=A)
    assert r.status_code == 201
    assert client.get("/ml/status").json()["feedback_count"] == 1
    assert client.post(f"/overlaps/{oid}/feedback", json={"useful": "yes"}, headers=A).status_code == 400
    assert client.post(f"/overlaps/{oid}/feedback", json={"useful": True}).status_code == 401
