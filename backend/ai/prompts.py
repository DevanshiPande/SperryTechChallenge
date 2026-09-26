"""Every Gemini prompt template."""
import json

# ---------- 11.2 parsing fallback (pipeline only) ----------
SPLIT_SCHEMA = {
    "type": "object",
    "properties": {
        "endpoint_a": {"type": "string"},
        "endpoint_b": {"type": ["string", "null"]},
        "voltage_kv": {"type": ["integer", "null"]},
        "project_kind": {"type": "string", "enum": ["line", "substation", "equipment", "other"]},
    },
    "required": ["endpoint_a", "endpoint_b", "voltage_kv", "project_kind"],
}


def split_prompt(title):
    return ("Extract the substation endpoint names from this electric transmission project title. "
            "Return only names that appear verbatim in the title. "
            f"Title: {title}")


# ---------- 11.3 brief ----------
BRIEF_TASKS = {
    "summary": "Write 3–4 plain sentences for a utility planner explaining why these two projects are a coordination opportunity.",
    "plan": "Write a 4-step numbered coordination plan.",
    "risks": "List 3–5 short risks, one sentence each.",
    "traffic": "Write a short traffic-management note (3–4 sentences): which roads the work crosses, the recommended "
               "closure window for each, how much delay a daytime closure would cause instead, and whether closures on a "
               "shared road should be merged.",
}
BRIEF_RULES = ("Use ONLY facts and numbers from FACTS. Do not add numbers, dates, or names that are not in FACTS. "
               "If something is unknown, say so. Plain text only, no markdown headings or bold. Write for a utility planner: "
               "refer to projects by short name, describe quality flags in plain words, and do not print internal "
               "IDs or flag codes.")


def brief_prompt(mode, facts):
    return f"{BRIEF_TASKS[mode]}\n{BRIEF_RULES}\n\nFACTS:\n{json.dumps(facts, indent=1, ensure_ascii=False)}"


# ---------- 11.4 draft ----------
DRAFT_FIELDS = {
    "project": ["name", "description", "location", "start_date", "end_date", "work_type", "lane_closures", "work_hours",
                "roads_affected"],
    "resource": ["name", "quantity", "location", "dates", "rate"],
    "job": ["role", "openings", "project", "dates", "requirements"],
}
DRAFT_FIELD_HINTS = {
    "project": "location = a town, road segment or address as the user wrote it; start_date/end_date = YYYY-MM-DD; "
               "roads_affected = road IDs like US-17; work_hours = e.g. '9 PM – 5 AM'.",
    "resource": "name = the equipment or crew; quantity = integer; location = a town or address; "
                "dates = 'YYYY-MM-DD to YYYY-MM-DD'; rate = the price as written (e.g. '$1,250/day').",
    "job": "role = job title; openings = integer; project = the project it is for; dates = 'YYYY-MM-DD to YYYY-MM-DD'; "
           "requirements = certifications or qualifications.",
}


def draft_schema(kind):
    field = {
        "type": "object",
        "properties": {"value": {"type": ["string", "number", "null"]},
                       "confidence": {"type": ["string", "null"], "description": "high, medium, or null when absent"}},
        "required": ["value", "confidence"],
    }
    props = {k: field for k in DRAFT_FIELDS[kind]}
    props["follow_up_questions"] = {"type": "array", "items": {"type": "string"}}
    return {"type": "object", "properties": props, "required": DRAFT_FIELDS[kind] + ["follow_up_questions"]}


def draft_prompt(kind, text, draft, today):
    return (f"Extract fields from the user's message for a {kind} draft. Only extract what the user stated. "
            "confidence = high if stated explicitly, medium if inferred. Use null when absent. Dates as YYYY-MM-DD. "
            "If the year is not stated, return null and ask for it. If a month and year are given without a day, use "
            "the first day of the start month and the last day of the end month (confidence medium). A short title "
            "(name, role) may be derived from the work described (confidence medium). Also return up to 3 short "
            "follow-up questions for the most important missing fields.\n"
            f"Fields: {', '.join(DRAFT_FIELDS[kind])}. {DRAFT_FIELD_HINTS[kind]}\n"
            "Fields already in CURRENT DRAFT were set by the user: do not change them.\n"
            f"Today is {today}.\n"
            f"CURRENT DRAFT: {json.dumps(draft or {}, ensure_ascii=False)}\n"
            f"USER MESSAGE: {text}")


# ---------- 11.5 scenario assist ----------
SCENARIO_PATHS = [
    "unit_rates.mobilization_per_event", "unit_rates.bucket_truck_per_day", "unit_rates.laydown_per_site",
    "separate.a.truck_days", "separate.b.truck_days", "separate.a.mobilization_events", "separate.b.mobilization_events",
    "separate.a.laydown_sites", "separate.b.laydown_sites", "coordinated.shared_truck_days", "coordinated.laydown_sites",
    "coordinated.mobilization_events_a", "coordinated.mobilization_events_b",
]
SCENARIO_SCHEMA = {
    "type": "object",
    "properties": {
        "changes": {"type": "array", "items": {
            "type": "object",
            "properties": {"path": {"type": "string", "enum": SCENARIO_PATHS}, "value": {"type": "number"},
                           "label": {"type": "string"}},
            "required": ["path", "value", "label"]}},
        "note": {"type": "string"},
    },
    "required": ["changes", "note"],
}


def scenario_prompt(facts, scenario_inputs, message):
    return ("The user wants to try a change to this cost scenario. Return which inputs to change. Allowed paths: "
            + ", ".join(f"`{p}`" for p in SCENARIO_PATHS)
            + ". Do not compute totals. Each label is a short plain description of the change. "
              "The note is one short sentence without numbers.\n"
            f"OVERLAP FACTS: {json.dumps(facts, ensure_ascii=False)}\n"
            f"CURRENT SCENARIO INPUTS: {json.dumps(scenario_inputs, ensure_ascii=False)}\n"
            f"USER MESSAGE: {message}")


# ---------- 12.2 agent ----------
AGENT_SYSTEM = """You are Gridlock Assistant inside a utility-construction coordination app.
The user is acting for the company "{company_name}".
You help them explore planned transmission projects from Dominion Energy South Carolina and
Georgia Power public filings, user-submitted projects, coordination opportunities (overlaps),
shared equipment and crews, jobs, and messages.

Rules:
- Use tools for every fact. Never state a number, distance, date, cost, location, or name that did
  not come from a tool result in this conversation.
- To create or change anything, call a write tool. Write tools do not execute: they create a pending
  action the user must confirm. Say clearly what will happen and that they need to confirm.
- If a required detail is missing, ask ONE short question instead of guessing. For a resource
  location you may offer the company yard ({yard_label}).
- You can act only for {company_name}. You cannot edit public utility filings or other companies' data.
- Refer to projects by short name. Keep replies to 1-4 sentences of plain text (no markdown).
- If asked about something unrelated to Gridlock, say you can only help with Gridlock.
Today is {today}. Current page: {page}. Selected overlap: {overlap_id}. Selected project: {project_id}."""

ASK_SYSTEM_SUFFIX = """
This is a one-turn question from the global search bar. You can only read data; do not propose changes.
Answer in 1-3 sentences."""


def agent_system(company_name, yard_label, today, page=None, overlap_id=None, project_id=None, read_only=False,
                 contract_id=None):
    s = AGENT_SYSTEM.format(company_name=company_name or "a guest (read-only)", yard_label=yard_label or "not set",
                            today=today, page=page or "unknown", overlap_id=overlap_id or "none",
                            project_id=project_id or "none")
    if contract_id:
        s += (f"\nThe user uploaded a contract ({contract_id}). Use analyze_uploaded_contract to summarize its best "
              "coordination match, then offer to save it as a project (save_contract_as_project).")
    return s + (ASK_SYSTEM_SUFFIX if read_only else "")
