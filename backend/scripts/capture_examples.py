"""Capture real responses from the new (M5-M9) endpoints into contract/examples/ and document them in API_README.md.

Runs the real app in-process on the answer-key fixture data with an in-memory Mongo, FAKE_GEMINI=1 (scripted agent
turns) and the test gazetteer, so the output is reproducible offline. Run from backend/:
    python scripts/capture_examples.py
"""
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests"))
os.environ["FAKE_GEMINI"] = "1"
os.environ["FAKE_GEOCODER"] = "1"
os.environ.pop("MONGO_URI", None)

import mongomock  # noqa: E402

import conftest  # noqa: E402
from ai import gemini  # noqa: E402

EX = BACKEND / "contract" / "examples"
README = BACKEND / "contract" / "API_README.md"
START, END = "<!-- NEW_ENDPOINTS_START -->", "<!-- NEW_ENDPOINTS_END -->"

A, B, C = {"X-Company-Id": "CMP_A"}, {"X-Company-Id": "CMP_B"}, {"X-Company-Id": "CMP_C"}
W = {"X-Worker-Id": "WRK_1"}
sections = []


def cap(fname, title, note, method, path, body=None, headers=None, show_path=None):
    client = cap.client
    r = client.request(method, path, json=body, headers=headers or {})
    data = r.json()
    (EX / fname).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    shown = data
    arr_note = ""
    if isinstance(data, list):
        arr_note = f"An **array** ({len(data)} items here). First item shown; every item has the same shape.\n\n"
        shown = data[:1]
    hdr = ", ".join(f"`{k}: {v}`" for k, v in (headers or {}).items())
    md = [f"### `{method} {show_path or path}`", "", note, ""]
    if hdr:
        md += [f"Headers: {hdr}", ""]
    if body is not None:
        md += ["Request body:", "```json", json.dumps(body, indent=2, ensure_ascii=False), "```", ""]
    md += [f"Response `{r.status_code}`:", "", arr_note + "```json", json.dumps(shown, indent=2, ensure_ascii=False),
           "```", "", f"Example file: `examples/{fname}`", "", "---", ""]
    sections.append((title, "\n".join(md)))
    return data


def main():
    cap.client = conftest._client(mongomock.MongoClient(tz_aware=True)["capture"])

    # identity
    cap("GET_companies.json", "Identity", "Demo companies for the company switcher. Send the chosen id as "
        "`X-Company-Id` on every request.", "GET", "/companies")
    cap("GET_me.json", "Identity", "Who the headers say you are: `company`, `worker` or `guest`. Guests can read "
        "everything but every write returns `401 UNAUTHORIZED`.", "GET", "/me", headers=A)

    # user projects
    proj = cap("POST_projects.json", "User projects",
               "Adds a user project. It joins the overlap analysis at once: it is compared with every project that has a "
               "different owner (both utilities' filings and other companies' projects). Location comes from "
               "`location_text` (geocoded) or 1-2 `endpoints` pins. Returns the project, its overlaps "
               "(`kind: \"user_project\"`) and lane-closure conflicts with other user projects.",
               "POST", "/projects", {"name": "Corridor upgrade", "location_text": "Near Hardeeville, SC",
                                     "start_date": "2027-06-01", "end_date": "2027-12-15", "work_type": "Roadway improvement",
                                     "roads_affected": "US-17", "lane_closures": "Northbound lane, nightly",
                                     "work_hours": "21:00-05:00"}, B)
    pid = proj["project"]["id"]
    cap("PATCH_project.json", "User projects", "Own user projects only (`403` for other companies and for public "
        "filings). Overlaps are recomputed. Same response shape as `POST /projects`.",
        "PATCH", f"/projects/{pid}", {"end_date": "2028-02-01"}, B, show_path="/projects/{id}")
    cap("GET_overlaps_user.json", "User projects", "Additive filter: `kind=cross_utility` is Sperry's ranked DESC x "
        "GPC list, `kind=user_project` the user-project overlaps (ranked among themselves). Default: both.",
        "GET", "/overlaps?kind=user_project")

    # resources
    res = cap("POST_resources.json", "Resources", "List equipment or a crew. `type`: `equipment` or `crew`. Location "
              "from `location_text`, `location {lat, lon, label}`, or the company yard when omitted. "
              "`nearby_project_ids` are projects within 40 km.", "POST", "/resources",
              {"name": "60-ton crane", "type": "equipment", "quantity": 2, "location_text": "Pooler, GA",
               "available_from": "2027-06-01", "available_to": "2027-06-30", "daily_rate": 1250,
               "notes": "Operator included"}, C)
    cap("GET_resources.json", "Resources", "Filters: `type`, `near=<lat,lon>` + `radius_km` (default 40; adds "
        "`distance_km` and sorts by it), `q`, `company_id`, `available_on=<date>`.",
        "GET", "/resources?near=32.1155,-81.247&radius_km=40")
    cap("PATCH_resource.json", "Resources", "Owner only. Any subset of the POST fields.",
        "PATCH", f"/resources/{res['id']}", {"quantity": 3}, C, show_path="/resources/{id}")

    # reservations
    rsv = cap("POST_reservation.json", "Reservations",
              "Request another company's resource. Rules: not your own (`400`), dates inside the availability window "
              "(`400`), and `quantity + accepted overlapping reservations <= resource.quantity` "
              "(`409 INSUFFICIENT_QUANTITY`). Starts `pending`.",
              "POST", f"/resources/{res['id']}/reservations", {"quantity": 2, "from": "2027-06-05", "to": "2027-06-10",
                                                               "note": "For the Hardeeville corridor work"}, A,
              show_path="/resources/{id}/reservations")
    cap("GET_reservations.json", "Reservations", "`role=incoming` (requests for my resources) or `outgoing` "
        "(my requests). Default: both.", "GET", "/reservations?role=incoming", headers=C)
    cap("PATCH_reservation.json", "Reservations", "The owner sets `accepted`/`declined`; the requester sets "
        "`cancelled`. Quantity is re-checked on accept.", "PATCH", f"/reservations/{rsv['id']}",
        {"status": "accepted"}, C, show_path="/reservations/{id}")
    cap("ERROR_409_quantity.json", "Reservations", "Over-booking.", "POST", f"/resources/{res['id']}/reservations",
        {"quantity": 2, "from": "2027-06-08", "to": "2027-06-09"}, B, show_path="/resources/{id}/reservations")

    # jobs
    job = cap("POST_jobs.json", "Jobs", "Post a job. Pay is per hour.", "POST", "/jobs",
              {"title": "Transmission lineworker", "openings": 3, "location_text": "Hardeeville, SC", "pay_min": 38,
               "pay_max": 46, "start_date": "2027-06-01", "end_date": "2027-12-15",
               "qualifications": ["Journeyman Lineworker", "CDL Class A"]}, B)
    cap("GET_jobs.json", "Jobs", "Open jobs. Filters: `q`, `near` + `radius_km`, `qualification`.",
        "GET", "/jobs?qualification=CDL")
    app = cap("POST_application.json", "Jobs", "A worker applies (`X-Worker-Id`). Fields default to the worker "
              "profile.", "POST", f"/jobs/{job['id']}/applications", {"availability": "Available from June 2027"}, W,
              show_path="/jobs/{id}/applications")
    cap("GET_applications.json", "Jobs", "Workers see their applications; companies see applications to their jobs.",
        "GET", "/applications", headers=B)
    cap("PATCH_application.json", "Jobs", "Job owner only. `status`: submitted, reviewed, accepted, rejected.",
        "PATCH", f"/applications/{app['id']}", {"status": "reviewed"}, B, show_path="/applications/{id}")

    # messages
    conv = cap("POST_conversations.json", "Messages", "Start a conversation with another company. Optional "
               "`overlap_id` and `attachment: {type: \"cost_scenario\", overlap_id}` (totals are filled in by the "
               "backend).", "POST", "/conversations",
               {"to_company_id": "CMP_C", "topic": "Crane for the corridor work", "overlap_id": "OVL_DESC_3__GPC_2",
                "text": "Could we share your crane in June 2027?",
                "attachment": {"type": "cost_scenario", "overlap_id": "OVL_DESC_3__GPC_2"}}, A)
    cid = conv["conversation"]["id"]
    cap("POST_message.json", "Messages", "Participants only.", "POST", f"/conversations/{cid}/messages",
        {"text": "Yes, both units are free June 5-10."}, C, show_path="/conversations/{id}/messages")
    cap("GET_conversations.json", "Messages", "The caller's conversations, newest first.", "GET", "/conversations",
        headers=A)
    cap("GET_messages.json", "Messages", "Participants only (`403` otherwise).", "GET",
        f"/conversations/{cid}/messages", headers=A, show_path="/conversations/{id}/messages")

    # agent
    gemini.fake_push({"calls": [{"name": "add_resource", "args": {"name": "Crane", "type": "equipment",
                                                                  "quantity": 2}}]},
                     {"text": "I can add 2 cranes to your inventory at your Savannah yard. Confirm below.",
                      "calls": []})
    chat = cap("POST_agent_chat.json", "Assistant (agent)",
               "Gemini with tools. Read tools run at once; write tools only create `pending_actions` the user must "
               "confirm. `changes` is always `[]` here. `intent` tells the UI where to navigate; `cited_ids` come "
               "from tool results, not model text. Every number in `reply` is checked against tool results "
               "(`source: \"template\"` when the check replaced the model text). `503 GEMINI_UNAVAILABLE` without a "
               "key.", "POST", "/agent/chat", {"message": "I have 2 cranes", "context": {"page": "inventory"}}, A)
    act = chat["pending_actions"][0]["id"]
    cap("POST_agent_confirm.json", "Assistant (agent)", "Runs the pending action (same company, while pending, "
        "within 30 minutes: `409`/`410` otherwise). Optional `args` override fields and are re-validated. "
        "`changes` lists what was written.", "POST", f"/agent/actions/{act}/confirm", {}, A,
        show_path="/agent/actions/{id}/confirm")
    gemini.fake_push({"calls": [{"name": "add_resource", "args": {"name": "Bucket truck", "type": "equipment",
                                                                  "quantity": 1}}]},
                     {"text": "I can add 1 bucket truck. Confirm below.", "calls": []})
    act2 = cap.client.post("/agent/chat", json={"message": "add a bucket truck", "thread_id": chat["thread_id"]},
                           headers=A).json()["pending_actions"][0]["id"]
    cap("POST_agent_cancel.json", "Assistant (agent)", "Cancel a pending action.", "POST",
        f"/agent/actions/{act2}/cancel", None, A, show_path="/agent/actions/{id}/cancel")
    cap("GET_agent_thread.json", "Assistant (agent)", "Thread history (last 30 messages) and its actions.",
        "GET", f"/agent/threads/{chat['thread_id']}", headers=A, show_path="/agent/threads/{id}")

    # ---- spec update 2: score v2 + sourced savings, site focus, traffic, contracts (real filings data)
    from services.state import STATE
    STATE.load_files()
    cap("GET_overlap_v2.json", "Score v2 and sourced savings",
        "Every overlap now carries `score_breakdown` (proximity 40 + savings 40 + timing 20), "
        "`schedule_shift_possible`, and `cost_estimate` v2: `total_estimated_savings_usd` (point), `range_usd`, "
        "`components` (mobilization, logistics, shared_land, traffic_delay; each low/point/high), the reference budget "
        "and its source, plus `sources[]` (named public sources and the values used) and `assumptions[]`. Old fields "
        "are kept. `cost_scenario` keeps its shape; defaults now come from `config/cost_sources.json` "
        "(`defaults_source`, `unit_rates.crew_size`, `unit_rates.crew_cost_per_day`).",
        "GET", "/overlaps/OVL_DESC_23__GPC_20277", show_path="/overlaps/{id}")
    cap("GET_overlaps_for_site.json", "Score v2 and sourced savings",
        "Additive filter `project_id`: every opportunity one work site is part of, best first. The frontend uses it "
        "when a site is selected on the map.", "GET", "/overlaps?project_id=DESC_23",
        show_path="/overlaps?project_id={id}")
    cap("GET_meta_v2.json", "Score v2 and sourced savings",
        "`/meta` adds `method_notes[]` (About/method text) and `traffic_data`.", "GET", "/meta")
    xs = cap("GET_traffic_crossings.json", "Traffic management",
             "Where planned lines cross major roads (OSM), with traffic volume (SCDOT 2025 / GDOT 2017 counts, else a "
             "labeled class estimate), closure type, the recommended closure window and its delay, and the worst window. "
             "Filters: `project_id`, `road_ref`, `min_aadt`. Crossing points are approximate (straight lines).",
             "GET", "/traffic/crossings?min_aadt=40000")
    xid = xs[0]["id"] if xs else "XING_DESC_23_1"
    cap("GET_traffic_crossing.json", "Traffic management",
        "One crossing with its full plan: `hourly` (24 x demand, capacity, queue) for a chart, sources and "
        "assumptions, and any closure conflicts on the same road.", "GET", f"/traffic/crossings/{xid}",
        show_path="/traffic/crossings/{id}")
    cap("POST_traffic_plan.json", "Traffic management",
        "Plan any proposed closure: nearest matching road to the point, optional overrides "
        "(`lanes`, `aadt`, `closure_hours`, `closure_type`).", "POST", "/traffic/plan",
        {"point": {"lat": 32.2871, "lon": -81.079}, "road_ref": "US-17", "closure_hours": 8})
    cap("GET_traffic_conflicts.json", "Traffic management",
        "Two owners closing the same road within 3 km while both are under construction: delay if merged into one "
        "closure (sign kept), closures and traffic-control setups avoided. Filters `kind`, `min_delay`.",
        "GET", "/traffic/conflicts")
    cap("GET_traffic_summary.json", "Traffic management", "Dashboard tile.", "GET", "/traffic/summary")
    cap("POST_crossing_brief.json", "Traffic management",
        "Gemini traffic-management note for one crossing, from computed facts only (number guard + template "
        "fallback). `POST /overlaps/{id}/brief` also accepts `mode: \"traffic\"`.",
        "POST", f"/traffic/crossings/{xid}/brief", {}, show_path="/traffic/crossings/{id}/brief")
    sample = BACKEND / "data" / "samples" / "sample_contract_hardeeville.pdf"
    r = cap.client.post("/contracts/analyze", files={"file": ("sample_contract_hardeeville.pdf", sample.read_bytes(),
                                                              "application/pdf")}, headers=A)
    d = r.json()
    (EX / "POST_contracts_analyze.json").write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    sections.append(("Contract upload", "\n".join([
        "### `POST /contracts/analyze`", "",
        "Multipart upload, form field `file` (PDF, 10 MB max). Text is extracted with pdfplumber; Gemini returns each "
        "field with an exact `evidence` quote. Code drops a field when its quote is not in the document or its numbers "
        "are not in the quote. Scanned PDFs: `422 NO_TEXT_LAYER`; non-PDF: `415 UNSUPPORTED_FILE`. The PDF is not "
        "stored, only its text hash and the fields.", "", f"Response `{r.status_code}`:", "", "```json",
        json.dumps(d, indent=2, ensure_ascii=False)[:3000] + ("\n..." if len(json.dumps(d)) > 3000 else ""), "```", "",
        "Example file: `examples/POST_contracts_analyze.json`", "", "---", ""])))
    m = cap("POST_contracts_match.json", "Contract upload",
            "Body: the reviewed fields (`{fields: {...}}`, only the ones the user changed). Locates the work "
            "(substation matcher, else Nominatim), compares it with every planned project under 25 mi, and returns "
            "`matches` sorted by score (with `score_breakdown`, `cost_estimate` v2, `suggestion`, `shared_roads`), "
            "`best_match`, the contract's own `traffic`, and a `summary`.",
            "POST", f"/contracts/{d['contract_id']}/match", {"fields": {}}, A, show_path="/contracts/{id}/match")
    cap("POST_contracts_save.json", "Contract upload",
        "Saves the reviewed contract as the company's user project (same as `POST /projects`, events emitted). "
        "The assistant tool `save_contract_as_project` does this only after confirmation.",
        "POST", f"/contracts/{d['contract_id']}/save", None, A, show_path="/contracts/{id}/save")

    # events + errors
    cap("GET_events.json", "Live updates", "Poll every few seconds with the last `latest_seq` you saw; refetch the "
        "collections that changed. Only events visible to the caller (public collections, or ones involving the "
        "caller's company).", "GET", "/events?since=0", headers=B)
    cap("ERROR_401.json", "Errors", "Writes without `X-Company-Id`.", "POST", "/resources",
        {"name": "Crane", "type": "equipment", "quantity": 1})
    cap("ERROR_403.json", "Errors", "Changing another company's record, or a public filing.", "PATCH",
        f"/resources/{res['id']}", {"quantity": 9}, A, show_path="/resources/{id}")

    # README
    order, grouped = [], {}
    for title, md in sections:
        if title not in grouped:
            order.append(title)
            grouped[title] = []
        grouped[title].append(md)
    doc = [START, "", "## New endpoints (real backend)", "",
           "Added by the real backend; the mock does not serve these. Identity is by header: `X-Company-Id` "
           "(e.g. `CMP_A`) for companies, `X-Worker-Id` (e.g. `WRK_1`) for workers. Without a database these "
           "return `503 DB_UNAVAILABLE`; the endpoints above keep working. Additive fields on existing objects: "
           "`overlap.kind` (`cross_utility` | `user_project`), `project.source.type` (`public_filing` | `user`), "
           "`project.user_overlap_ids` on public projects, `project.budget_usd`/`budget_source`/`budget_note`, "
           "`project.traffic` on `GET /projects/{id}`, `traffic` on `/whatif`, `overlap.score_breakdown`, "
           "`overlap.cost_estimate` v2, and new query params `GET /projects?source=`, `GET /overlaps?kind=` and "
           "`GET /overlaps?project_id=`.", "",
           "Errors also use `UNAUTHORIZED` (401), `FORBIDDEN` (403), `CONFLICT` / `INSUFFICIENT_QUANTITY` (409), "
           "`GONE` (410, expired assistant action), `NO_TEXT_LAYER` (422), `UNSUPPORTED_FILE` (415), "
           "`TRAFFIC_UNAVAILABLE` (503) and `DB_UNAVAILABLE` (503).", ""]
    for t in order:
        doc += [f"## {t}", ""] + grouped[t]
    doc.append(END)
    text = README.read_text(encoding="utf-8")
    block = "\n".join(doc)
    if START in text:
        text = text[:text.index(START)] + block + text[text.index(END) + len(END):]
    else:
        text = text.rstrip() + "\n\n---\n\n" + block + "\n"
    README.write_text(text, encoding="utf-8", newline="\n")
    print(f"captured {len(sections)} examples")


if __name__ == "__main__":
    main()
