"""Meta, quality, what-if and the Excel export (Sperry core; never depends on Gemini or Mongo)."""
import io
from datetime import date

from openpyxl import Workbook

from engine import geo, quality, whatif as wi
from engine.overlaps import METHOD_NOTES, POTENTIAL_LEVELS, THRESHOLD_MI, is_user
from services import projects as svc
from services.errors import bad_request
from services.geocode import geocode
from services.state import STATE

UTILITIES = [
    {"code": "DESC", "name": "Dominion Energy South Carolina", "color": "#1F6FB2"},
    {"code": "GPC", "name": "Georgia Power", "color": "#D9822B"},
]


def meta():
    years = [int(p["in_service_date"][:4]) for p in STATE.projects if p.get("in_service_date")]
    return {
        "utilities": UTILITIES,
        "threshold_mi": THRESHOLD_MI,
        "generated_at": STATE.generated_at,
        "tiers": [{"code": code, "label": label, "max_km": max_km} for code, max_km, _, label, _ in geo.TIERS],
        "potential_levels": POTENTIAL_LEVELS,
        "in_service_years": [min(years), max(years)] if years else None,
        "method_notes": METHOD_NOTES,
        "traffic_data": STATE.traffic is not None,
    }


def quality_list():
    return quality.flat_list(svc.all_projects(with_ids=False))


def _valid_date(s):
    try:
        return isinstance(s, str) and len(s) == 10 and bool(date.fromisoformat(s))
    except ValueError:
        return False


def run_whatif(body, today=None):
    """Body as in API_README. Validation messages follow the mock server."""
    if not isinstance(body, dict):
        raise bad_request("Body must be a JSON object")
    name = body.get("name")
    utility = body.get("utility")
    w = body.get("construction_window")
    if not name:
        raise bad_request("name is required")
    if utility is not None and utility not in ("DESC", "GPC"):
        raise bad_request("utility must be DESC, GPC or omitted")
    endpoints = body.get("endpoints")
    geocoded = None
    if not endpoints and body.get("location_text"):
        geocoded = geocode(body["location_text"])
        if not geocoded:
            raise bad_request(f'Could not locate "{body["location_text"]}". Try a town name or drop a pin on the map.')
        endpoints = [{"name": geocoded["label"], "lat": geocoded["lat"], "lon": geocoded["lon"]}]
    if (not isinstance(endpoints, list) or not 1 <= len(endpoints) <= 2
            or any(not isinstance(e, dict) or not isinstance(e.get("lat"), (int, float))
                   or not isinstance(e.get("lon"), (int, float)) for e in endpoints)):
        raise bad_request("provide endpoints (1 or 2 with numeric lat and lon) or location_text")
    if (not isinstance(w, dict) or not _valid_date(w.get("start")) or not _valid_date(w.get("end"))
            or w["end"] <= w["start"]):
        raise bad_request("construction_window needs valid start and end (YYYY-MM-DD), end after start")
    try:
        max_shift = int(body.get("max_shift_months", 24))
    except (TypeError, ValueError):
        raise bad_request("max_shift_months must be a number")
    if not 0 <= max_shift <= 120:
        raise bad_request("max_shift_months must be between 0 and 120")
    eps = [{"name": e.get("name"), "lat": e["lat"], "lon": e["lon"]} for e in endpoints]
    result = wi.whatif(name, eps, {"start": w["start"], "end": w["end"]}, svc.all_projects(with_ids=False),
                     utility=utility, voltage_kv=body.get("voltage_kv"), max_shift_months=max_shift,
                     geocoded=geocoded, roads_affected=body.get("roads_affected"), work_hours=body.get("work_hours"),
                     today=today)
    return add_traffic(result, body)


def add_traffic(result, body):
    """Proposed project's road crossings, closure plans and conflicts with other owners' closures (spec U3.6)."""
    t = STATE.traffic
    if t is None:
        return result
    pr = result["proposed"]
    proposed = {"id": "PROPOSED", "name": pr["name"], "project_type": "line" if len(pr["endpoints"]) == 2 else "substation",
                "endpoints": pr["endpoints"], "center": pr["center"], "construction_window": pr["construction_window"],
                "roads_affected": body.get("roads_affected"), "work_hours": body.get("work_hours"),
                "source": {"type": "user"}, "company_id": "__proposed__", "utility": pr.get("utility") or "USER"}
    xs = t.crossings(proposed)
    others = svc.all_projects(with_ids=False)
    conflicts = [c for p in others for c in t.conflicts_between(proposed, p)]
    result["traffic"] = {"crossings": xs, "access_roads": t.access_roads(proposed) if not xs else [],
                         "conflicts": sorted(conflicts, key=lambda c: -c["traffic_delay_avoided_veh_hours"])}
    result["closure_data_available"] = True
    result["closure_note"] = ("Road crossings use OpenStreetMap roads with SCDOT/GDOT traffic counts. Closure conflicts are "
                              "checked against every planned project's crossings and user projects' listed roads.")
    return result


def export_xlsx():
    """Sperry's template: sheet `overlaps` (cross-utility, by distance) and sheet `projects` (public)."""
    projects = {p["id"]: p for p in STATE.projects}
    ovs = sorted([o for o in STATE.overlaps if o.get("kind", "cross_utility") == "cross_utility"],
                 key=lambda o: (o["center_distance_mi"], o["id"]))
    wb = Workbook()
    ws = wb.active
    ws.title = "overlaps"
    ws.append(["overlap_id", "distance_mi", "time_gap (day)", "utility_a", "project_id_a", "project_name_a",
               "utility_b", "project_id_b", "project_name_b"])
    for o in ovs:
        a, b = projects[o["project_a"]], projects[o["project_b"]]
        ws.append([o["id"], o["center_distance_mi"], o["time_gap_days"], a["utility_name"], a["id"], a["name"],
                   b["utility_name"], b["id"], b["name"]])
    ws2 = wb.create_sheet("projects")
    ws2.append(["project_id", "utility", "state", "project_name", "name_a", "lat_a", "lon_a", "name_b", "lat_b", "lon_b",
                "lat_center", "lon_center", "in_service_date", "overlap_count", "overlap_1", "overlap_2", "overlap_3"])
    partners = {}
    for o in sorted(ovs, key=lambda o: (o["center_distance_mi"], o["id"])):
        partners.setdefault(o["project_a"], []).append(o["project_b"])
        partners.setdefault(o["project_b"], []).append(o["project_a"])
    for p in STATE.projects:
        if is_user(p):
            continue
        eps = (p.get("endpoints") or []) + [{}, {}]
        a, b = eps[0], eps[1]
        c = p.get("center") or {}
        others = partners.get(p["id"], [])
        ws2.append([p["id"], p["utility_name"], p["state"], p["name"], a.get("name"), a.get("lat"), a.get("lon"),
                    b.get("name"), b.get("lat"), b.get("lon"), c.get("lat"), c.get("lon"), p.get("in_service_date"),
                    len(others), *(others[:3] + [None] * (3 - len(others[:3])))])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
