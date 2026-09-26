"""Agent flows (spec 12.6) with scripted fake Gemini tool calls."""
from ai import gemini
from conftest import as_company

A, B = as_company("CMP_A"), as_company("CMP_B")


def call(tool, /, **args):
    return {"calls": [{"name": tool, "args": args}]}


def text(t):
    return {"text": t, "calls": []}


def test_i_have_2_cranes(client):
    gemini.fake_push(call("add_resource", name="Crane", type="equipment", quantity=2),
                     text("I can add 2 cranes to your inventory at your Savannah yard. Confirm below."))
    r = client.post("/agent/chat", json={"message": "I have 2 cranes"}, headers=A)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["source"] == "gemini" and out["changes"] == []
    assert out["intent"] == {"action": "navigate", "page": "inventory"}
    [act] = out["pending_actions"]
    assert act["tool"] == "add_resource"
    assert "Savannah, GA" in act["summary"] and "company yard" in act["summary"] and "30 days" in act["summary"]
    assert client.get("/resources?q=crane&company_id=CMP_A").json() == []  # nothing written yet

    c = client.post(f"/agent/actions/{act['id']}/confirm", json={}, headers=A)
    assert c.status_code == 200, c.text
    body = c.json()
    assert body["action"]["status"] == "confirmed"
    assert body["changes"][0]["collection"] == "resources" and body["changes"][0]["op"] == "insert"
    rid = body["result"]["id"]
    assert body["reply"].startswith("Added 2 cranes to your inventory")
    ev = client.get("/events?since=0", headers=B).json()["events"]
    assert any(e["collection"] == "resources" and e["op"] == "insert" and e["doc_id"] == rid for e in ev)
    assert rid in {x["id"] for x in client.get("/resources", headers=B).json()}
    # the thread records the confirmation
    th = client.get(f"/agent/threads/{out['thread_id']}", headers=A).json()
    assert any(m["role"] == "note" and "confirmed" in m["text"] for m in th["messages"])
    # a second confirm is a conflict
    assert client.post(f"/agent/actions/{act['id']}/confirm", json={}, headers=A).status_code == 409


def test_confirm_with_edits_and_other_company(client):
    gemini.fake_push(call("add_resource", name="Crane", type="equipment", quantity=2), text("Confirm below."))
    act = client.post("/agent/chat", json={"message": "I have 2 cranes"}, headers=A).json()["pending_actions"][0]
    assert client.post(f"/agent/actions/{act['id']}/confirm", json={}, headers=B).status_code == 403
    c = client.post(f"/agent/actions/{act['id']}/confirm", json={"args": {"quantity": 3, "location_text": "Pooler"}},
                    headers=A).json()
    assert c["result"]["quantity"] == 3 and c["result"]["location"]["label"] == "Pooler, GA"


def test_cancel(client):
    gemini.fake_push(call("add_resource", name="Crane", type="equipment", quantity=1), text("Confirm below."))
    act = client.post("/agent/chat", json={"message": "add a crane"}, headers=A).json()["pending_actions"][0]
    assert client.post(f"/agent/actions/{act['id']}/cancel", headers=A).json()["action"]["status"] == "cancelled"
    assert client.post(f"/agent/actions/{act['id']}/confirm", json={}, headers=A).status_code == 409


def test_create_project_flow(client):
    msg = ("Add a corridor upgrade near Hardeeville from June to December 2027 with a nightly lane closure on US-17")
    gemini.fake_push(call("create_project", name="Corridor upgrade", location_text="Hardeeville, SC",
                          start_date="2027-06-01", end_date="2027-12-31", roads_affected="US-17",
                          lane_closures="Nightly lane closure", work_hours="21:00-05:00"),
                     text("I can add the corridor upgrade near Hardeeville. Confirm below."))
    out = client.post("/agent/chat", json={"message": msg}, headers=B).json()
    [act] = out["pending_actions"]
    assert act["tool"] == "create_project" and "Hardeeville" in act["summary"]
    assert any(o["project_id"] == "DESC_3" for o in act["preview"]["overlaps_preview"])
    assert client.get("/overlaps?kind=user_project").json() == []
    c = client.post(f"/agent/actions/{act['id']}/confirm", json={}, headers=B).json()
    pid = c["result"]["project"]["id"]
    assert c["result"]["project"]["center"] == {"lat": 32.2871, "lon": -81.079}  # geocoded, never from Gemini
    ovs = client.get("/overlaps?kind=user_project").json()
    assert f"OVL_{pid}__DESC_3" in {o["id"] for o in ovs}


def test_which_opportunity_saves_most(client):
    gemini.fake_push(call("list_overlaps", kind="cross_utility", sort="score", limit=3),
                     call("get_cost_scenario", overlap_id="OVL_DESC_3__GPC_2"),
                     text("Jasper–Okatie ↔ McIntosh–Purrysburg saves about $17,000 (37.0%) in the illustrative "
                          "scenario."))
    out = client.post("/agent/chat", json={"message": "Which opportunity saves the most?"}, headers=A).json()
    assert out["source"] == "gemini" and "$17,000" in out["reply"]
    assert out["intent"] == {"action": "navigate", "page": "cost", "overlap_id": "OVL_DESC_3__GPC_2"}
    assert "OVL_DESC_3__GPC_2" in out["cited_ids"]["overlaps"]


def test_reply_with_invented_number_is_replaced(client):
    gemini.fake_push(call("get_cost_scenario", overlap_id="OVL_DESC_3__GPC_2"),
                     text("This saves $250,000 for sure."))
    out = client.post("/agent/chat", json={"message": "How much does it save?"}, headers=A).json()
    assert out["source"] == "template" and "250,000" not in out["reply"] and "$17,000" in out["reply"]


def test_cannot_touch_other_company_resource(client):
    gemini.fake_push(call("update_resource", resource_id="RES_DEMO2", fields={"quantity": 9}),
                     text("I can't change that listing because it belongs to another company."))
    out = client.post("/agent/chat", json={"message": "Set the crane to 9"}, headers=A).json()
    assert out["pending_actions"] == []
    th = client.get(f"/agent/threads/{out['thread_id']}", headers=A).json()
    tool_msgs = [m for m in th["messages"] if m["role"] == "tool"]
    assert tool_msgs[-1]["results"][0]["response"]["error"]["code"] == "FORBIDDEN"
    assert th["pending_actions"] == []


def test_missing_project_fields_returned_to_model(client):
    gemini.fake_push(call("create_project", name="Corridor upgrade", location_text="Hardeeville"),
                     text("What are the start and end dates?"))
    out = client.post("/agent/chat", json={"message": "add a project near Hardeeville"}, headers=A).json()
    assert out["pending_actions"] == [] and out["reply"] == "What are the start and end dates?"
    th = client.get(f"/agent/threads/{out['thread_id']}", headers=A).json()
    err = [m for m in th["messages"] if m["role"] == "tool"][-1]["results"][0]["response"]["error"]
    assert "start_date" in err["message"] and "end_date" in err["message"]


def test_thread_continues_and_is_company_scoped(client):
    gemini.fake_push(text("Hello."))
    tid = client.post("/agent/chat", json={"message": "hi"}, headers=A).json()["thread_id"]
    gemini.fake_push(text("Again."))
    assert client.post("/agent/chat", json={"message": "hi", "thread_id": tid}, headers=A).json()["thread_id"] == tid
    assert client.post("/agent/chat", json={"message": "hi", "thread_id": tid}, headers=B).status_code == 403
    assert len(client.get(f"/agent/threads/{tid}", headers=A).json()["messages"]) == 4


def test_no_key_is_503(client, monkeypatch):
    monkeypatch.setenv("FAKE_GEMINI", "0")
    r = client.post("/agent/chat", json={"message": "hi"}, headers=A)
    assert r.status_code == 503 and r.json()["error"]["code"] == "GEMINI_UNAVAILABLE"


def test_ask_is_read_only_and_cites_tool_ids(client_ro):
    gemini.fake_push(call("add_resource", name="Crane", type="equipment", quantity=2),
                     call("get_overlap", overlap_id="OVL_DESC_2__GPC_1"),
                     text("Hooks–Thurmond and Evans–Thurmond share the Thurmond substation, 4.09 mi apart."))
    out = client_ro.post("/ask", json={"question": "Tell me about Thurmond"}).json()
    assert out["intent"] == {"action": "navigate", "page": "opportunities", "overlap_id": "OVL_DESC_2__GPC_1"}
    assert out["cited_overlap_ids"] == ["OVL_DESC_2__GPC_1"]
    assert set(out["cited_project_ids"]) == {"DESC_2", "GPC_1"}
    assert "4.09" in out["answer"]
