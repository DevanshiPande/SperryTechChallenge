"""Gridlock Assistant: Gemini function calling over read tools + pending-action write tools.

Writes never execute from chat: a write tool call creates a pending action; POST /agent/actions/{id}/confirm runs it."""
import logging
from datetime import date, datetime, timedelta, timezone

from ai import fakes, gemini, prompts, tools
from ai.validate import ID_RE, id_check, number_check
from db import mongo
from services import events
from services.common import new_id
from services.errors import ApiError, bad_request, forbidden, gemini_unavailable, not_found
from services.state import require_db

log = logging.getLogger("gridlock.agent")

MAX_ITERATIONS = 5
HISTORY_TO_MODEL = 20
HISTORY_KEEP = 30
ACTION_TTL = timedelta(minutes=30)
CONTRACT_PAGES = {"map", "opportunities", "feasibility", "cost", "inventory", "jobs", "addProject", "road_closures", "contracts"}
ASK_PAGE = {"projects": "map"}  # /ask uses the prototype's page names


def _now():
    return datetime.now(timezone.utc)


# ---------- history ----------
def _model_history(messages):
    """Thread messages -> what the model sees: last N, starting at a user turn; notes become user text."""
    msgs = messages[-HISTORY_TO_MODEL:]
    while msgs and msgs[0]["role"] != "user":
        msgs = msgs[1:]
    out = []
    for m in msgs:
        if m["role"] == "note":
            m = {"role": "user", "text": f"[Gridlock update] {m['text']}"}
        if m["role"] == "user" and out and out[-1]["role"] == "user":
            out[-1] = {"role": "user", "text": out[-1]["text"] + "\n" + m["text"]}
        else:
            out.append({k: v for k, v in m.items() if k in ("role", "text", "calls", "results")})
    return out


def _cited(results):
    """IDs from tool results, latest tool call first (the most specific lookup), max 5 per kind."""
    ids = []
    for r in reversed(results):
        for i in ID_RE.findall(str(r)):
            if i not in ids:
                ids.append(i)
    pick = lambda prefixes: [i for i in ids if i.split("_")[0] in prefixes][:5]  # noqa: E731
    return {"projects": pick(("DESC", "GPC", "USR")), "overlaps": pick(("OVL",)), "resources": pick(("RES",)),
            "jobs": pick(("JOB",))}


def _intent(last_call, last_result, ask=False):
    if not last_call:
        return {"action": "none"}
    page = tools.page_for(last_call["name"])
    if ask:
        page = ASK_PAGE.get(page, page)
        if page not in CONTRACT_PAGES:
            return {"action": "none"}
    intent = {"action": "navigate", "page": page}
    args = last_call.get("args") or {}
    oid = args.get("overlap_id")
    if not oid and last_call["name"] == "list_overlaps" and isinstance(last_result, dict):
        ovs = last_result.get("overlaps") or []
        oid = ovs[0]["id"] if ovs else None
    if oid:
        intent["overlap_id"] = oid
    if args.get("project_id"):
        intent["project_id"] = args["project_id"]
    return intent


def _template_reply(turn_results, pending):
    """Code-built reply from tool results (used when the model's text fails a guard or never arrives)."""
    parts = []
    for name, res in turn_results:
        if not isinstance(res, dict):
            continue
        if "error" in res:
            parts.append(f"I couldn't complete {name.replace('_', ' ')}: {res['error']['message']}")
        elif name == "list_overlaps" and res.get("overlaps"):
            o = res["overlaps"][0]
            parts.append(f"Top result: {o['label']}, {o['center_distance_mi']} mi apart, "
                         f"{o['window_overlap_months']} months of overlapping construction, illustrative savings "
                         f"${o['illustrative_savings_usd']:,}.")
        elif name == "get_cost_scenario":
            t = res["totals"]
            parts.append(f"For {res['label']}: separate ${t['separate']:,}, coordinated ${t['coordinated']:,}, "
                         f"savings ${t['savings']:,} (illustrative).")
        elif name == "get_overlap":
            o = res["overlap"]
            parts.append(f"{o['label']}: {o['center_distance_mi']} mi apart, tier {o['tier']}.")
        elif "count" in res:
            parts.append(f"Found {res['count']} result(s) for {name.replace('_', ' ')}.")
    for p in pending:
        parts.append(f"I prepared this action: {p['summary']} Please confirm it below.")
    return " ".join(parts) or "I couldn't find anything for that. Try asking about overlaps, projects or equipment."


# ---------- the loop ----------
def _run(ident, history, system, read_only, thread_id=None, persist_actions=True):
    """Runs up to MAX_ITERATIONS model turns. Mutates `history`. Returns (reply, pending, turn_results, last_call)."""
    decls = tools.declarations(read_only=read_only)
    turn_results, pending, last_call, last_result, reply = [], [], None, None, None
    for _ in range(MAX_ITERATIONS):
        resp = gemini.chat_with_tools(system, _model_history(history), decls,
                                      fake=lambda: fakes.agent_turn(_model_history(history), read_only))
        calls = resp.get("calls") or []
        if not calls:
            reply = (resp.get("text") or "").strip() or None
            break
        history.append({"role": "model", "text": resp.get("text"), "calls": calls, "ts": mongo.now()})
        results = []
        for c in calls:
            name, args = c.get("name"), c.get("args") or {}
            try:
                if name in tools.READ:
                    res = tools.run_read(ident, name, args)
                elif name in tools.WRITE and not read_only:
                    res = _create_pending(ident, thread_id, name, args, pending, persist_actions)
                else:
                    res = {"error": {"code": "BAD_REQUEST", "message": f"Unknown tool {name}"}}
            except ApiError as e:
                res = tools.error_result(e)
            except Exception:  # a tool bug must not kill the chat
                log.exception("tool %s failed", name)
                res = tools.error_result(None)
            results.append({"name": name, "response": res})
            turn_results.append((name, res))
            last_call, last_result = {"name": name, "args": args}, res
        history.append({"role": "tool", "results": results, "ts": mongo.now()})
    return reply, pending, turn_results, last_call, last_result


def _guard(reply, history, turn_results, pending, user_text):
    facts = [r.get("results") for r in history if r["role"] == "tool"] + [user_text, date.today().isoformat(),
                                                                         [p["summary"] for p in pending]]
    if not reply:
        return _template_reply(turn_results, pending), "template"
    bad_nums = number_check(reply, facts)
    bad_ids = id_check(reply, set(ID_RE.findall(str(facts))))
    if bad_nums or bad_ids:
        log.info("agent reply guard failed: numbers=%s ids=%s", bad_nums[:5], bad_ids[:5])
        return _template_reply(turn_results, pending), "template"
    return reply, "gemini"


# ---------- pending actions ----------
def _create_pending(ident, thread_id, tool, args, pending, persist):
    norm, summary, preview = tools.validate_write(ident, tool, args)
    act = {"id": new_id("ACT"), "thread_id": thread_id, "company_id": ident.company_id, "tool": tool, "args": norm,
           "summary": summary, "preview": preview, "status": "pending", "created_at": mongo.now(),
           "expires_at": (_now() + ACTION_TTL).isoformat(timespec="seconds"), "result": None, "error": None}
    if persist:
        mongo.insert(require_db(), "pending_actions", act)
    pending.append({k: act[k] for k in ("id", "tool", "summary", "preview", "expires_at")})
    return {"pending_action_id": act["id"], "summary": summary,
            "note": "Not executed yet. The user must confirm this action in the app."}


def _load_action(ident, action_id):
    db = require_db()
    company = ident.require_company()
    act = mongo.clean(db.pending_actions.find_one({"_id": action_id}))
    if act is None:
        raise not_found("Action", action_id)
    if act["company_id"] != company["id"]:
        raise forbidden("This action belongs to another company")
    if act["status"] != "pending":
        raise ApiError("CONFLICT", f"Action is already {act['status']}")
    if act["expires_at"] < _now().isoformat(timespec="seconds"):
        mongo.update(db, "pending_actions", action_id, {"status": "expired"})
        raise ApiError("GONE", "This action expired. Ask the assistant again.")
    return db, act


def _append_note(db, thread_id, text):
    if not thread_id:
        return
    th = db.agent_threads.find_one({"_id": thread_id})
    if th:
        msgs = (th.get("messages") or []) + [{"role": "note", "text": text, "ts": mongo.now()}]
        mongo.update(db, "agent_threads", thread_id, {"messages": msgs[-HISTORY_KEEP:]})


def _summarize_result(result):
    if isinstance(result, dict):
        if "project" in result and isinstance(result["project"], dict):
            return {"project_id": result["project"]["id"], "overlap_ids": [o["id"] for o in result.get("overlaps", [])],
                    "closure_conflicts": result.get("closure_conflicts", [])}
        if "message" in result and isinstance(result["message"], dict):
            return {"conversation_id": result["conversation"]["id"], "message_id": result["message"]["id"]}
    return result


def confirm(ident, action_id, edited_args=None):
    db, act = _load_action(ident, action_id)
    if edited_args is not None and not isinstance(edited_args, dict):
        raise bad_request("args must be an object")
    args = {**act["args"], **(edited_args or {})}
    try:
        norm, _, _ = tools.validate_write(ident, act["tool"], args)
        result, changes, reply = tools.execute_write(ident, act["tool"], norm)
    except ApiError as e:
        mongo.update(db, "pending_actions", action_id, {"status": "failed", "error": e.message})
        _append_note(db, act["thread_id"], f"Action {action_id} failed: {e.message}")
        raise
    summary = _summarize_result(result)
    new = mongo.update(db, "pending_actions", action_id, {"status": "confirmed", "args": norm, "result": summary})
    created = ", ".join(f"{c['op']} {c['id']}" for c in changes)
    _append_note(db, act["thread_id"], f"Action {action_id} confirmed: {created}")
    events.emit("pending_actions", "update", action_id, f"Action {act['tool']} confirmed", ident.company_id,
                ident.company_id)
    return {"action": new, "result": result, "changes": changes, "reply": reply}


def cancel(ident, action_id):
    db, act = _load_action(ident, action_id)
    new = mongo.update(db, "pending_actions", action_id, {"status": "cancelled"})
    _append_note(db, act["thread_id"], f"Action {action_id} cancelled by the user.")
    return {"action": new}


# ---------- endpoints ----------
def chat(ident, message, thread_id=None, context=None):
    if not isinstance(message, str) or not message.strip():
        raise bad_request("message is required")
    if not gemini.available():
        raise gemini_unavailable("The assistant is unavailable right now (Gemini is not configured or not responding).")
    db = require_db()
    company = ident.require_company()
    context = context if isinstance(context, dict) else {}
    if thread_id:
        th = mongo.clean(db.agent_threads.find_one({"_id": thread_id}))
        if th is None:
            raise not_found("Thread", thread_id)
        if th["company_id"] != company["id"]:
            raise forbidden("This thread belongs to another company")
    else:
        th = mongo.insert(db, "agent_threads", {"id": new_id("THR"), "company_id": company["id"], "messages": []})
    history = list(th.get("messages") or [])
    history.append({"role": "user", "text": message.strip(), "ts": mongo.now()})
    system = prompts.agent_system(company["name"], (company.get("yard") or {}).get("label"), date.today().isoformat(),
                                  context.get("page"), context.get("overlap_id"), context.get("project_id"),
                                  contract_id=context.get("contract_id"))
    try:
        reply, pending, turn_results, last_call, last_result = _run(ident, history, system, False, th["id"])
    except gemini.GeminiUnavailable:
        raise gemini_unavailable("The assistant is unavailable right now (Gemini is not responding).")
    reply, source = _guard(reply, history, turn_results, pending, message)
    history.append({"role": "model", "text": reply, "ts": mongo.now()})
    mongo.update(db, "agent_threads", th["id"], {"messages": history[-HISTORY_KEEP:]})
    return {"thread_id": th["id"], "reply": reply, "pending_actions": pending, "changes": [],
            "intent": _intent(last_call, last_result), "cited_ids": _cited([r for _, r in turn_results]),
            "source": source}


def ask(ident, question, context=None):
    """Global Ask bar: the agent with read-only tools, one turn, no thread. Works without Mongo."""
    if not isinstance(question, str) or not question.strip():
        raise bad_request("question is required")
    if not gemini.available():
        raise gemini_unavailable("Gemini is not responding. Try again in a moment.")
    company = ident.company or {}
    context = context if isinstance(context, dict) else {}
    system = prompts.agent_system(company.get("name"), (company.get("yard") or {}).get("label"),
                                  date.today().isoformat(), context.get("page"), context.get("overlap_id"),
                                  context.get("project_id"), read_only=True)
    history = [{"role": "user", "text": question.strip()}]
    try:
        reply, pending, turn_results, last_call, last_result = _run(ident, history, system, True, None, False)
    except gemini.GeminiUnavailable:
        raise gemini_unavailable("Gemini is not responding. Try again in a moment.")
    reply, _ = _guard(reply, history, turn_results, pending, question)
    cited = _cited([r for _, r in turn_results])
    return {"intent": _intent(last_call, last_result, ask=True), "answer": reply,
            "cited_project_ids": cited["projects"], "cited_overlap_ids": cited["overlaps"]}


def get_thread(ident, thread_id):
    db = require_db()
    company = ident.require_company()
    th = mongo.clean(db.agent_threads.find_one({"_id": thread_id}))
    if th is None:
        raise not_found("Thread", thread_id)
    if th["company_id"] != company["id"]:
        raise forbidden("This thread belongs to another company")
    th["pending_actions"] = [mongo.clean(a) for a in db.pending_actions.find({"thread_id": thread_id})]
    return th
