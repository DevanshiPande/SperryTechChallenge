"""Projects and overlaps: public reads (memory) + user projects (Mongo). Shared by REST and agent tools."""
import copy
from datetime import date

from db import mongo
from engine import budget, closures, geo, overlaps as eng
from services import events, ml
from services.common import new_id, parse_iso, text_match
from services.errors import bad_request, forbidden, not_found
from services.geocode import geocode
from services.state import STATE, require_db

CONFIDENCES = ("high", "medium", "low", "not_found")
SORTS = ("score", "distance", "timeline")
POTENTIALS = ("high", "moderate", "lower")
TIERS = ("crossing", "shared_land", "shared_site", "shared_crews")
KINDS = ("cross_utility", "user_project")


# ---------- reads ----------
def user_projects():
    if STATE.db is None:
        return []
    return [mongo.clean(d) for d in STATE.db.projects.find({"source.type": "user"})]


def user_overlaps():
    if STATE.db is None:
        return []
    return [mongo.clean(d) for d in STATE.db.overlaps.find({"kind": "user_project"})]


def _with_overlap_ids(projects, uovs):
    """Copies with overlap ids. Public projects keep their Sperry (cross-utility) overlap_ids and get the user-project
    overlaps in the additive `user_overlap_ids`; user projects list all of theirs in overlap_ids."""
    by_proj = {}
    for o in uovs:
        by_proj.setdefault(o["project_a"], []).append(o["id"])
        by_proj.setdefault(o["project_b"], []).append(o["id"])
    out = []
    for p in projects:
        q = copy.copy(p)
        if eng.is_user(p):
            q["overlap_ids"] = by_proj.get(p["id"], [])
        else:
            q["user_overlap_ids"] = by_proj.get(p["id"], [])
        out.append(q)
    return out


def all_projects(with_ids=True):
    ups = user_projects()
    ps = STATE.projects + ups
    return _with_overlap_ids(ps, user_overlaps()) if with_ids else ps


def get_project(pid):
    p = STATE.projects_by_id.get(pid)
    if p is None and STATE.db is not None:
        p = mongo.clean(STATE.db.projects.find_one({"_id": pid, "source.type": "user"}))
    if p is None:
        raise not_found("Project", pid)
    return _with_overlap_ids([p], user_overlaps())[0]


def all_overlaps():
    return STATE.overlaps + user_overlaps()


def get_overlap(oid):
    o = STATE.overlaps_by_id.get(oid)
    if o is None and STATE.db is not None:
        o = mongo.clean(STATE.db.overlaps.find_one({"_id": oid}))
    if o is None:
        raise not_found("Overlap", oid)
    o = copy.copy(o)
    cached = brief_cache_get(oid, "summary")
    if cached and not o.get("brief"):
        o["brief"] = cached["brief"]
    return o


def _year(s):
    return int(str(s)[:4]) if s else None


def _num(v, name):
    try:
        return float(v)
    except (TypeError, ValueError):
        raise bad_request(f"{name} must be a number")


def project_hay(p):
    return [p.get("name"), p.get("short_name"), p.get("utility_name"), p.get("utility"), *(p.get("counties") or []),
            *[e.get("name") for e in p.get("endpoints") or []]]


def list_projects(utility=None, confidence=None, has_overlap=None, year_from=None, year_to=None, q=None, source=None):
    if utility and utility not in ("DESC", "GPC", "USER"):
        raise bad_request("utility must be DESC or GPC")
    if confidence and confidence not in CONFIDENCES:
        raise bad_request("invalid confidence")
    if source and source not in ("public_filing", "user"):
        raise bad_request("source must be public_filing or user")
    out = all_projects()
    if source:
        out = [p for p in out if eng.origin(p) == source]
    if utility:
        out = [p for p in out if p.get("utility") == utility]
    if confidence:
        out = [p for p in out if p.get("location_confidence") == confidence]
    if has_overlap in ("true", True):
        out = [p for p in out if p.get("overlap_ids")]
    elif has_overlap in ("false", False):
        out = [p for p in out if not p.get("overlap_ids")]
    if year_from not in (None, ""):
        yf = _num(year_from, "year_from")
        out = [p for p in out if _year(p.get("in_service_date")) and _year(p["in_service_date"]) >= yf]
    if year_to not in (None, ""):
        yt = _num(year_to, "year_to")
        out = [p for p in out if _year(p.get("in_service_date")) and _year(p["in_service_date"]) <= yt]
    if q:
        out = [p for p in out if text_match(project_hay(p), q)]
    return out


def list_overlaps(max_mi=None, tier=None, potential=None, min_window_overlap_months=None, year_from=None, year_to=None,
                  q=None, sort=None, kind=None, project_id=None):
    max_mi = 25 if max_mi in (None, "") else max_mi
    min_win = 0 if min_window_overlap_months in (None, "") else min_window_overlap_months
    try:
        max_mi, min_win = float(max_mi), float(min_win)
    except (TypeError, ValueError):
        raise bad_request("max_mi and min_window_overlap_months must be numbers")
    sort = sort or "score"
    if sort not in SORTS:
        raise bad_request("sort must be score, distance or timeline")
    if potential and potential not in POTENTIALS:
        raise bad_request("potential must be high, moderate or lower")
    if tier and tier not in TIERS:
        raise bad_request("tier must be crossing, shared_land, shared_site or shared_crews")
    if kind and kind not in KINDS:
        raise bad_request("kind must be cross_utility or user_project")
    yf = _num(year_from, "year_from") if year_from not in (None, "") else float("-inf")
    yt = _num(year_to, "year_to") if year_to not in (None, "") else float("inf")
    projects = {p["id"]: p for p in all_projects(with_ids=False)}

    def in_years(o):
        ys = [_year(projects[x].get("in_service_date")) for x in (o["project_a"], o["project_b"]) if x in projects]
        return any(y is not None and yf <= y <= yt for y in ys)

    def matches(o):
        return any(text_match(project_hay(projects[x]), q) for x in (o["project_a"], o["project_b"]) if x in projects)

    out = [o for o in all_overlaps()
           if eng.edge_mi(o) <= max_mi and o["window_overlap_months"] >= min_win
           and (not tier or o["tier"] == tier) and (not potential or o["potential"] == potential)
           and (not kind or o.get("kind", "cross_utility") == kind)
           and (not project_id or project_id in (o["project_a"], o["project_b"]))
           and in_years(o) and (not q or matches(o))]
    key = {"score": lambda o: (-o["score"], eng.edge_mi(o), o["id"]),
           "distance": lambda o: (eng.edge_mi(o), -o["score"], o["id"]),
           "timeline": lambda o: (-o["window_overlap_months"], -o["score"], o["id"])}[sort]
    return sorted(out, key=key)


# ---------- traffic ----------
def traffic_callable():
    return STATE.traffic.pair_savings if STATE.traffic else None


def project_traffic(p):
    """Traffic block for one project: its crossings (with closure plans), access roads for substation work, and
    closure conflicts with other owners' crossings on the same road."""
    t = STATE.traffic
    if t is None:
        return None
    xs = t.crossings(p)
    conflicts = [c for c in t.all_conflicts(all_projects(with_ids=False)) if p["id"] in (c["project_a"], c["project_b"])]
    return {"crossings": xs, "access_roads": t.access_roads(p) if not xs else [], "conflicts": conflicts,
            "note": "Lines are straight between substations, so crossing points are approximate."}


# ---------- brief cache (shared with ai.brief) ----------
def brief_cache_get(oid, mode):
    if STATE.db is not None:
        d = STATE.db.briefs.find_one({"_id": f"{oid}:{mode}"})
        return {"brief": d["brief"], "source": d["source"]} if d else None
    return STATE.briefs.get((oid, mode))


def brief_cache_set(oid, mode, brief, source):
    if STATE.db is not None:
        STATE.db.briefs.update_one({"_id": f"{oid}:{mode}"},
                                   {"$set": {"brief": brief, "source": source, "updated_at": mongo.now()}}, upsert=True)
    else:
        STATE.briefs[(oid, mode)] = {"brief": brief, "source": source}


# ---------- user projects ----------
USER_FIELDS = ("line_miles", "contract_text_hash", "budget_usd", "name", "description", "location_text", "endpoints", "start_date", "end_date", "voltage_kv", "work_type",
               "roads_affected", "lane_closures", "work_hours", "planning_authority")


def resolve_location(location_text=None, endpoints=None):
    """-> (endpoints, geocoded). Explicit endpoints (map pins) win over text."""
    if endpoints:
        if not isinstance(endpoints, list) or not 1 <= len(endpoints) <= 2:
            raise bad_request("endpoints must have 1 or 2 items")
        eps = []
        for i, e in enumerate(endpoints):
            try:
                lat, lon = float(e["lat"]), float(e["lon"])
            except (KeyError, TypeError, ValueError):
                raise bad_request("each endpoint needs numeric lat and lon")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise bad_request("endpoint lat/lon out of range")
            eps.append({"name": e.get("name") or f"Point {i + 1}", "lat": lat, "lon": lon, "confidence": "high",
                        "source": "user", "county": None})
        return eps, None
    if location_text:
        g = geocode(location_text)
        if not g:
            raise bad_request(f'Could not locate "{location_text}". Try a town name or drop a pin on the map.')
        return [{"name": g["label"], "lat": g["lat"], "lon": g["lon"], "confidence": "medium",
                 "source": g["source"], "county": None}], g
    raise bad_request("provide location_text or endpoints (1 or 2 with lat and lon)")


def _state_of(label):
    if label and "," in label:
        st = label.rsplit(",", 1)[1].strip()
        return st if len(st) == 2 else None
    return None


def build_user_project(pid, company, data, today=None):
    name = (data.get("name") or "").strip()
    if not name:
        raise bad_request("name is required")
    start = parse_iso(data.get("start_date"), "start_date")
    end = parse_iso(data.get("end_date"), "end_date")
    if not end and not start:
        raise bad_request("start_date or end_date is required (the missing one is predicted)")
    if start and end and end <= start:
        raise bad_request("end_date must be after start_date")
    eps, geocoded = resolve_location(data.get("location_text"), data.get("endpoints"))
    kv = data.get("voltage_kv")
    if kv not in (None, ""):
        try:
            kv = int(kv)
        except (TypeError, ValueError):
            raise bad_request("voltage_kv must be a number")
    else:
        kv = None
    ptype = "line" if len(eps) == 2 else "substation"
    window, start_flags = {"start": start, "end": end, "source": data.get("window_source") or "user"}, []
    if not start:
        # Missing start date: predict it from the duration model (ML_README U6), never before today.
        pw = ml.predicted_window({"id": pid, "name": name, "description": data.get("description"), "voltage_kv": kv,
                                  "line_miles": data.get("line_miles"), "in_service_date": end},
                                 reference_year=ml.this_year(), not_before=(today or date.today()).isoformat())
        if not pw:
            raise bad_request("start_date is required (the start-date model is not available)")
        if pw["start"] >= end:
            raise bad_request("end_date is too soon for a predicted start (it would start after it ends); give a start_date")
        window = {"start": pw["start"], "end": end, "source": "predicted", "prediction": pw["prediction"]}
        start_flags = pw["flags"]
    elif not end:
        # Missing end date: start + predicted construction duration.
        pe = ml.predicted_end({"id": pid, "name": name, "description": data.get("description"), "voltage_kv": kv,
                               "line_miles": data.get("line_miles")}, start, reference_year=ml.this_year())
        if not pe:
            raise bad_request("end_date is required (the duration model is not available)")
        end = pe["end"]
        window = {"start": start, "end": end, "source": "predicted", "prediction": pe["prediction"]}
    p = {
        "id": pid,
        "utility": "USER",
        "utility_name": company["name"],
        "state": _state_of(geocoded["label"]) if geocoded else None,
        "name": name,
        "voltage_kv": kv,
        "project_type": ptype,
        "status": "Planned",
        "in_service_date": end,
        "construction_window": window,
        "endpoints": eps,
        "center": geo.center_of(eps),
        "geometry": geo.geojson(eps),
        "location_confidence": "medium" if geocoded else "high",
        "description": data.get("description") or None,
        "cost": None,
        "source": {"document": None, "page": None, "type": "user"},
        "quality_flags": [],
        "overlap_ids": [],
        "short_name": name if len(name) <= 40 else name[:39] + "…",
        "work_type_label": data.get("work_type") or "User project",
        "counties": [],
        "county_source": None,
        "company_id": company["id"],
        "work_type": data.get("work_type") or None,
        "roads_affected": closures.normalize_roads(data.get("roads_affected")),
        "lane_closures": data.get("lane_closures") or None,
        "work_hours": data.get("work_hours") or None,
        "planning_authority": data.get("planning_authority") or None,
        "location_text": data.get("location_text") or None,
        "geocoded": geocoded,
        "contract_text_hash": data.get("contract_text_hash") or None,
        "line_miles": data.get("line_miles") or None,
    }
    for code in start_flags:
        p["quality_flags"].append({"code": code, "message": "The predicted start fell in the past, so it was set to today."})
    if data.get("budget_usd"):
        try:
            b = int(float(data["budget_usd"]))
        except (TypeError, ValueError):
            raise bad_request("budget_usd must be a number")
        if b <= 0:
            raise bad_request("budget_usd must be positive")
        p.update(budget_usd=b, budget_source="contract" if data.get("contract_text_hash") else "user")
    # Missing budget: predict it only for transmission work (a voltage is known); never for e.g. road work.
    budget.attach(p, predictor=ml.predicted_budget, predict_missing=kv is not None)
    if end < (today or date.today()).isoformat():
        p["quality_flags"].append({"code": "POSSIBLY_COMPLETE",
                                   "message": "In-service date is in the past; project may already be complete."})
    return p


def _rerank_user_overlaps(db):
    ranked = eng.rank(user_overlaps())
    for o in ranked:
        db.overlaps.update_one({"_id": o["id"]}, {"$set": {"rank": o["rank"]}})
    return {o["id"]: o["rank"] for o in ranked}


def _recompute_overlaps(db, project, company_id):
    """Delete and recompute every overlap involving this user project."""
    old = [d["_id"] for d in db.overlaps.find({"$or": [{"project_a": project["id"]}, {"project_b": project["id"]}]},
                                              {"_id": 1})]
    db.overlaps.delete_many({"_id": {"$in": old}})
    others = [p for p in all_projects(with_ids=False) if p["id"] != project["id"]]
    new = eng.user_project_overlaps(project, others, traffic_callable())
    for o in new:
        mongo.insert(db, "overlaps", o)
    ranks = _rerank_user_overlaps(db)
    for o in new:
        o["rank"] = ranks.get(o["id"])
    removed = sorted(set(old) - {o["id"] for o in new})
    for oid in removed:
        events.emit("overlaps", "delete", oid, f"Overlap {oid} removed", company_id)
    for o in new:
        events.emit("overlaps", "update" if o["id"] in old else "insert", o["id"], f"Overlap {o['label']}", company_id)
    return new


def _closure_conflicts(project):
    others = [p for p in user_projects() if p["id"] != project["id"]]
    return closures.conflicts(project, others)


def _same_project(db, company_id, data):
    """An existing project of this company with the same name, dates and location (a repeated save), or None."""
    name = (data.get("name") or "").strip().lower()
    if not name:
        return None
    for d in db.projects.find({"company_id": company_id, "source.type": "user"}):
        w = d.get("construction_window") or {}
        same_dates = (not data.get("start_date") or data.get("start_date") == w.get("start")) and \
                     (not data.get("end_date") or data.get("end_date") == w.get("end"))
        same_place = (data.get("location_text") or None) == (d.get("location_text") or None) and \
                     (not data.get("endpoints") or [(e.get("lat"), e.get("lon")) for e in data["endpoints"]] ==
                      [(e.get("lat"), e.get("lon")) for e in d.get("endpoints") or []])
        if (d.get("name") or "").strip().lower() == name and same_dates and same_place:
            return d
    return None


def create_user_project(ident, data):
    db = require_db()
    company = ident.require_company()
    existing = _same_project(db, company["id"], data or {})
    if existing:
        # Saving the same project twice returns the first copy instead of creating a duplicate.
        return {"project": get_project(existing["id"]), "overlaps": [o for o in user_overlaps() if existing["id"] in
                (o["project_a"], o["project_b"])], "closure_conflicts": _closure_conflicts(existing), "already_saved": True}
    p = build_user_project(new_id("USR"), company, data)
    mongo.insert(db, "projects", p)
    events.emit("projects", "insert", p["id"], f"{company['name']} added project {p['name']}", company["id"])
    ovs = _recompute_overlaps(db, p, company["id"])
    from services import congestion
    congestion.compute_in_background(p["id"])  # new project (or uploaded contract): its traffic congestion, ready when opened
    return {"project": get_project(p["id"]), "overlaps": ovs, "closure_conflicts": _closure_conflicts(p)}


def _own_user_project(ident, pid):
    db = require_db()
    company = ident.require_company()
    if pid in STATE.projects_by_id:
        raise forbidden("Public filing records are read-only")
    doc = mongo.clean(db.projects.find_one({"_id": pid}))
    if doc is None:
        raise not_found("Project", pid)
    if doc.get("company_id") != company["id"]:
        raise forbidden("You can only change your own company's projects")
    return db, company, doc


def update_user_project(ident, pid, fields):
    db, company, doc = _own_user_project(ident, pid)
    unknown = set(fields) - set(USER_FIELDS)
    if unknown:
        raise bad_request(f"unknown fields: {', '.join(sorted(unknown))}")
    merged = {"name": doc["name"], "description": doc.get("description"),
              "start_date": None if ml.predicted_field(doc["construction_window"]) == "start" else doc["construction_window"]["start"],
              "end_date": None if ml.predicted_field(doc["construction_window"]) == "end" else doc["construction_window"]["end"], "line_miles": doc.get("line_miles"),
              "voltage_kv": doc.get("voltage_kv"), "work_type": doc.get("work_type"),
              "roads_affected": doc.get("roads_affected"), "lane_closures": doc.get("lane_closures"),
              "work_hours": doc.get("work_hours"), "planning_authority": doc.get("planning_authority"),
              "contract_text_hash": doc.get("contract_text_hash"),
              "budget_usd": doc.get("budget_usd") if doc.get("budget_source") in ("contract", "user") else None}
    if "location_text" in fields or "endpoints" in fields:
        merged.update({k: fields.get(k) for k in ("location_text", "endpoints")})
    else:
        merged["endpoints"] = [{"name": e["name"], "lat": e["lat"], "lon": e["lon"]} for e in doc["endpoints"]]
    merged.update({k: v for k, v in fields.items() if k not in ("location_text", "endpoints")})
    p = build_user_project(pid, company, merged)
    if "location_text" not in fields and "endpoints" not in fields:
        p.update(endpoints=doc["endpoints"], geocoded=doc.get("geocoded"), location_confidence=doc["location_confidence"],
                 state=doc.get("state"), location_text=doc.get("location_text"))
    p.pop("id")
    mongo.update(db, "projects", pid, p)
    events.emit("projects", "update", pid, f"{company['name']} updated project {p['name']}", company["id"])
    fresh = mongo.clean(db.projects.find_one({"_id": pid}))
    ovs = _recompute_overlaps(db, fresh, company["id"])
    return {"project": get_project(pid), "overlaps": ovs, "closure_conflicts": _closure_conflicts(fresh)}


def delete_user_project(ident, pid):
    db, company, doc = _own_user_project(ident, pid)
    ov_ids = [d["_id"] for d in db.overlaps.find({"$or": [{"project_a": pid}, {"project_b": pid}]}, {"_id": 1})]
    db.overlaps.delete_many({"_id": {"$in": ov_ids}})
    db.projects.delete_one({"_id": pid})
    _rerank_user_overlaps(db)
    events.emit("projects", "delete", pid, f"{company['name']} removed project {doc['name']}", company["id"])
    for oid in ov_ids:
        events.emit("overlaps", "delete", oid, f"Overlap {oid} removed", company["id"])
    return {"deleted": pid, "overlaps_deleted": ov_ids}
