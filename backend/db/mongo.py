"""MongoDB connection, indexes and counters."""
import logging
import os
from datetime import datetime, timezone

from pymongo import ASCENDING, ReturnDocument

log = logging.getLogger("gridlock.db")

INDEXES = [
    ("projects", "source.type", False), ("projects", "company_id", False),
    ("overlaps", "project_a", False), ("overlaps", "project_b", False), ("overlaps", "kind", False),
    ("resources", "company_id", False), ("reservations", "resource_id", False), ("jobs", "status", False),
    ("events", "seq", True), ("gemini_cache", "key", True), ("geocode_cache", "key", True),
    ("pending_actions", "thread_id", False), ("messages", "conversation_id", False),
]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def connect(uri=None, db_name=None, timeout_ms=5000):
    """Returns a pymongo Database, or None if MONGO_URI is missing or Mongo is unreachable (read-only mode)."""
    uri = uri or os.environ.get("MONGO_URI")
    if not uri:
        log.warning("MONGO_URI not set: read-only mode")
        return None
    try:
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms, connectTimeoutMS=timeout_ms, tz_aware=True)
        client.admin.command("ping")
        db = client[db_name or os.environ.get("MONGO_DB", "gridlock")]
        ensure_indexes(db)
        log.info("connected to MongoDB database %s", db.name)
        return db
    except Exception as e:  # unreachable, auth failure, DNS
        log.warning("MongoDB unavailable (%s): read-only mode", type(e).__name__)
        return None


def ensure_indexes(db):
    for coll, field, unique in INDEXES:
        db[coll].create_index([(field, ASCENDING)], unique=unique)
    try:
        db.gemini_cache.create_index("created_at_dt", expireAfterSeconds=7 * 24 * 3600)
    except Exception:
        pass


def next_seq(db, name):
    doc = db.counters.find_one_and_update({"_id": name}, {"$inc": {"seq": 1}}, upsert=True,
                                          return_document=ReturnDocument.AFTER)
    return doc["seq"]


def clean(doc):
    """Mongo doc -> API dict: _id becomes id, never leaks _id."""
    if doc is None:
        return None
    d = dict(doc)
    _id = d.pop("_id", None)
    d.setdefault("id", _id)
    d.pop("created_at_dt", None)
    return d


def insert(db, coll, doc):
    ts = now()
    d = {**doc, "_id": doc["id"], "created_at": doc.get("created_at") or ts, "updated_at": ts}
    db[coll].insert_one(d)
    return clean(d)


def update(db, coll, id_, fields):
    fields = {**fields, "updated_at": now()}
    doc = db[coll].find_one_and_update({"_id": id_}, {"$set": fields}, return_document=ReturnDocument.AFTER)
    return clean(doc)
