"""Event log for live updates. The frontend polls GET /events?since=<seq>."""
from db import mongo
from services.state import STATE

MAX_EVENTS = 200


def emit(collection, op, doc_id, summary, company_id=None, visibility="all"):
    """visibility: "all" or a company id; a list of company ids emits one event per company."""
    db = STATE.db
    if db is None:
        return None
    targets = visibility if isinstance(visibility, (list, tuple, set)) else [visibility]
    out = None
    for vis in dict.fromkeys(v for v in targets if v):
        seq = mongo.next_seq(db, "events")
        ev = {"_id": f"EVT_{seq}", "seq": seq, "ts": mongo.now(), "company_id": company_id, "collection": collection,
              "op": op, "doc_id": doc_id, "summary": summary, "visibility": vis}
        db.events.insert_one(ev)
        out = ev
    return out


def since(seq, company_id=None):
    db = STATE.db
    if db is None:
        return {"latest_seq": 0, "events": []}
    vis = ["all"] + ([company_id] if company_id else [])
    cur = db.events.find({"seq": {"$gt": int(seq)}, "visibility": {"$in": vis}}).sort("seq", 1).limit(MAX_EVENTS)
    events = [mongo.clean(e) for e in cur]
    latest = db.counters.find_one({"_id": "events"})
    return {"latest_seq": (latest or {}).get("seq", 0), "events": events}
