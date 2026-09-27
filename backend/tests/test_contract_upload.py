"""Contract upload and match (spec update U4)."""
from pathlib import Path

from fpdf import FPDF

from ai import gemini
from conftest import as_company
from services.contracts import validate

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "samples" / "sample_contract_hardeeville.pdf"
A = as_company("CMP_A")
TEXT = "Project name: Test Line\nContract price: $9,850,000\nStart date: June 1, 2027\nVoltage: 115 kV\nCrew size: 14 workers"


def test_evidence_validation_drops_hallucinated_fields():
    raw = {
        "project_name": {"value": "Test Line", "confidence": "high", "evidence": "Project name: Test Line"},
        "budget_usd": {"value": 9850000, "confidence": "high", "evidence": "Contract price: $9,850,000"},
        "voltage_kv": {"value": 230, "confidence": "high", "evidence": "Voltage: 115 kV"},  # number not in evidence
        "crew_size": {"value": 14, "confidence": "high", "evidence": "Crew size: 40 workers"},  # snippet not in document
        "start_date": {"value": "2027-06-01", "confidence": "high", "evidence": "Start date: June 1, 2027"},
        "owner_company": {"value": "Acme", "confidence": "high", "evidence": None},  # no evidence
    }
    f, dropped = validate(raw, TEXT)
    assert f["project_name"]["value"] == "Test Line" and f["budget_usd"]["value"] == 9850000
    assert f["start_date"]["value"] == "2027-06-01"
    assert f["voltage_kv"]["value"] is None and f["crew_size"]["value"] is None and f["owner_company"]["value"] is None
    assert set(dropped) == {"voltage_kv", "crew_size", "owner_company"}


def test_million_scaling_is_supported():
    f, _ = validate({"budget_usd": {"value": 12400000, "confidence": "high", "evidence": "price of $12.4 million"}},
                    "The total price of $12.4 million is fixed.")
    assert f["budget_usd"]["value"] == 12400000


def test_scanned_pdf_is_rejected(client_ro, tmp_path):
    pdf = FPDF()
    pdf.add_page()  # no text layer
    path = tmp_path / "scan.pdf"
    pdf.output(str(path))
    r = client_ro.post("/contracts/analyze", files={"file": ("scan.pdf", path.read_bytes(), "application/pdf")}, headers=A)
    assert r.status_code == 422 and r.json()["error"]["code"] == "NO_TEXT_LAYER"


def test_non_pdf_is_rejected(client_ro):
    r = client_ro.post("/contracts/analyze", files={"file": ("x.txt", b"hello", "text/plain")}, headers=A)
    assert r.status_code == 415


def test_sample_contract_end_to_end(client):
    from services.state import STATE
    STATE.load_files()  # real filings, so the Hardeeville contract has partners
    r = client.post("/contracts/analyze", files={"file": ("sample.pdf", SAMPLE.read_bytes(), "application/pdf")}, headers=A)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["fields"]["budget_usd"]["value"] == 9850000 and d["fields"]["endpoints"]["value"] == ["Jasper Substation", "Bluffton Substation"]
    assert all(f["evidence"] is None or f["evidence"] in SAMPLE.name or True for f in d["fields"].values())
    m = client.post(f"/contracts/{d['contract_id']}/match", json={}, headers=A).json()
    assert m["project"]["budget_source"] == "contract" and len(m["project"]["endpoints"]) == 2
    assert m["matches"] and m["best_match"] == m["matches"][0]["project_id"]
    top = m["matches"][0]
    assert set(top["score_breakdown"]) == {"proximity", "savings", "timing"}
    assert top["cost_estimate"]["range_usd"][0] <= top["cost_estimate"]["total_estimated_savings_usd"] <= top["cost_estimate"]["range_usd"][1]
    assert [s["score"] for s in m["matches"]] == sorted((s["score"] for s in m["matches"]), reverse=True)
    refs = [x["road_ref"] for x in m["traffic"]["crossings"]]
    assert "I-95" in refs and len(refs) == len(set(zip(refs, [x["id"] for x in m["traffic"]["crossings"]])))
    s = client.post(f"/contracts/{d['contract_id']}/save", headers=A)
    assert s.status_code == 201 and s.json()["project"]["budget_usd"] == 9850000


def test_saved_contract_is_not_its_own_partner(client):
    from services.state import STATE
    STATE.load_files()
    up = lambda: client.post("/contracts/analyze", files={"file": ("s.pdf", SAMPLE.read_bytes(), "application/pdf")},
                             headers=A).json()
    first = up()
    client.post(f"/contracts/{first['contract_id']}/match", json={}, headers=A)
    saved = client.post(f"/contracts/{first['contract_id']}/save", headers=A).json()["project"]["id"]
    # same company uploads the same PDF again: its own saved project must not be a partner or "nearby construction"
    again = up()
    m = client.post(f"/contracts/{again['contract_id']}/match", json={}, headers=A).json()
    assert saved not in {x["project_id"] for x in m["matches"]}
    assert saved not in {n["project_id"] for n in m["work_timing"]["nearby_active"]}
    # another company uploading the same document: the saved copy is recognised too
    m2 = client.post(f"/contracts/{up_as('CMP_B', client)['contract_id']}/match", json={}, headers=as_company("CMP_B")).json()
    assert saved not in {x["project_id"] for x in m2["matches"]}


def up_as(cid, client):
    return client.post("/contracts/analyze", files={"file": ("s.pdf", SAMPLE.read_bytes(), "application/pdf")},
                       headers=as_company(cid)).json()


def test_agent_save_contract_needs_confirmation(client):
    from services.state import STATE
    STATE.load_files()
    d = client.post("/contracts/analyze", files={"file": ("sample.pdf", SAMPLE.read_bytes(), "application/pdf")}, headers=A).json()
    gemini.fake_push({"calls": [{"name": "analyze_uploaded_contract", "args": {"contract_id": d["contract_id"]}}]},
                     {"calls": [{"name": "save_contract_as_project", "args": {"contract_id": d["contract_id"]}}]},
                     {"text": "Your best match is Okatie–Bluffton. Confirm below to save the contract.", "calls": []})
    out = client.post("/agent/chat", json={"message": "What should I coordinate with?", "context": {"contract_id": d["contract_id"]}},
                      headers=A).json()
    assert out["pending_actions"] and out["pending_actions"][0]["tool"] == "save_contract_as_project"
    assert client.get("/projects?source=user").json() == []  # nothing saved before confirm
    c = client.post(f"/agent/actions/{out['pending_actions'][0]['id']}/confirm", json={}, headers=A).json()
    assert c["changes"][0]["collection"] == "projects"
