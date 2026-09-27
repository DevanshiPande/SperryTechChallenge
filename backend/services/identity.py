"""Who is calling: X-Company-Id / X-Worker-Id headers. No real login (hackathon demo)."""
from dataclasses import dataclass

from db import mongo
from services.errors import unauthorized
from services.state import STATE


@dataclass
class Identity:
    company: dict = None
    worker: dict = None

    @property
    def company_id(self):
        return self.company["id"] if self.company else None

    @property
    def worker_id(self):
        return self.worker["id"] if self.worker else None

    @property
    def kind(self):
        return "company" if self.company else "worker" if self.worker else "guest"

    def require_company(self):
        if not self.company:
            raise unauthorized()
        return self.company


def _demo(coll):
    from db import seed
    return {"companies": seed.DEMO_COMPANIES, "workers": seed.DEMO_WORKERS}[coll]


def find(coll, id_):
    if not id_:
        return None
    if STATE.db is not None:
        return mongo.clean(STATE.db[coll].find_one({"_id": id_}))
    return next((dict(c) for c in _demo(coll) if c["id"] == id_), None)


def companies():
    if STATE.db is not None:
        return [mongo.clean(c) for c in STATE.db.companies.find().sort("_id", 1)]
    return [dict(c) for c in _demo("companies")]


def resolve(company_id=None, worker_id=None):
    return Identity(company=find("companies", (company_id or "").strip()), worker=find("workers", (worker_id or "").strip()))


WORKER_FIELDS = ("name", "trade", "certifications", "experience", "availability", "service_area_text")


def update_worker(ident, data):
    from db import mongo as m
    from services import events
    from services.errors import ApiError, bad_request
    from services.geocode import geocode
    from services.state import require_db
    db = require_db()
    if not ident.worker:
        raise ApiError("UNAUTHORIZED", "Select a worker profile first (X-Worker-Id)")
    unknown = set(data) - set(WORKER_FIELDS)
    if unknown:
        raise bad_request(f"unknown fields: {', '.join(sorted(unknown))}")
    upd = {}
    for k in ("name", "trade", "experience", "availability"):
        if k in data:
            v = str(data[k] or "").strip()
            if k == "name" and not v:
                raise bad_request("name is required")
            upd[k] = v or None
    if "certifications" in data:
        c = data["certifications"] or []
        upd["certifications"] = [x.strip() for x in (c.split(",") if isinstance(c, str) else c) if str(x).strip()]
    if data.get("service_area_text"):
        g = geocode(data["service_area_text"])
        if not g:
            raise bad_request(f'Could not locate "{data["service_area_text"]}". Try a town name.')
        radius = (ident.worker.get("service_area") or {}).get("radius_mi", 25)
        upd["service_area"] = {"label": g["label"], "lat": g["lat"], "lon": g["lon"], "radius_mi": radius}
    new = m.update(db, "workers", ident.worker_id, upd) if upd else ident.worker
    events.emit("workers", "update", ident.worker_id, "Worker profile updated", None, ident.worker_id)
    return new
