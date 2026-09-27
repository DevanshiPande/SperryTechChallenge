"""Jobs and applications."""
from db import mongo
from engine import geo
from services import events
from services.common import date_label, new_id, parse_iso, parse_near, text_match
from services.errors import ApiError, bad_request, forbidden, not_found, unauthorized
from services.resources import resolve_location
from services.state import require_db

JOB_FIELDS = ("title", "openings", "location_text", "location", "pay_min", "pay_max", "start_date", "end_date",
              "qualifications", "project_id", "status")
APP_STATUSES = ("submitted", "reviewed", "accepted", "rejected")


def _num(v, name):
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise bad_request(f"{name} must be a number")
    if x < 0:
        raise bad_request(f"{name} must be 0 or more")
    return int(x) if x.is_integer() else x


def pay_label(lo, hi):
    if lo is None and hi is None:
        return "Pay on request"
    if lo is not None and hi is not None and lo != hi:
        return f"${lo:g}–${hi:g}/hr"
    return f"${(lo if lo is not None else hi):g}/hr"


def normalize_job(company, data, partial=False, existing=None):
    unknown = set(data) - set(JOB_FIELDS)
    if unknown:
        raise bad_request(f"unknown fields: {', '.join(sorted(unknown))}")
    out, notes = {}, []
    if not partial or "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            raise bad_request("title is required")
        out["title"] = title
    if not partial or "openings" in data:
        try:
            n = int(data.get("openings") if data.get("openings") is not None else 1)
        except (TypeError, ValueError):
            raise bad_request("openings must be a whole number of at least 1")
        if n < 1:
            raise bad_request("openings must be a whole number of at least 1")
        out["openings"] = n
    if not partial or "location_text" in data or "location" in data:
        loc, yard = resolve_location(company, data.get("location_text"), data.get("location"))
        out["location"] = loc
        if yard:
            notes.append(f"location defaulted to the company yard ({loc['label']})")
    if not partial or "pay_min" in data or "pay_max" in data:
        lo = _num(data.get("pay_min"), "pay_min") if "pay_min" in data or not partial else existing.get("pay_min")
        hi = _num(data.get("pay_max"), "pay_max") if "pay_max" in data or not partial else existing.get("pay_max")
        if lo is not None and hi is not None and hi < lo:
            raise bad_request("pay_max must be at least pay_min")
        out.update(pay_min=lo, pay_max=hi, pay_label=pay_label(lo, hi))
    if not partial or "start_date" in data or "end_date" in data:
        s = parse_iso(data.get("start_date"), "start_date") if "start_date" in data or not partial \
            else existing.get("start_date")
        e = parse_iso(data.get("end_date"), "end_date") if "end_date" in data or not partial else existing.get("end_date")
        if s and e and e < s:
            raise bad_request("end_date must be on or after start_date")
        out.update(start_date=s, end_date=e, date_label=date_label(s, e) if (s or e) else None)
    if not partial or "qualifications" in data:
        quals = data.get("qualifications") or []
        if isinstance(quals, str):
            quals = [q.strip() for q in quals.split(",") if q.strip()]
        if not isinstance(quals, list):
            raise bad_request("qualifications must be a list")
        out["qualifications"] = [str(q) for q in quals]
    if not partial or "project_id" in data:
        pid = data.get("project_id") or None
        if pid:
            from services.projects import get_project
            get_project(pid)
        out["project_id"] = pid
    if "status" in data:
        if data["status"] not in ("open", "closed"):
            raise bad_request("status must be open or closed")
        out["status"] = data["status"]
    elif not partial:
        out["status"] = "open"
    return out, notes


def list_jobs(q=None, near=None, radius_km=None, qualification=None, status="open"):
    db = require_db()
    docs = [mongo.clean(d) for d in db.jobs.find({"status": status} if status else {})]
    if q:
        docs = [d for d in docs if text_match([d["title"], d["company_name"], d["location"]["label"],
                                               *d.get("qualifications", [])], q)]
    if qualification:
        ql = qualification.lower()
        docs = [d for d in docs if any(ql in x.lower() for x in d.get("qualifications", []))]
    if near:
        pt = parse_near(near)
        radius = float(radius_km) if radius_km not in (None, "") else 80
        for d in docs:
            d["distance_km"] = round(geo.haversine_km(pt, d["location"]), 1)
        return sorted([d for d in docs if d["distance_km"] <= radius], key=lambda d: (d["distance_km"], d["id"]))
    return sorted(docs, key=lambda d: d.get("created_at") or "", reverse=True)


def get_job(jid):
    db = require_db()
    doc = mongo.clean(db.jobs.find_one({"_id": jid}))
    if doc is None:
        raise not_found("Job", jid)
    return doc


def list_saved_jobs(ident):
    db = require_db()
    if not ident.worker:
        raise ApiError("UNAUTHORIZED", "Select a worker profile first (X-Worker-Id)")
    saved = [mongo.clean(d) for d in db.saved_jobs.find({"worker_id": ident.worker_id})]
    jobs = {job["id"]: job for job in list_jobs(status="open")}
    return [jobs[s["job_id"]] for s in saved if s["job_id"] in jobs]


def save_job(ident, jid):
    db = require_db()
    if not ident.worker:
        raise ApiError("UNAUTHORIZED", "Select a worker profile first (X-Worker-Id)")
    job = get_job(jid)
    now = mongo.now()
    db.saved_jobs.update_one({"worker_id": ident.worker_id, "job_id": jid},
                             {"$set": {"updated_at": now}, "$setOnInsert": {"worker_id": ident.worker_id, "job_id": jid, "created_at": now}}, upsert=True)
    return job


def unsave_job(ident, jid):
    db = require_db()
    if not ident.worker:
        raise ApiError("UNAUTHORIZED", "Select a worker profile first (X-Worker-Id)")
    db.saved_jobs.delete_one({"worker_id": ident.worker_id, "job_id": jid})
    return {"status": "removed", "job_id": jid}


def create_job(ident, data):
    db = require_db()
    company = ident.require_company()
    fields, _ = normalize_job(company, data)
    doc = mongo.insert(db, "jobs", {"id": new_id("JOB"), "company_id": company["id"], "company_name": company["name"],
                                    **fields})
    events.emit("jobs", "insert", doc["id"], f"{company['name']} posted {doc['title']}", company["id"])
    return doc


def update_job(ident, jid, data):
    db = require_db()
    company = ident.require_company()
    job = get_job(jid)
    if job["company_id"] != company["id"]:
        raise forbidden("You can only change your own company's jobs")
    fields, _ = normalize_job(company, data, partial=True, existing=job)
    new = mongo.update(db, "jobs", jid, fields)
    events.emit("jobs", "update", jid, f"{company['name']} updated {new['title']}", company["id"])
    return new


# ---------- applications ----------
def apply(ident, jid, data):
    db = require_db()
    if not ident.worker:
        raise ApiError("UNAUTHORIZED", "Select a worker profile first (X-Worker-Id)")
    job = get_job(jid)
    if job["status"] != "open":
        raise ApiError("CONFLICT", "This job is closed")
    if db.applications.find_one({"job_id": jid, "worker_id": ident.worker_id, "status": {"$ne": "rejected"}}):
        raise ApiError("CONFLICT", "You already applied to this job")
    w = ident.worker
    quals = data.get("qualifications", w.get("certifications") or [])
    if isinstance(quals, str):
        quals = [q.strip() for q in quals.split(",") if q.strip()]
    applicant = {"name": (data.get("name") or w["name"]).strip(), "qualifications": quals,
                 "availability": data.get("availability") or w.get("availability")}
    doc = mongo.insert(db, "applications", {"id": new_id("APP"), "job_id": jid, "job_title": job["title"],
                                            "company_id": job["company_id"], "worker_id": w["id"],
                                            "applicant": applicant, "status": "submitted"})
    events.emit("applications", "insert", doc["id"], f"New application for {job['title']}", None, [job["company_id"]])
    return doc


def list_applications(ident):
    db = require_db()
    if ident.company:
        q = {"company_id": ident.company_id}
    elif ident.worker:
        q = {"worker_id": ident.worker_id}
    else:
        raise unauthorized()
    return sorted([mongo.clean(d) for d in db.applications.find(q)], key=lambda d: d.get("created_at") or "",
                  reverse=True)


def update_application(ident, app_id, status):
    db = require_db()
    company = ident.require_company()
    doc = mongo.clean(db.applications.find_one({"_id": app_id}))
    if doc is None:
        raise not_found("Application", app_id)
    if doc["company_id"] != company["id"]:
        raise forbidden("Only the job owner can update applications")
    if status not in APP_STATUSES:
        raise bad_request("status must be submitted, reviewed, accepted or rejected")
    new = mongo.update(db, "applications", app_id, {"status": status})
    events.emit("applications", "update", app_id, f"Application for {doc['job_title']} {status}", company["id"],
                [company["id"]])
    return new
