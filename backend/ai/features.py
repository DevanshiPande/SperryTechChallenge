"""Brief, draft and scenario assist. Code builds the facts and does every number; Gemini writes words."""
import logging
import re
from datetime import date

from dateutil import parser as dateparser

from ai import fakes, gemini, prompts
from ai.validate import number_check
from engine import closures, cost
from services import projects as psvc
from services.common import money
from services.errors import bad_request, gemini_unavailable
from services.geocode import geocode

log = logging.getLogger("gridlock.ai")

MODES = ("summary", "plan", "risks", "traffic")


# ---------- brief ----------
def brief_facts(o):
    a, b = psvc.get_project(o["project_a"]), psvc.get_project(o["project_b"])
    t = o["cost_scenario"]["totals"]

    def proj(p):
        return {"id": p["id"], "short_name": p.get("short_name"), "name": p["name"], "utility": p.get("utility_name"),
                "work_type": p.get("work_type_label"), "in_service_date": p.get("in_service_date"),
                "construction_window": p.get("construction_window"), "location_confidence": p.get("location_confidence"),
                "quality_flags": [f["code"] for f in p.get("quality_flags") or []]}

    return {
        "overlap_id": o["id"], "label": o["label"], "project_a": proj(a), "project_b": proj(b),
        "center_distance_mi": o["center_distance_mi"], "closest_distance_km": o["closest_distance_km"],
        "tier": o["tier"], "tier_explanation": o["tier_explanation"], "shared_endpoint": o["shared_endpoint"],
        "window_overlap_months": o["window_overlap_months"], "time_gap_days": o["time_gap_days"],
        "score": o.get("score"), "score_breakdown": o.get("score_breakdown"),
        "estimated_savings": _savings_facts(o),
        "sandbox_scenario": {"separate_usd": t["separate"], "coordinated_usd": t["coordinated"], "savings_usd": t["savings"],
                             "note": "editable sandbox with placeholder inputs"},
    }


def _savings_facts(o):
    e = o.get("cost_estimate") or {}
    comps = {k: v.get("point") for k, v in (e.get("components") or {}).items() if v.get("applies")}
    return {"point_usd": e.get("total_estimated_savings_usd"), "range_usd": e.get("range_usd"),
            "reference_budget_usd": e.get("reference_budget_usd"), "reference_budget_source": e.get("reference_budget_source"),
            "components_usd": comps, "sources": [s.get("name") for s in e.get("sources") or []],
            "assumptions": e.get("assumptions")}


def traffic_facts(project_ids, conflicts_filter=None):
    """Crossings (with best/worst closure windows) for the given projects, plus closure conflicts between them."""
    from services.state import STATE
    t = STATE.traffic
    if t is None:
        return {"available": False}
    ps = [psvc.get_project(pid) for pid in project_ids]
    xs = []
    for p in ps:
        for x in sorted(t.crossings(p), key=lambda x: -(x.get("worst_delay_veh_hours") or 0))[:4]:
            xs.append({"project": p.get("short_name"), "road": x.get("road_ref") or x.get("road_name") or "unnamed road",
                       "vehicles_per_day": x.get("aadt"), "traffic_count_source": x.get("aadt_source"),
                       "closure_type": x.get("closure_type"), "closure_hours": x.get("closure_hours"),
                       "recommended_window": x.get("recommended_window"), "delay_vehicle_hours": x.get("delay_veh_hours"),
                       "worst_window": x.get("worst_window"), "worst_delay_vehicle_hours": x.get("worst_delay_veh_hours")})
    conf = t.conflicts_between(ps[0], ps[1]) if len(ps) == 2 else []
    return {"available": True, "crossings": xs,
            "shared_road_conflicts": [{"road": c.get("road_ref") or c.get("road_name"), "distance_km": c["distance_km"],
                                       "delay_avoided_vehicle_hours": c["traffic_delay_avoided_veh_hours"],
                                       "merged_window": c["merged_window"]} for c in conf]}


def fallback_brief(o, mode):
    """Template text (ported from mock-server.js). Used when Gemini is off or its output fails the guards."""
    a, b = psvc.get_project(o["project_a"]), psvc.get_project(o["project_b"])
    wa, wb = a.get("construction_window") or {}, b.get("construction_window") or {}
    sav = o["cost_estimate"].get("total_estimated_savings_usd")
    if mode == "plan":
        return (f"Coordination plan for {o['label']}: 1) Planners from {a['utility_name']} and {b['utility_name']} "
                f"confirm construction windows ({wa.get('start')} to {wa.get('end')} and {wb.get('start')} to "
                f"{wb.get('end')}). 2) " +
                (f"Schedule shared crews and equipment during the {o['window_overlap_months']} overlapping months."
                 if o["window_overlap_months"] > 0 else "Decide whether one schedule can move so construction overlaps.")
                + " 3) " + ("Share one laydown yard and delivery route." if (o["closest_distance_km"] or 99) < 8
                            else "Share crews and contractors; staging stays separate.")
                + " 4) " + ("Coordinate outages at the shared substation." if o["shared_endpoint"]
                            else "Exchange contacts and review permits for common roads."))
    if mode == "traffic":
        return traffic_fallback(o["label"], traffic_facts([o["project_a"], o["project_b"]]))
    if mode == "risks":
        risks = [
            "construction windows do not overlap, so sharing requires a schedule change"
            if o["window_overlap_months"] == 0 else None,
            "work at a shared substation needs coordinated outages" if o["shared_endpoint"] else None,
            "one or more locations are not fully confirmed"
            if a.get("location_confidence") != "high" or b.get("location_confidence") != "high" else None,
            "cost figures are illustrative until real bids are available",
        ]
        return f"Risks for {o['label']}: " + "; ".join(r for r in risks if r) + "."
    return (f"{a['utility_name']}'s \"{a['name']}\" and {b['utility_name']}'s \"{b['name']}\" are "
            f"{o['center_distance_mi']} miles apart center to center, and their closest points are "
            f"{o['closest_distance_km']} km apart ({(o['tier_explanation'] or '').lower()}). "
            + ("Both projects connect to the same substation, so outages and work at that site must be coordinated. "
               if o["shared_endpoint"] else "")
            + (f"They are under construction at the same time for about {o['window_overlap_months']} months, which is "
               f"the window to share crews and equipment. " if o["window_overlap_months"] > 0 else
               f"Their construction windows do not overlap (in-service dates are {o['time_gap_days']} days apart), so "
               f"sharing would require shifting one schedule. ")
            + (f"Estimated savings from coordinating: about {money(sav)} (illustrative)." if sav else "")).strip()


def brief(overlap_id, mode="summary", refresh=False):
    mode = mode or "summary"
    if mode not in MODES:
        raise bad_request("mode must be summary, plan, risks or traffic")
    o = psvc.get_overlap(overlap_id)
    if not refresh:
        hit = psvc.brief_cache_get(o["id"], mode)
        if hit:
            return {"overlap_id": o["id"], "mode": mode, "brief": hit["brief"], "source": hit["source"], "cached": True}
    facts = brief_facts(o)
    if mode == "traffic":
        facts = {"label": o["label"], "traffic": traffic_facts([o["project_a"], o["project_b"]])}
    text, source = None, "gemini"
    if gemini.available():
        try:
            text = gemini.generate_text(prompts.brief_prompt(mode, facts), temperature=0.3, use_cache=not refresh,
                                        fake=lambda: fallback_brief(o, mode))
            bad = number_check(text, facts, extra_allowed=range(1, 6) if mode == "plan" else ())
            if bad:
                log.info("brief guard rejected %s/%s: numbers not in facts %s", o["id"], mode, bad[:5])
                text = None
        except gemini.GeminiUnavailable as e:
            log.info("brief fallback for %s: %s", o["id"], e)
            text = None
    if not text:
        text, source = fallback_brief(o, mode), "fallback"
    psvc.brief_cache_set(o["id"], mode, text, source)
    return {"overlap_id": o["id"], "mode": mode, "brief": text, "source": source, "cached": False}


# ---------- draft ----------
FOLLOW_UPS = {
    "location": "Where exactly is the work? A town or road segment works.", "start_date": "What is the exact start date?",
    "end_date": "What is the end date?", "lane_closures": "Is there a lane closure, and in which direction?",
    "roads_affected": "Which road or segment is affected?", "work_hours": "What are the work hours?",
    "quantity": "How many units are available?", "dates": "Which dates?", "rate": "What is the daily rate?",
    "openings": "How many openings?", "project": "Which project is this for?",
    "requirements": "What qualifications are required?", "name": "What should this be called?",
    "role": "What is the role?", "description": "Can you describe the work in a sentence?",
    "work_type": "What type of work is it?",
}


def _iso(v):
    if v in (None, ""):
        return None
    s = str(v).strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return None  # only explicit YYYY-MM-DD from the model; a missing year must stay missing
    try:
        return dateparser.isoparse(s).date().isoformat()
    except (ValueError, OverflowError):
        return None


def _date_range(v):
    if v in (None, ""):
        return None
    parts = [p.strip() for p in re.split(r"\s+to\s+", str(v))]
    isos = [_iso(p) for p in parts]
    if not isos or any(x is None for x in isos) or len(isos) > 2:
        return None
    if len(isos) == 2 and isos[1] < isos[0]:
        return None
    return " to ".join(isos)


def _count(v):
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return n if n >= 1 else None


def _user_value(v):
    if isinstance(v, dict):
        return v.get("value")
    return v


def clean_field(kind, key, value):
    if value in (None, ""):
        return None
    if kind == "project" and key in ("start_date", "end_date"):
        return _iso(value)
    if key == "dates":
        return _date_range(value)
    if key in ("quantity", "openings"):
        return _count(value)
    if key == "roads_affected":
        roads = closures.normalize_roads(value)
        return ", ".join(roads) if roads else None
    return str(value).strip() if isinstance(value, str) else value


def draft(kind, text, current=None, today=None):
    if kind not in prompts.DRAFT_FIELDS:
        raise bad_request("kind must be project, resource or job")
    if not isinstance(text, str) or not text.strip():
        raise bad_request("text is required")
    if not gemini.available():
        raise gemini_unavailable("Gemini is not responding. Use the manual form.")
    current = current if isinstance(current, dict) else {}
    keys = prompts.DRAFT_FIELDS[kind]
    user = {k: _user_value(current.get(k)) for k in keys if _user_value(current.get(k)) not in (None, "")}
    try:
        out = gemini.generate_json(prompts.draft_prompt(kind, text, user, (today or date.today()).isoformat()),
                                   prompts.draft_schema(kind), temperature=0.1, fake=lambda: fakes.draft(kind, text))
    except gemini.GeminiUnavailable:
        raise gemini_unavailable("Gemini is not responding. Use the manual form.")

    fields = {}
    for k in keys:
        if k in user:
            fields[k] = {"value": user[k], "confidence": "user"}
            continue
        f = out.get(k) if isinstance(out.get(k), dict) else {}
        v = clean_field(kind, k, f.get("value"))
        conf = f.get("confidence") if f.get("confidence") in ("high", "medium") else "medium"
        fields[k] = {"value": v, "confidence": conf if v is not None else None}

    if kind == "project" and fields["start_date"]["value"] and fields["end_date"]["value"] \
            and fields["end_date"]["value"] < fields["start_date"]["value"] and "end_date" not in user:
        fields["end_date"] = {"value": None, "confidence": None}

    loc = fields.get("location", {}).get("value")
    g = geocode(loc) if loc else None
    missing = [k for k in keys if fields[k]["value"] in (None, "")]
    qs = [q.strip() for q in (out.get("follow_up_questions") or []) if isinstance(q, str) and q.strip()][:3]
    if not qs and missing:
        qs = [FOLLOW_UPS[k] for k in missing if k in FOLLOW_UPS][:3]
    if loc and not g:
        qs = (["I couldn't place that location on the map. Can you give a town name?"] + qs)[:3]
    return {
        "kind": kind, "fields": fields, "missing": missing, "ready": len(missing) <= 2,
        "follow_up_questions": qs if missing or (loc and not g) else [],
        "location_point": {"lat": g["lat"], "lon": g["lon"], "label": g["label"]} if g else None,
        "source": "gemini", "note": "Draft only. Nothing is saved until the user reviews it.",
    }


# ---------- scenario assist ----------
def _clamp(path, value):
    if path.startswith("unit_rates."):
        lo, hi = 0, 100000
    elif path.endswith("laydown_sites"):
        lo, hi = 1, 10
    else:
        lo, hi = 0, 1000
    v = max(lo, min(hi, float(value)))
    return int(round(v)) if not path.startswith("unit_rates.") or v.is_integer() else round(v, 2)


def _scenario_inputs(sc):
    return {"unit_rates": sc["unit_rates"], "separate": sc["separate"], "coordinated": sc["coordinated"]}


def _validate_scenario(sc):
    try:
        for k in prompts.SCENARIO_PATHS:
            node = sc
            for part in k.split("."):
                node = node[part]
            if isinstance(node, bool) or not isinstance(node, (int, float)):
                raise TypeError
    except (KeyError, TypeError):
        raise bad_request("scenario must be a cost_scenario object with numeric inputs")


def scenario_reply(sc, note=None, window_overlap_months=None):
    t = sc["totals"]
    s, c, sv = t["separate"], t["coordinated"], t["savings"]
    pct = abs(round(sv / s * 100)) if s else 0
    reply = (f"Applying these changes gives separate work at {money(s)} and coordinated work at {money(c)}, "
             f"about {money(abs(sv))} ({pct}%) {'lower' if sv >= 0 else 'higher'}.")
    if note and not re.search(r"\d", note):
        reply += " " + note.strip()
    if window_overlap_months == 0:
        reply += (" Note: these construction windows do not overlap today, so sharing trucks requires moving one "
                  "schedule.")
    return reply


def scenario_assist(overlap_id, message, scenario=None):
    if not isinstance(message, str) or not message.strip():
        raise bad_request("message is required")
    o = psvc.get_overlap(overlap_id)
    base = scenario if scenario else o["cost_scenario"]
    if not isinstance(base, dict):
        raise bad_request("scenario must be an object")
    _validate_scenario(base)
    if not gemini.available():
        raise gemini_unavailable("Gemini is not responding. Edit the inputs directly.")
    facts = {k: v for k, v in brief_facts(o).items() if k not in ("cost_illustrative",)}
    try:
        out = gemini.generate_json(prompts.scenario_prompt(facts, _scenario_inputs(base), message),
                                   prompts.SCENARIO_SCHEMA, temperature=0.1, fake=lambda: fakes.scenario(message))
    except gemini.GeminiUnavailable:
        raise gemini_unavailable("Gemini is not responding. Edit the inputs directly.")
    changes = []
    for ch in out.get("changes") or []:
        if not isinstance(ch, dict) or ch.get("path") not in prompts.SCENARIO_PATHS:
            continue
        try:
            value = _clamp(ch["path"], ch.get("value"))
        except (TypeError, ValueError):
            continue
        label = str(ch.get("label") or ch["path"]).strip()[:120]
        changes = [c for c in changes if c["path"] != ch["path"]] + [{"path": ch["path"], "value": value,
                                                                       "label": label}]
    nxt = cost.apply_changes(base, changes)
    t = nxt["totals"]
    if changes:
        reply = scenario_reply(nxt, out.get("note"), o["window_overlap_months"])
    else:
        reply = ("I couldn't map that to a scenario input. I can change unit rates, truck-days, mobilization events "
                 "or laydown yards.")
    return {"overlap_id": o["id"], "reply": reply, "suggested_changes": changes,
            "preview_totals": {"separate": t["separate"], "coordinated": t["coordinated"], "savings": t["savings"],
                               "savings_pct": t["savings_pct"]}}


def traffic_fallback(label, tf):
    if not tf.get("available"):
        return f"Traffic for {label}: road and traffic data are not loaded."
    if not tf["crossings"]:
        return f"Traffic for {label}: neither project's straight-line route crosses a major road, so no lane closures are expected."
    parts = []
    for x in tf["crossings"][:4]:
        parts.append(f"{x['project']} crosses {x['road']} ({x['vehicles_per_day']:,} vehicles/day): close {x['recommended_window']} "
                     f"({x['delay_vehicle_hours']} vehicle-hours of delay); a {x['worst_window']} closure would cause "
                     f"{x['worst_delay_vehicle_hours']} vehicle-hours.")
    for c in tf["shared_road_conflicts"]:
        parts.append(f"Both projects close {c['road']} within {c['distance_km']} km: merging into one {c['merged_window']} closure "
                     f"changes delay by {c['delay_avoided_vehicle_hours']} vehicle-hours and saves one traffic-control setup.")
    return f"Traffic plan for {label}: " + " ".join(parts)


def crossing_brief(crossing_id, refresh=False):
    """Traffic-management note for one crossing, from computed facts only (same guard + fallback as briefs)."""
    from services import traffic as tsvc
    x = tsvc.get_crossing(crossing_id)
    key = f"{crossing_id}:traffic"
    if not refresh:
        hit = psvc.brief_cache_get(crossing_id, "traffic")
        if hit:
            return {"crossing_id": crossing_id, "mode": "traffic", "brief": hit["brief"], "source": hit["source"], "cached": True}
    p = psvc.get_project(x["project_id"])
    facts = {"project": p.get("short_name"), "road": x.get("road_ref") or x.get("road_name"), "road_class": x.get("road_class"),
             "lanes": x.get("lanes"), "vehicles_per_day": x.get("aadt"), "traffic_count_source": x.get("aadt_source"),
             "closure_type": x.get("closure_type"), "closure_hours": x.get("closure_hours"),
             "recommended_window": x["plan"]["recommended_window"], "delay_vehicle_hours": x["plan"]["delay_veh_hours"],
             "vehicles_affected": x["plan"]["vehicles_affected"], "worst_window": x["plan"]["worst_window"],
             "worst_delay_vehicle_hours": x["plan"]["worst_delay_veh_hours"], "delay_cost_usd": x["plan"]["delay_cost_usd"],
             "worst_delay_cost_usd": x["plan"]["worst_delay_cost_usd"],
             "conflicts": [{"other_project": c["project_b"] if c["project_a"] == p["id"] else c["project_a"],
                            "delay_avoided_vehicle_hours": c["traffic_delay_avoided_veh_hours"]} for c in x["conflicts"]]}
    text, source = None, "gemini"
    if gemini.available():
        try:
            text = gemini.generate_text(prompts.brief_prompt("traffic", facts), temperature=0.3, use_cache=not refresh,
                                        fake=lambda: None)
            if text and number_check(text, facts):
                text = None
        except gemini.GeminiUnavailable:
            text = None
    if not text:
        text, source = (f"{facts['project']} crosses {facts['road']} ({facts['vehicles_per_day']:,} vehicles/day). Close it "
                        f"{facts['recommended_window']}: about {facts['delay_vehicle_hours']} vehicle-hours of delay versus "
                        f"{facts['worst_delay_vehicle_hours']} for a {facts['worst_window']} closure."), "fallback"
    psvc.brief_cache_set(crossing_id, "traffic", text, source)
    return {"crossing_id": crossing_id, "mode": "traffic", "brief": text, "source": source, "cached": False}
