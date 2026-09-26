"""Shared equipment and crews (resources) and reservations."""
from datetime import date, timedelta

from db import mongo
from engine import geo
from services import events
from services.common import date_label, new_id, parse_iso, parse_near, text_match
from services.errors import ApiError, bad_request, forbidden, not_found
from services.geocode import geocode
from services.state import require_db

NEARBY_KM = 40
TYPES = ("equipment", "crew")
EDITABLE = ("name", "type", "quantity", "location_text", "location", "available_from", "available_to", "daily_rate",
            "notes")


def nearby_projects(location, km=NEARBY_KM):
    from services.projects import all_projects
    pt = [{"lat": location["lat"], "lon": location["lon"]}]
    out = []
    for p in all_projects(with_ids=False):
        if not p.get("center"):
            continue
        d, _ = geo.closest(pt, p["endpoints"])
        if d is not None and d <= km:
            out.append((d, p["id"]))
    return [pid for _, pid in sorted(out)]


def rate_label(rate):
    if rate in (None, ""):
        return "Rate on request"
    return f"${rate:,.0f}/day per unit" if float(rate).is_integer() else f"${rate:,.2f}/day per unit"


def resolve_location(company, location_text=None, location=None):
    """-> (location {label, lat, lon}, defaulted_to_yard: bool)"""
    if location:
        try:
            lat, lon = float(location["lat"]), float(location["lon"])
        except (KeyError, TypeError, ValueError):
            raise bad_request("location needs numeric lat and lon")
        return {"label": location.get("label") or f"{lat:.4f}, {lon:.4f}", "lat": lat, "lon": lon}, False
    if location_text:
        g = geocode(location_text)
        if not g:
            raise bad_request(f'Could not locate "{location_text}". Try a town name.')
        return {"label": g["label"], "lat": g["lat"], "lon": g["lon"]}, False
    yard = company.get("yard")
    if not yard:
        raise bad_request("location is required (the company has no yard on file)")
    return dict(yard), True


def normalize_fields(company, data, today=None, partial=False, existing=None):
    """Validate + normalize resource input. Returns (fields, notes) where notes lists defaults applied."""
    notes = []
    out = {}
    if not partial or "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            raise bad_request("name is required")
        out["name"] = name
    if not partial or "type" in data:
        t = (data.get("type") or "").strip().lower()
        if t not in TYPES:
            raise bad_request("type must be equipment or crew")
        out["type"] = t
    if not partial or "quantity" in data:
        try:
            q = int(data.get("quantity"))
        except (TypeError, ValueError):
            raise bad_request("quantity must be a whole number of at least 1")
        if q < 1 or q != float(data.get("quantity")):
            raise bad_request("quantity must be a whole number of at least 1")
        out["quantity"] = q
    if not partial or "location_text" in data or "location" in data:
        loc, yard = resolve_location(company, data.get("location_text"), data.get("location"))
        out["location"] = loc
        if yard:
            notes.append(f"location defaulted to the company yard ({loc['label']})")
    if not partial or "available_from" in data or "available_to" in data:
        start = parse_iso(data.get("available_from"), "available_from") if "available_from" in data or not partial \
            else existing["available_from"]
        end = parse_iso(data.get("available_to"), "available_to") if "available_to" in data or not partial \
            else existing["available_to"]
        if not start and not end and not partial:
            t0 = today or date.today()
            start, end = t0.isoformat(), (t0 + timedelta(days=30)).isoformat()
            notes.append("dates defaulted to today for 30 days")
        elif not start or not end:
            raise bad_request("give both available_from and available_to")
        if end < start:
            raise bad_request("available_to must be on or after available_from")
        out.update(available_from=start, available_to=end, date_label=date_label(start, end))
    if not partial or "daily_rate" in data:
        rate = data.get("daily_rate")
        if rate in (None, ""):
            rate = None
        else:
            try:
                rate = float(rate)
            except (TypeError, ValueError):
                raise bad_request("daily_rate must be a number")
            if rate < 0:
                raise bad_request("daily_rate must be 0 or more")
            rate = int(rate) if rate.is_integer() else rate
        out.update(daily_rate=rate, rate_label=rate_label(rate))
    if not partial or "notes" in data:
        out["notes"] = data.get("notes") or None
    unknown = set(data) - set(EDITABLE)
    if unknown:
        raise bad_request(f"unknown fields: {', '.join(sorted(unknown))}")
    return out, notes


def get_resource(rid):
    db = require_db()
    doc = mongo.clean(db.resources.find_one({"_id": rid}))
    if doc is None:
        raise not_found("Resource", rid)
    return doc


def list_resources(type=None, near=None, radius_km=None, q=None, company_id=None, available_on=None):
    db = require_db()
    query = {}
    if type:
        if type not in TYPES:
            raise bad_request("type must be equipment or crew")
        query["type"] = type
    if company_id:
        query["company_id"] = company_id
    docs = [mongo.clean(d) for d in db.resources.find(query)]
    if available_on:
        day = parse_iso(available_on, "available_on")
        docs = [d for d in docs if d["available_from"] <= day <= d["available_to"]]
    if q:
        docs = [d for d in docs if text_match([d["name"], d.get("notes"), d["company_name"], d["location"]["label"],
                                               d["type"]], q)]
    if near:
        pt = parse_near(near)
        radius = float(radius_km) if radius_km not in (None, "") else NEARBY_KM
        for d in docs:
            d["distance_km"] = round(geo.haversine_km(pt, d["location"]), 1)
        docs = sorted([d for d in docs if d["distance_km"] <= radius], key=lambda d: (d["distance_km"], d["id"]))
    else:
        docs.sort(key=lambda d: (d.get("created_at") or "", d["id"]), reverse=True)
    return docs


def create_resource(ident, data):
    db = require_db()
    company = ident.require_company()
    fields, _ = normalize_fields(company, data)
    doc = {"id": new_id("RES"), "company_id": company["id"], "company_name": company["name"], **fields,
           "nearby_project_ids": nearby_projects(fields["location"])}
    doc = mongo.insert(db, "resources", doc)
    events.emit("resources", "insert", doc["id"], f"{company['name']} listed {doc['quantity']} x {doc['name']}",
                company["id"])
    return doc


def _own(ident, rid):
    company = ident.require_company()
    doc = get_resource(rid)
    if doc["company_id"] != company["id"]:
        raise forbidden("You can only change your own company's resources")
    return company, doc


def check_update(ident, rid, fields):
    """Validate an update without writing (used for pending-action previews)."""
    company, doc = _own(ident, rid)
    upd, notes = normalize_fields(company, fields, partial=True, existing=doc)
    return doc, upd, notes


def update_resource(ident, rid, fields):
    db = require_db()
    doc, upd, _ = check_update(ident, rid, fields)
    if "location" in upd:
        upd["nearby_project_ids"] = nearby_projects(upd["location"])
    new = mongo.update(db, "resources", rid, upd)
    events.emit("resources", "update", rid, f"{doc['company_name']} updated {new['name']}", doc["company_id"])
    return new


def delete_resource(ident, rid):
    db = require_db()
    company, doc = _own(ident, rid)
    db.resources.delete_one({"_id": rid})
    events.emit("resources", "delete", rid, f"{company['name']} removed {doc['name']}", company["id"])
    return {"deleted": rid}


# ---------- reservations ----------
STATUSES = ("pending", "accepted", "declined", "cancelled")


def _overlapping_accepted(db, resource_id, start, end, exclude_id=None):
    total = 0
    for r in db.reservations.find({"resource_id": resource_id, "status": "accepted"}):
        if r["_id"] != exclude_id and r["from"] <= end and start <= r["to"]:
            total += r["quantity"]
    return total


def check_reservation(ident, rid, data):
    """Validate a reservation request; returns (resource, normalized fields). Raises on rule violations."""
    db = require_db()
    company = ident.require_company()
    res = get_resource(rid)
    if res["company_id"] == company["id"]:
        raise bad_request("You cannot reserve your own resource")
    try:
        qty = int(data.get("quantity"))
    except (TypeError, ValueError):
        raise bad_request("quantity must be a whole number of at least 1")
    if qty < 1:
        raise bad_request("quantity must be a whole number of at least 1")
    start, end = parse_iso(data.get("from"), "from"), parse_iso(data.get("to"), "to")
    if not start or not end:
        raise bad_request("from and to are required")
    if end < start:
        raise bad_request("to must be on or after from")
    if start < res["available_from"] or end > res["available_to"]:
        raise bad_request(f"Dates must fall inside the availability window ({res['available_from']} to "
                          f"{res['available_to']})")
    booked = _overlapping_accepted(db, rid, start, end)
    if qty + booked > res["quantity"]:
        raise ApiError("INSUFFICIENT_QUANTITY", f"Only {res['quantity'] - booked} of {res['quantity']} available for "
                                                f"those dates")
    project_id = data.get("project_id") or None
    if project_id:
        from services.projects import get_project
        get_project(project_id)
    return res, {"quantity": qty, "from": start, "to": end, "project_id": project_id, "note": data.get("note") or None}


def create_reservation(ident, rid, data):
    db = require_db()
    res, f = check_reservation(ident, rid, data)
    company = ident.company
    doc = {"id": new_id("RSV"), "resource_id": rid, "resource_name": res["name"], "owner_company_id": res["company_id"],
           "requester_company_id": company["id"], "requester_company_name": company["name"], **f, "status": "pending"}
    doc = mongo.insert(db, "reservations", doc)
    events.emit("reservations", "insert", doc["id"], f"{company['name']} requested {f['quantity']} x {res['name']}",
                company["id"], [res["company_id"], company["id"]])
    return doc


def list_reservations(ident, role=None):
    db = require_db()
    company = ident.require_company()
    if role not in (None, "", "incoming", "outgoing"):
        raise bad_request("role must be incoming or outgoing")
    if role == "incoming":
        q = {"owner_company_id": company["id"]}
    elif role == "outgoing":
        q = {"requester_company_id": company["id"]}
    else:
        q = {"$or": [{"owner_company_id": company["id"]}, {"requester_company_id": company["id"]}]}
    docs = [mongo.clean(d) for d in db.reservations.find(q)]
    return sorted(docs, key=lambda d: d.get("created_at") or "", reverse=True)


def get_reservation(rsv_id):
    db = require_db()
    doc = mongo.clean(db.reservations.find_one({"_id": rsv_id}))
    if doc is None:
        raise not_found("Reservation", rsv_id)
    return doc


def check_status_change(ident, rsv_id, status):
    company = ident.require_company()
    r = get_reservation(rsv_id)
    if status not in ("accepted", "declined", "cancelled"):
        raise bad_request("status must be accepted, declined or cancelled")
    if company["id"] not in (r["owner_company_id"], r["requester_company_id"]):
        raise forbidden("This reservation belongs to other companies")
    if status in ("accepted", "declined") and company["id"] != r["owner_company_id"]:
        raise forbidden("Only the resource owner can accept or decline")
    if status == "cancelled" and company["id"] != r["requester_company_id"]:
        raise forbidden("Only the requester can cancel")
    if r["status"] != "pending" and not (status == "cancelled" and r["status"] == "accepted"):
        raise ApiError("CONFLICT", f"Reservation is already {r['status']}")
    if status == "accepted":
        db = require_db()
        res = get_resource(r["resource_id"])
        booked = _overlapping_accepted(db, r["resource_id"], r["from"], r["to"], exclude_id=rsv_id)
        if r["quantity"] + booked > res["quantity"]:
            raise ApiError("INSUFFICIENT_QUANTITY", f"Only {res['quantity'] - booked} of {res['quantity']} available "
                                                    f"for those dates")
    return r


def update_reservation(ident, rsv_id, status):
    db = require_db()
    r = check_status_change(ident, rsv_id, status)
    new = mongo.update(db, "reservations", rsv_id, {"status": status})
    events.emit("reservations", "update", rsv_id, f"Reservation for {r['resource_name']} {status}",
                ident.company_id, [r["owner_company_id"], r["requester_company_id"]])
    return new
