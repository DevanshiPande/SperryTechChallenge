"""Idempotent seed: public filing data (always re-synced) + demo companies, worker, listings (only when empty).

Demo records are labeled "(demo)". Phone numbers use the reserved fictional 555-01xx range."""
import logging

from db import mongo
from services.common import date_label

log = logging.getLogger("gridlock.seed")

DEMO_COMPANIES = [
    {"id": "CMP_A", "name": "Demo Contractor A", "type": "contractor",
     "yard": {"label": "Savannah, GA", "lat": 32.0809, "lon": -81.0912}, "phone": "(555) 010-0101"},
    {"id": "CMP_B", "name": "Demo Contractor B", "type": "contractor",
     "yard": {"label": "Hardeeville, SC", "lat": 32.2871, "lon": -81.079}, "phone": "(555) 010-0102"},
    {"id": "CMP_C", "name": "Coastal Crane (demo)", "type": "contractor",
     "yard": {"label": "Pooler, GA", "lat": 32.1155, "lon": -81.247}, "phone": "(555) 010-0103"},
]
DEMO_WORKERS = [
    {"id": "WRK_1", "name": "Jordan Davis (demo)", "trade": "Transmission lineworker",
     "certifications": ["OSHA 10", "CDL Class A", "Journeyman Lineworker"], "experience": "6 years (demo profile)",
     "availability": "Available from Jun 2027",
     "service_area": {"label": "Savannah, GA", "lat": 32.0809, "lon": -81.0912, "radius_mi": 50}},
]


def _company(cid):
    return next(c for c in DEMO_COMPANIES if c["id"] == cid)


def _resource(rid, cid, name, rtype, qty, loc, start, end, rate, notes):
    c = _company(cid)
    return {"id": rid, "company_id": cid, "company_name": c["name"], "name": name, "type": rtype, "quantity": qty,
            "location": loc, "available_from": start, "available_to": end, "date_label": date_label(start, end),
            "daily_rate": rate, "rate_label": f"${rate:,}/day per unit" if rate else "Rate on request",
            "notes": notes, "nearby_project_ids": [], "demo": True}


def _job(jid, cid, title, openings, loc, pay_min, pay_max, start, end, quals):
    c = _company(cid)
    return {"id": jid, "company_id": cid, "company_name": c["name"], "title": title, "openings": openings,
            "location": loc, "pay_min": pay_min, "pay_max": pay_max, "pay_label": f"${pay_min}–${pay_max}/hr",
            "start_date": start, "end_date": end, "date_label": date_label(start, end), "qualifications": quals,
            "project_id": None, "status": "open", "demo": True}


SAV = {"label": "Savannah, GA", "lat": 32.0809, "lon": -81.0912}
HAR = {"label": "Hardeeville, SC", "lat": 32.2871, "lon": -81.079}
POO = {"label": "Pooler, GA", "lat": 32.1155, "lon": -81.247}

DEMO_RESOURCES = [
    _resource("RES_DEMO1", "CMP_A", "Bucket trucks with operators", "equipment", 2, SAV, "2027-06-03", "2027-06-10", 1250,
              "Demo listing. 45 ft bucket trucks, operators included."),
    _resource("RES_DEMO2", "CMP_C", "60-ton crane", "equipment", 1, POO, "2027-05-01", "2027-08-31", None,
              "Demo listing. Operator and rigger available."),
    _resource("RES_DEMO3", "CMP_B", "Certified lineworkers", "crew", 4, HAR, "2027-06-01", "2027-12-15", 900,
              "Demo listing. Four-person transmission crew."),
]
DEMO_JOBS = [
    _job("JOB_DEMO1", "CMP_B", "Transmission lineworker", 3, HAR, 38, 46, "2027-06-01", "2027-12-15",
         ["Journeyman Lineworker", "CDL Class A", "OSHA 10"]),
    _job("JOB_DEMO2", "CMP_A", "Substation electrician", 2, SAV, 34, 42, "2027-03-01", "2027-09-30",
         ["Journeyman Electrician", "NFPA 70E"]),
    _job("JOB_DEMO3", "CMP_C", "Bucket truck operator", 1, POO, 28, 34, "2027-05-01", "2027-08-31",
         ["CDL Class A", "Aerial lift certification"]),
]


def sync_public(db, projects, overlaps):
    """Replace public filing docs; never touches user docs."""
    db.projects.delete_many({"source.type": "public_filing"})
    db.overlaps.delete_many({"kind": "cross_utility"})
    if projects:
        db.projects.insert_many([{**p, "_id": p["id"], "created_at": mongo.now(), "updated_at": mongo.now()}
                                 for p in projects])
    if overlaps:
        db.overlaps.insert_many([{**o, "_id": o["id"], "created_at": mongo.now(), "updated_at": mongo.now()}
                                 for o in overlaps])


def seed_demo(db, top_overlap_id=None):
    if db.companies.count_documents({}) > 0:
        return False
    for c in DEMO_COMPANIES:
        mongo.insert(db, "companies", c)
    for w in DEMO_WORKERS:
        mongo.insert(db, "workers", w)
    from services import resources
    for r in DEMO_RESOURCES:
        mongo.insert(db, "resources", {**r, "nearby_project_ids": resources.nearby_projects(r["location"])})
    for j in DEMO_JOBS:
        mongo.insert(db, "jobs", j)
    text = ("Hi, this is a demo thread. Our crews are near the Jasper–Okatie work next year; "
            "want to compare schedules and share a laydown yard?")
    conv = {"id": "CNV_DEMO1", "participant_company_ids": ["CMP_A", "CMP_B"], "topic": "Sharing a laydown yard (demo)",
            "overlap_id": top_overlap_id, "last_message_at": mongo.now(), "last_message_preview": text[:80]}
    mongo.insert(db, "conversations", conv)
    mongo.insert(db, "messages", {"id": "MSG_DEMO1", "conversation_id": "CNV_DEMO1", "sender_company_id": "CMP_B",
                                  "sender_name": "Demo Contractor B", "text": text, "attachment": None})
    log.info("seeded demo companies, worker, resources, jobs, conversation")
    return True


def run(db, projects, overlaps):
    sync_public(db, projects, overlaps)
    top = min(overlaps, key=lambda o: o["rank"])["id"] if overlaps else None
    seed_demo(db, top)
    # Public data may have changed since user overlaps were computed: recompute them.
    from services import projects as psvc
    for p in psvc.user_projects():
        psvc._recompute_overlaps(db, p, None)
