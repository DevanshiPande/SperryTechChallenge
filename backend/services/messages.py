"""Company-to-company conversations and messages."""
from rapidfuzz import fuzz, process

from db import mongo
from services import events, identity
from services.errors import ApiError, bad_request, forbidden, not_found
from services.common import new_id
from services.state import require_db

MAX_TEXT = 4000


def _check_text(text):
    text = (text or "").strip()
    if not text:
        raise bad_request("text is required")
    if len(text) > MAX_TEXT:
        raise bad_request(f"text must be at most {MAX_TEXT} characters")
    return text


def resolve_company(name_or_id, exclude_id=None):
    """Exact id/name first, then fuzzy name match among companies."""
    comps = [c for c in identity.companies() if c["id"] != exclude_id]
    key = (name_or_id or "").strip()
    for c in comps:
        if key.upper() == c["id"] or key.lower() == c["name"].lower():
            return c
    if not key or not comps:
        raise not_found("Company", key or "(blank)")
    best = process.extractOne(key, {c["id"]: c["name"] for c in comps}, scorer=fuzz.WRatio)
    if best and best[1] >= 80:
        return next(c for c in comps if c["id"] == best[2])
    raise not_found("Company", key)


def _attachment(att):
    if not att:
        return None
    if att.get("type") != "cost_scenario" or not att.get("overlap_id"):
        raise bad_request("attachment must be {type: 'cost_scenario', overlap_id}")
    from services.projects import get_overlap
    o = get_overlap(att["overlap_id"])
    return {"type": "cost_scenario", "overlap_id": o["id"], "totals": o["cost_scenario"]["totals"]}


def list_conversations(ident):
    db = require_db()
    company = ident.require_company()
    docs = [mongo.clean(d) for d in db.conversations.find({"participant_company_ids": company["id"]})]
    names = {c["id"]: c["name"] for c in identity.companies()}
    for d in docs:
        d["participants"] = [{"id": cid, "name": names.get(cid)} for cid in d["participant_company_ids"]]
    return sorted(docs, key=lambda d: d.get("last_message_at") or "", reverse=True)


def _conversation(ident, cid):
    db = require_db()
    company = ident.require_company()
    doc = mongo.clean(db.conversations.find_one({"_id": cid}))
    if doc is None:
        raise not_found("Conversation", cid)
    if company["id"] not in doc["participant_company_ids"]:
        raise forbidden("You are not part of this conversation")
    return db, company, doc


def _post(db, company, conv, text, attachment):
    msg = mongo.insert(db, "messages", {"id": new_id("MSG"), "conversation_id": conv["id"],
                                        "sender_company_id": company["id"], "sender_name": company["name"],
                                        "text": text, "attachment": attachment})
    mongo.update(db, "conversations", conv["id"], {"last_message_at": msg["created_at"],
                                                   "last_message_preview": text[:80]})
    events.emit("messages", "insert", msg["id"], f"New message from {company['name']}", company["id"],
                conv["participant_company_ids"])
    return msg


def create_conversation(ident, data):
    db = require_db()
    company = ident.require_company()
    to = resolve_company(data.get("to_company_id") or data.get("to_company_name"), exclude_id=None)
    if to["id"] == company["id"]:
        raise bad_request("You cannot message your own company")
    text = _check_text(data.get("text"))
    topic = (data.get("topic") or "").strip() or "Coordination"
    overlap_id = data.get("overlap_id") or None
    if overlap_id:
        from services.projects import get_overlap
        get_overlap(overlap_id)
    att = _attachment(data.get("attachment"))
    conv = mongo.insert(db, "conversations", {"id": new_id("CNV"), "participant_company_ids": [company["id"], to["id"]],
                                              "topic": topic, "overlap_id": overlap_id, "last_message_at": mongo.now(),
                                              "last_message_preview": text[:80]})
    events.emit("conversations", "insert", conv["id"], f"{company['name']} started a conversation", company["id"],
                conv["participant_company_ids"])
    msg = _post(db, company, conv, text, att)
    return {"conversation": mongo.clean(db.conversations.find_one({"_id": conv["id"]})), "message": msg}


def list_messages(ident, cid):
    db, _, _ = _conversation(ident, cid)
    return [mongo.clean(d) for d in db.messages.find({"conversation_id": cid}).sort("created_at", 1)]


def post_message(ident, cid, data):
    db, company, conv = _conversation(ident, cid)
    return _post(db, company, conv, _check_text(data.get("text")), _attachment(data.get("attachment")))


def send_to_company(ident, to_company_name, text, overlap_id=None):
    """Agent helper: append to an existing conversation with that company (same overlap) or start one."""
    db = require_db()
    company = ident.require_company()
    to = resolve_company(to_company_name, exclude_id=company["id"])
    q = {"participant_company_ids": {"$all": [company["id"], to["id"]]}}
    if overlap_id:
        q["overlap_id"] = overlap_id
    existing = db.conversations.find_one(q, sort=[("last_message_at", -1)])
    if existing:
        conv = mongo.clean(existing)
        return {"conversation": conv, "message": _post(db, company, conv, _check_text(text), None)}
    return create_conversation(ident, {"to_company_id": to["id"], "text": text, "overlap_id": overlap_id,
                                       "topic": "Coordination" if not overlap_id else f"Coordination on {overlap_id}"})


def check_send(ident, to_company_name, text):
    company = ident.require_company()
    to = resolve_company(to_company_name, exclude_id=company["id"])
    _check_text(text)
    if to["id"] == company["id"]:
        raise ApiError("BAD_REQUEST", "You cannot message your own company")
    return to
