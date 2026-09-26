"""Agent tools: thin wrappers over services/. The company is never a tool argument: it comes from the caller identity.

Read tools execute immediately. Write tools only validate + describe (pending action); `execute` runs on confirm."""
from datetime import date

from engine import geo, overlaps as eng
from services import jobs, messages, projects as psvc, public, resources
from services.common import money
from services.errors import ApiError, bad_request
from services.geocode import geocode

MAX_ROWS = 10


# ---------- compact views (what the model sees) ----------
def c_project(p, extra=None):
    return {"id": p["id"], "short_name": p.get("short_name"), "name": p["name"], "utility": p.get("utility"),
            "utility_name": p.get("utility_name"), "work_type": p.get("work_type_label"),
            "in_service_date": p.get("in_service_date"), "construction_window": p.get("construction_window"),
            "location_confidence": p.get("location_confidence"), "counties": p.get("counties"),
            "origin": eng.origin(p), **(extra or {})}


def c_overlap(o, with_cost=True):
    out = {"id": o["id"], "label": o["label"], "kind": o.get("kind"), "project_a": o["project_a"],
           "project_b": o["project_b"], "center_distance_mi": o["center_distance_mi"],
           "closest_distance_km": o["closest_distance_km"], "tier": o["tier"],
           "window_overlap_months": o["window_overlap_months"], "time_gap_days": o["time_gap_days"],
           "score": o["score"], "rank": o["rank"], "potential": o["potential"]}
    if with_cost:
        out["illustrative_savings_usd"] = o["cost_scenario"]["totals"]["savings"]
    return out


def c_resource(r):
    return {k: r.get(k) for k in ("id", "company_name", "name", "type", "quantity", "location", "available_from",
                                  "available_to", "date_label", "rate_label", "distance_km") if k in r}


def c_job(j):
    return {k: j.get(k) for k in ("id", "company_name", "title", "openings", "location", "pay_label", "date_label",
                                  "qualifications", "status", "distance_km") if k in j}


def _geo(text):
    g = geocode(text)
    if not g:
        raise bad_request(f'Could not locate "{text}". Ask the user for a town name.')
    return g


# ---------- read tools ----------
def search_projects(ident, q=None, utility=None, source=None, near_text=None, radius_km=40, year_from=None,
                    year_to=None):
    ps = psvc.list_projects(utility=utility, year_from=year_from, year_to=year_to, q=q, source=source)
    rows = []
    if near_text:
        g = _geo(near_text)
        r = float(radius_km or 40)
        for p in ps:
            if p.get("center"):
                d = round(geo.haversine_km(g, p["center"]), 1)
                if d <= r:
                    rows.append((d, p))
        rows.sort(key=lambda x: x[0])
        return {"near": g["label"], "radius_km": r, "count": len(rows),
                "projects": [c_project(p, {"distance_km": d}) for d, p in rows[:MAX_ROWS]]}
    return {"count": len(ps), "projects": [c_project(p) for p in ps[:MAX_ROWS]]}


def get_project(ident, project_id):
    p = psvc.get_project(project_id)
    ids = set(p.get("overlap_ids") or []) | set(p.get("user_overlap_ids") or [])
    ovs = [c_overlap(o) for o in psvc.all_overlaps() if o["id"] in ids]
    return {"project": c_project(p, {"description": (p.get("description") or "")[:400], "status": p.get("status"),
                                     "quality_flags": [f["code"] for f in p.get("quality_flags") or []]}),
            "overlaps": sorted(ovs, key=lambda o: -o["score"])[:MAX_ROWS]}


def list_overlaps(ident, kind=None, potential=None, max_mi=None, sort="score", limit=5):
    s = sort or "score"
    ovs = psvc.list_overlaps(max_mi=max_mi, potential=potential, kind=kind, sort=s if s != "savings" else "score")
    if s == "savings":
        ovs = sorted(ovs, key=lambda o: (-o["cost_scenario"]["totals"]["savings"], -o["score"]))
    n = max(1, min(int(limit or 5), MAX_ROWS))
    return {"count": len(ovs), "sort": s, "overlaps": [c_overlap(o) for o in ovs[:n]]}


def get_overlap(ident, overlap_id):
    o = psvc.get_overlap(overlap_id)
    a, b = psvc.get_project(o["project_a"]), psvc.get_project(o["project_b"])
    return {"overlap": {**c_overlap(o), "tier_explanation": o["tier_explanation"],
                        "shared_endpoint": o["shared_endpoint"], "cost_totals": o["cost_scenario"]["totals"]},
            "project_a": c_project(a), "project_b": c_project(b)}


def get_cost_scenario(ident, overlap_id):
    o = psvc.get_overlap(overlap_id)
    sc = o["cost_scenario"]
    return {"overlap_id": o["id"], "label": o["label"], "illustrative": True, "unit_rates": sc["unit_rates"],
            "totals": sc["totals"], "range": sc["range"], "assumptions": sc["assumptions"]}


def check_feasibility(ident, location_text, start_date, end_date, roads_affected=None, work_hours=None):
    r = public.run_whatif({"name": "Proposed project", "location_text": location_text,
                           "construction_window": {"start": start_date, "end": end_date},
                           "roads_affected": roads_affected, "work_hours": work_hours})
    return {"location": r["proposed"]["geocoded"]["label"] if r["proposed"]["geocoded"] else None,
            "nearby_projects": r["overlaps"][:MAX_ROWS], "suggestion": r["suggestion"],
            "closure_conflicts": r["closure_conflicts"], "closure_note": r["closure_note"]}


def find_resources(ident, q=None, type=None, near_text=None, radius_km=40, available_on=None):
    near = None
    if near_text:
        g = _geo(near_text)
        near = f"{g['lat']},{g['lon']}"
    rs = resources.list_resources(type=type, near=near, radius_km=radius_km, q=q, available_on=available_on)
    return {"count": len(rs), "resources": [c_resource(r) for r in rs[:MAX_ROWS]]}


def my_inventory(ident):
    company = ident.require_company()
    rs = resources.list_resources(company_id=company["id"])
    return {"company": company["name"], "count": len(rs), "resources": [c_resource(r) for r in rs[:MAX_ROWS]]}


def my_reservations(ident, role=None):
    rs = resources.list_reservations(ident, role)
    return {"count": len(rs), "reservations": [{k: r.get(k) for k in ("id", "resource_id", "resource_name", "quantity",
                                                                       "from", "to", "status", "requester_company_name")}
                                               for r in rs[:MAX_ROWS]]}


def search_jobs(ident, q=None, near_text=None, qualification=None):
    near = None
    if near_text:
        g = _geo(near_text)
        near = f"{g['lat']},{g['lon']}"
    js = jobs.list_jobs(q=q, near=near, qualification=qualification)
    return {"count": len(js), "jobs": [c_job(j) for j in js[:MAX_ROWS]]}


def list_conversations(ident):
    cs = messages.list_conversations(ident)
    return {"count": len(cs), "conversations": [{k: c.get(k) for k in ("id", "topic", "overlap_id", "participants",
                                                                         "last_message_at", "last_message_preview")}
                                                 for c in cs[:MAX_ROWS]]}


# ---------- write tools: validate (preview) + execute (on confirm) ----------
def _fmt_day(iso):
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _plural(name, qty):
    n = name.strip()
    return n if qty == 1 or n.lower().endswith("s") else n + "s"


def v_add_resource(ident, args):
    company = ident.require_company()
    missing = [k for k in ("name", "type", "quantity") if args.get(k) in (None, "")]
    if missing:
        raise bad_request(f"missing required fields: {', '.join(missing)} (type is equipment or crew)")
    data = {k: args[k] for k in ("name", "type", "quantity", "location_text", "available_from", "available_to",
                                 "daily_rate", "notes") if args.get(k) not in (None, "")}
    fields, notes = resources.normalize_fields(company, data)
    q = fields["quantity"]
    summary = (f"Add {q} {_plural(fields['name'], q).lower()} to {company['name']}'s inventory at "
               f"{fields['location']['label']}, available {_fmt_day(fields['available_from'])} to "
               f"{_fmt_day(fields['available_to'])}, {fields['rate_label'].lower()}.")
    if notes:
        summary += f" ({'; '.join(notes)}; edit if needed.)"
    return data, summary, {"collection": "resources", "fields": fields,
                           "location_point": {"lat": fields["location"]["lat"], "lon": fields["location"]["lon"]}}


def x_add_resource(ident, args):
    r = resources.create_resource(ident, args)
    return r, [{"collection": "resources", "op": "insert", "id": r["id"]}], \
        f"Added {r['quantity']} {_plural(r['name'], r['quantity']).lower()} to your inventory. They're now visible to " \
        f"other companies."


def v_update_resource(ident, args):
    rid, fields = args.get("resource_id"), args.get("fields") or {}
    if not rid or not fields:
        raise bad_request("resource_id and fields are required")
    doc, upd, notes = resources.check_update(ident, rid, fields)
    changes = ", ".join(f"{k} → {v}" for k, v in upd.items() if k not in ("date_label", "rate_label", "location"))
    if "location" in upd:
        changes = (changes + ", " if changes else "") + f"location → {upd['location']['label']}"
    return {"resource_id": rid, "fields": fields}, f"Update {doc['name']} ({rid}): {changes}.", \
        {"collection": "resources", "id": rid, "fields": upd}


def x_update_resource(ident, args):
    r = resources.update_resource(ident, args["resource_id"], args["fields"])
    return r, [{"collection": "resources", "op": "update", "id": r["id"]}], f"Updated {r['name']}."


def v_remove_resource(ident, args):
    rid = args.get("resource_id")
    if not rid:
        raise bad_request("resource_id is required")
    doc, _, _ = resources.check_update(ident, rid, {})
    return {"resource_id": rid}, f"Remove {doc['name']} ({doc['quantity']} listed) from your inventory.", \
        {"collection": "resources", "id": rid}


def x_remove_resource(ident, args):
    out = resources.delete_resource(ident, args["resource_id"])
    return out, [{"collection": "resources", "op": "delete", "id": args["resource_id"]}], "Removed it from your inventory."


PROJECT_ARGS = ("name", "location_text", "start_date", "end_date", "description", "work_type", "roads_affected",
                "lane_closures", "work_hours", "voltage_kv")


def v_create_project(ident, args):
    company = ident.require_company()
    missing = [k for k in ("name", "location_text", "start_date", "end_date") if args.get(k) in (None, "")]
    if missing:
        raise bad_request(f"missing required fields: {', '.join(missing)}")
    data = {k: args[k] for k in PROJECT_ARGS if args.get(k) not in (None, "")}
    p = psvc.build_user_project("USR_PREVIEW", company, data)
    ovs = eng.user_project_overlaps(p, [x for x in psvc.all_projects(with_ids=False)])
    summary = (f"Add project \"{p['name']}\" for {company['name']} at {p['endpoints'][0]['name']}, "
               f"{_fmt_day(p['construction_window']['start'])} to {_fmt_day(p['construction_window']['end'])}"
               + (f", roads {', '.join(p['roads_affected'])}" if p["roads_affected"] else "")
               + f". It would overlap {len(ovs)} planned project{'s' if len(ovs) != 1 else ''} within 25 miles.")
    return data, summary, {"collection": "projects", "fields": {k: p[k] for k in ("name", "construction_window",
                                                                                  "roads_affected", "work_hours",
                                                                                  "lane_closures", "work_type_label")},
                           "location_point": p["center"],
                           "overlaps_preview": [{"project_id": o["project_b"], "label": o["label"],
                                                 "center_distance_mi": o["center_distance_mi"]} for o in ovs[:5]]}


def x_create_project(ident, args):
    out = psvc.create_user_project(ident, args)
    p = out["project"]
    changes = [{"collection": "projects", "op": "insert", "id": p["id"]}] + \
              [{"collection": "overlaps", "op": "insert", "id": o["id"]} for o in out["overlaps"]]
    n = len(out["overlaps"])
    return out, changes, f"Added {p['name']}. It overlaps {n} planned project{'s' if n != 1 else ''}" + \
        (f" and has {len(out['closure_conflicts'])} lane-closure conflict(s) to review." if out["closure_conflicts"]
         else ".")


def v_update_project(ident, args):
    pid, fields = args.get("project_id"), args.get("fields") or {}
    if not pid or not fields:
        raise bad_request("project_id and fields are required")
    _, company, doc = psvc._own_user_project(ident, pid)
    unknown = set(fields) - set(psvc.USER_FIELDS)
    if unknown:
        raise bad_request(f"unknown fields: {', '.join(sorted(unknown))}")
    for k in ("start_date", "end_date"):
        if k in fields:
            from services.common import parse_iso
            parse_iso(fields[k], k)
    return {"project_id": pid, "fields": fields}, \
        f"Update project {doc['name']}: " + ", ".join(f"{k} → {v}" for k, v in fields.items()) + ".", \
        {"collection": "projects", "id": pid, "fields": fields}


def x_update_project(ident, args):
    out = psvc.update_user_project(ident, args["project_id"], args["fields"])
    return out, [{"collection": "projects", "op": "update", "id": args["project_id"]}], \
        f"Updated {out['project']['name']}; its overlaps were recomputed."


def v_request_reservation(ident, args):
    rid = args.get("resource_id")
    if not rid:
        raise bad_request("resource_id is required")
    res, f = resources.check_reservation(ident, rid, args)
    return {"resource_id": rid, **f}, (f"Request {f['quantity']} x {res['name']} from {res['company_name']}, "
                                       f"{_fmt_day(f['from'])} to {_fmt_day(f['to'])}. The owner must accept."), \
        {"collection": "reservations", "fields": {"resource_id": rid, **f}}


def x_request_reservation(ident, args):
    a = dict(args)
    rid = a.pop("resource_id")
    r = resources.create_reservation(ident, rid, a)
    return r, [{"collection": "reservations", "op": "insert", "id": r["id"]}], \
        f"Sent the request for {r['quantity']} x {r['resource_name']}. It's pending until the owner responds."


def v_respond_reservation(ident, args):
    rsv, status = args.get("reservation_id"), args.get("status")
    r = resources.check_status_change(ident, rsv, status)
    verb = {"accepted": "Accept", "declined": "Decline", "cancelled": "Cancel"}[status]
    return {"reservation_id": rsv, "status": status}, \
        f"{verb} the reservation of {r['quantity']} x {r['resource_name']} ({r['from']} to {r['to']}).", \
        {"collection": "reservations", "id": rsv, "fields": {"status": status}}


def x_respond_reservation(ident, args):
    r = resources.update_reservation(ident, args["reservation_id"], args["status"])
    return r, [{"collection": "reservations", "op": "update", "id": r["id"]}], f"Reservation {r['status']}."


def v_post_job(ident, args):
    company = ident.require_company()
    missing = [k for k in ("title", "openings") if args.get(k) in (None, "")]
    if missing:
        raise bad_request(f"missing required fields: {', '.join(missing)}")
    data = {k: args[k] for k in ("title", "openings", "location_text", "pay_min", "pay_max", "start_date", "end_date",
                                 "qualifications") if args.get(k) not in (None, "")}
    fields, notes = jobs.normalize_job(company, data)
    summary = (f"Post {fields['openings']} opening{'s' if fields['openings'] != 1 else ''} for {fields['title']} at "
               f"{fields['location']['label']}, {fields['pay_label']}"
               + (f", {fields['date_label']}" if fields.get("date_label") else "") + ".")
    if notes:
        summary += f" ({'; '.join(notes)}.)"
    return data, summary, {"collection": "jobs", "fields": fields}


def x_post_job(ident, args):
    j = jobs.create_job(ident, args)
    return j, [{"collection": "jobs", "op": "insert", "id": j["id"]}], f"Posted {j['title']}. Workers can apply now."


def v_send_message(ident, args):
    to = messages.check_send(ident, args.get("to_company_name"), args.get("text"))
    if args.get("overlap_id"):
        psvc.get_overlap(args["overlap_id"])
    data = {"to_company_name": to["name"], "text": args["text"].strip(), "overlap_id": args.get("overlap_id") or None}
    return data, f"Send to {to['name']}: \"{data['text'][:140]}\"", {"collection": "messages", "fields": data}


def x_send_message(ident, args):
    out = messages.send_to_company(ident, args["to_company_name"], args["text"], args.get("overlap_id"))
    return out, [{"collection": "messages", "op": "insert", "id": out["message"]["id"]}], \
        f"Message sent to {args['to_company_name']}."


# ---------- traffic + contracts (spec update U3.7 / U4.3) ----------
def _c_crossing(x):
    return {k: x.get(k) for k in ("id", "project_id", "road_ref", "road_name", "road_class", "lanes", "aadt", "aadt_source",
                                  "closure_type", "recommended_window", "delay_veh_hours", "worst_window",
                                  "worst_delay_veh_hours", "delay_cost_usd")}


def get_traffic_plan(ident, crossing_id=None, lat=None, lon=None, road_ref=None, closure_hours=None):
    from services import traffic as tsvc
    if crossing_id:
        x = tsvc.get_crossing(crossing_id)
        return {"crossing": _c_crossing(x), "conflicts": [{k: c[k] for k in ("id", "road_ref", "project_a", "project_b",
                                                                              "traffic_delay_avoided_veh_hours", "merged_window")}
                                                          for c in x["conflicts"]]}
    if lat is None or lon is None:
        raise bad_request("give crossing_id, or lat and lon (optionally road_ref)")
    r = tsvc.plan_request({"point": {"lat": lat, "lon": lon}, "road_ref": road_ref, "closure_hours": closure_hours})
    return {"road": r["road"], **{k: r[k] for k in ("closure_type", "closure_hours", "recommended_window", "delay_veh_hours",
                                                    "vehicles_affected", "worst_window", "worst_delay_veh_hours")}}


def list_closure_conflicts(ident, kind=None, min_delay=None):
    from services import traffic as tsvc
    cs = tsvc.list_conflicts(kind, min_delay)
    return {"count": len(cs), "conflicts": [{k: c[k] for k in ("id", "road_ref", "road_name", "project_a", "project_b",
                                                                "distance_km", "traffic_delay_avoided_veh_hours",
                                                                "delay_avoided_usd", "merged_window")} for c in cs[:MAX_ROWS]]}


def list_road_crossings(ident, project_id=None, road_ref=None, min_aadt=None):
    from services import traffic as tsvc
    xs = tsvc.list_crossings(project_id, road_ref, min_aadt)
    return {"count": len(xs), "crossings": [_c_crossing(x) for x in xs[:MAX_ROWS]]}


def analyze_uploaded_contract(ident, contract_id):
    from services import contracts as csvc
    r = csvc.match(ident, contract_id, {})
    top = [{"project_id": m["project_id"], "short_name": m["short_name"], "utility_name": m["utility_name"],
            "score": m["score"], "score_breakdown": m["score_breakdown"], "potential": m["potential"],
            "center_distance_mi": m["center_distance_mi"], "window_overlap_months": m["window_overlap_months"],
            "savings_usd": m["cost_estimate"]["total_estimated_savings_usd"], "savings_range_usd": m["cost_estimate"]["range_usd"],
            "shift": m["suggestion"]["explanation"]} for m in r["matches"][:5]]
    return {"contract_id": contract_id, "project": r["project"]["name"], "matches_count": r["summary"]["matches_count"],
            "best_time_to_work": {"headline": r["work_timing"]["headline"], "reasons": r["work_timing"]["reasons"]},
            "best_match": r["best_match"], "top_matches": top,
            "crossings": [_c_crossing(x) for x in r["traffic"]["crossings"][:6]]}


def v_save_contract(ident, args):
    from services import contracts as csvc
    ident.require_company()
    cid = args.get("contract_id")
    if not cid:
        raise bad_request("contract_id is required")
    doc = csvc.get_contract(ident, cid)
    f = doc.get("reviewed_fields") or doc["extracted"]
    name = (f.get("project_name") or {}).get("value") or "Uploaded contract"
    w = [(f.get(k) or {}).get("value") for k in ("start_date", "end_date")]
    return {"contract_id": cid}, f"Save the uploaded contract \"{name}\" ({w[0]} to {w[1]}) as a project for your company. " \
                                 "It then joins the overlap analysis.", {"collection": "projects", "fields": {"name": name}}


def x_save_contract(ident, args):
    from services import contracts as csvc
    out = csvc.save(ident, args["contract_id"])
    changes = [{"collection": "projects", "op": "insert", "id": out["project"]["id"]}] + \
              [{"collection": "overlaps", "op": "insert", "id": o["id"]} for o in out["overlaps"]]
    return out, changes, f"Saved {out['project']['name']} as a project. It overlaps {len(out['overlaps'])} planned projects."


# ---------- registry ----------
S, I, N, B = {"type": "string"}, {"type": "integer"}, {"type": "number"}, {"type": "boolean"}


def obj(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


READ = {
    "search_projects": (search_projects, "projects",
                        "Search planned projects (public filings and user projects). near_text is a place name.",
                        obj({"q": S, "utility": {"type": "string", "enum": ["DESC", "GPC", "USER"]},
                             "source": {"type": "string", "enum": ["public_filing", "user"]}, "near_text": S,
                             "radius_km": N, "year_from": I, "year_to": I})),
    "get_project": (get_project, "projects", "One project and its overlaps.", obj({"project_id": S}, ["project_id"])),
    "list_overlaps": (list_overlaps, "opportunities",
                      "Coordination opportunities (overlaps). kind cross_utility is Sperry's ranked DESC x GPC list. "
                      "sort: score, distance, timeline or savings.",
                      obj({"kind": {"type": "string", "enum": ["cross_utility", "user_project"]},
                           "potential": {"type": "string", "enum": ["high", "moderate", "lower"]}, "max_mi": N,
                           "sort": {"type": "string", "enum": ["score", "distance", "timeline", "savings"]},
                           "limit": I})),
    "get_overlap": (get_overlap, "opportunities", "One overlap with both projects and cost totals.",
                    obj({"overlap_id": S}, ["overlap_id"])),
    "get_cost_scenario": (get_cost_scenario, "cost", "Illustrative cost scenario totals and assumptions for an overlap.",
                          obj({"overlap_id": S}, ["overlap_id"])),
    "check_feasibility": (check_feasibility, "feasibility",
                          "Nearby planned projects, a schedule-shift suggestion and lane-closure conflicts for a "
                          "proposed project. Dates YYYY-MM-DD.",
                          obj({"location_text": S, "start_date": S, "end_date": S, "roads_affected": S,
                               "work_hours": S}, ["location_text", "start_date", "end_date"])),
    "find_resources": (find_resources, "inventory", "Shared equipment and crews listed by companies.",
                       obj({"q": S, "type": {"type": "string", "enum": ["equipment", "crew"]}, "near_text": S,
                            "radius_km": N, "available_on": S})),
    "my_inventory": (my_inventory, "inventory", "The user's own company's listed resources.", obj({})),
    "my_reservations": (my_reservations, "inventory", "The user's company's reservations.",
                        obj({"role": {"type": "string", "enum": ["incoming", "outgoing"]}})),
    "search_jobs": (search_jobs, "jobs", "Open jobs.", obj({"q": S, "near_text": S, "qualification": S})),
    "list_conversations": (list_conversations, "messages", "The user's company's conversations.", obj({})),
    "get_traffic_plan": (get_traffic_plan, "road_closures",
                         "Recommended lane-closure window and delay for a road crossing (by crossing_id) or any point on a road.",
                         obj({"crossing_id": S, "lat": N, "lon": N, "road_ref": S, "closure_hours": I})),
    "list_closure_conflicts": (list_closure_conflicts, "road_closures",
                               "Places where two owners close the same road within 3 km during overlapping windows.",
                               obj({"kind": {"type": "string", "enum": ["cross_utility", "user_project"]}, "min_delay": N})),
    "list_road_crossings": (list_road_crossings, "road_closures",
                            "Road crossings of planned lines with traffic volumes and closure plans.",
                            obj({"project_id": S, "road_ref": S, "min_aadt": N})),
    "analyze_uploaded_contract": (analyze_uploaded_contract, "contracts",
                                  "Coordination partners, savings ranges and road crossings for an uploaded contract.",
                                  obj({"contract_id": S}, ["contract_id"])),
}

WRITE = {
    "add_resource": (v_add_resource, x_add_resource, "inventory",
                     "Propose listing equipment or a crew in the user's inventory. Needs name, type (equipment or "
                     "crew) and quantity; location defaults to the company yard and dates to 30 days from today.",
                     obj({"name": S, "type": {"type": "string", "enum": ["equipment", "crew"]}, "quantity": I,
                          "location_text": S, "available_from": S, "available_to": S, "daily_rate": N, "notes": S},
                         ["name", "type", "quantity"])),
    "update_resource": (v_update_resource, x_update_resource, "inventory",
                        "Propose changing one of the user's resources. fields may include name, quantity, "
                        "location_text, available_from, available_to, daily_rate, notes.",
                        obj({"resource_id": S, "fields": {"type": "object"}}, ["resource_id", "fields"])),
    "remove_resource": (v_remove_resource, x_remove_resource, "inventory", "Propose removing one of the user's resources.",
                        obj({"resource_id": S}, ["resource_id"])),
    "create_project": (v_create_project, x_create_project, "projects",
                       "Propose adding a user project (joins the overlap analysis). Needs name, location_text, "
                       "start_date and end_date (YYYY-MM-DD).",
                       obj({"name": S, "location_text": S, "start_date": S, "end_date": S, "description": S,
                            "work_type": S, "roads_affected": S, "lane_closures": S, "work_hours": S, "voltage_kv": I},
                           ["name", "location_text", "start_date", "end_date"])),
    "update_project": (v_update_project, x_update_project, "projects", "Propose changing one of the user's projects.",
                       obj({"project_id": S, "fields": {"type": "object"}}, ["project_id", "fields"])),
    "request_reservation": (v_request_reservation, x_request_reservation, "inventory",
                            "Propose reserving another company's resource. Dates YYYY-MM-DD.",
                            obj({"resource_id": S, "quantity": I, "from": S, "to": S, "project_id": S, "note": S},
                                ["resource_id", "quantity", "from", "to"])),
    "respond_reservation": (v_respond_reservation, x_respond_reservation, "inventory",
                            "Propose accepting/declining (owner) or cancelling (requester) a reservation.",
                            obj({"reservation_id": S,
                                 "status": {"type": "string", "enum": ["accepted", "declined", "cancelled"]}},
                                ["reservation_id", "status"])),
    "post_job": (v_post_job, x_post_job, "jobs", "Propose posting a job. pay is per hour.",
                 obj({"title": S, "openings": I, "location_text": S, "pay_min": N, "pay_max": N, "start_date": S,
                      "end_date": S, "qualifications": {"type": "array", "items": S}}, ["title", "openings"])),
    "send_message": (v_send_message, x_send_message, "messages", "Propose sending a message to another company.",
                     obj({"to_company_name": S, "text": S, "overlap_id": S}, ["to_company_name", "text"])),
    "save_contract_as_project": (v_save_contract, x_save_contract, "projects",
                                 "Propose saving an uploaded contract as the user's project.",
                                 obj({"contract_id": S}, ["contract_id"])),
}


def declarations(read_only=False):
    out = [{"name": n, "description": d, "parameters": p} for n, (_, _, d, p) in READ.items()]
    if not read_only:
        out += [{"name": n, "description": d, "parameters": p} for n, (_, _, _, d, p) in WRITE.items()]
    return out


def page_for(tool):
    if tool in READ:
        return READ[tool][1]
    if tool in WRITE:
        return WRITE[tool][2]
    return None


def run_read(ident, name, args):
    fn = READ[name][0]
    try:
        return fn(ident, **(args or {}))
    except TypeError as e:
        raise bad_request(f"bad arguments for {name}: {e}")


def validate_write(ident, name, args):
    return WRITE[name][0](ident, dict(args or {}))


def execute_write(ident, name, args):
    return WRITE[name][1](ident, dict(args or {}))


def error_result(e):
    if isinstance(e, ApiError):
        return {"error": {"code": e.code, "message": e.message}}
    return {"error": {"code": "INTERNAL", "message": "Tool failed"}}


__all__ = ["READ", "WRITE", "declarations", "run_read", "validate_write", "execute_write", "page_for", "money"]
