"""Predicted congestion around a project: the roads its work closes lanes on, the crossroads that absorb the backup,
and the main roads near its sites. Numbers come from the traffic model (counts + work-zone queue model); Gemini only
writes the one-paragraph summary, which is checked against the facts (template fallback)."""
import json
import logging
import re
import threading
import time
from datetime import date

from shapely.geometry import Point
from shapely.ops import nearest_points

from ai import gemini
from ai.validate import number_check
from engine import geo, timing, traffic as T
from services import projects as psvc
from services.errors import ApiError
from services.state import STATE
from services.traffic import CLASS_RANK, _refs

log = logging.getLogger("gridlock.congestion")

DAY_START = 7                 # the daytime closure we predict for: work starting 7 AM
CROSSED_CLIP_M = 2500         # length of crossed road drawn each side of the crossing
CROSSROAD_CLIP_M = 1200       # length of a crossroad drawn around its junction
ACCESS_RADIUS_M = 5000        # main roads this close to a site are its delivery routes
ACCESS_CLIP_M = 2500          # length drawn around the road's closest point to the site
MAX_CROSSROADS = 4
MAJOR = {"motorway", "trunk", "primary", "secondary", "tertiary"}
# Daytime vehicle-hours of delay for a lane closure -> level (thresholds are assumptions).
LEVELS = [("heavy", 100), ("moderate", 15), ("light", 0)]
LOWER = {"heavy": "moderate", "moderate": "light", "light": None}
ROAD_RE = re.compile(r"\b(?:I|US|SC|GA|SR)-\d+[A-Z]?\b")


def _hour(h):
    h %= 24
    return "12 AM" if h == 0 else "12 PM" if h == 12 else f"{h} AM" if h < 12 else f"{h - 12} PM"


def _span(start, end):
    return f"{_hour(start)}–{_hour(end)}"


def _window_label(start, hours):
    return _span(start, start + hours)


def _clock(label):
    """'19:00–03:00' -> '7 PM–3 AM'."""
    m = re.match(r"(\d{1,2}):00\s*[–-]\s*(\d{1,2}):00", label or "")
    return _span(int(m.group(1)), int(m.group(2))) if m else label


def _level(delay):
    return next(name for name, lo in LEVELS if delay >= lo)


def _key(props):
    return (_refs(props.get("ref")) or [None])[0] or props.get("name") or props.get("osm_id")


def _label(props):
    refs = _refs(props.get("ref"))
    name = props.get("name")
    if refs and name:
        return f"{refs[0]} ({name})"
    return refs[0] if refs else name or "Unnamed road"


def _wgs_lines(geom):
    """UTM (Multi)LineString -> list of [[lat, lon], ...] parts, lightly simplified for drawing."""
    inv = geo._to_wgs().transform
    parts = [geom] if geom.geom_type == "LineString" else [g for g in getattr(geom, "geoms", []) if g.geom_type == "LineString"]
    out = []
    for g in parts:
        g = g.simplify(8)
        coords = [inv(x, y) for x, y in g.coords]
        if len(coords) >= 2:
            out.append([[round(lat, 6), round(lon, 6)] for lon, lat in coords])
    return out


def _clip(tx, idxs, pt, radius):
    """Union of road segments idxs clipped to a circle around pt."""
    zone = pt.buffer(radius)
    lines = []
    for i in idxs:
        g = tx.roads[i].intersection(zone)
        if not g.is_empty:
            lines.extend(_wgs_lines(g))
    return lines


def _daytime_queue(road):
    """Queue model for a lane closure starting at DAY_START: delay, and the hours traffic is backed up."""
    hours = T.S.get("closure_hours_per_crossing")["point"]
    ctype = T.closure_type(road["lanes"], road["oneway"])
    delay, _, queue = T.closure_delay(road["aadt"], road["lanes"], road["oneway"], ctype, DAY_START, hours)
    backed = sorted(h for h, q in queue.items() if q >= 25)
    span = None
    if backed:
        # hours are consecutive from the closure start (the queue drains after it); express as a clock span
        first = backed[0] if DAY_START not in backed else DAY_START
        n = 0
        while (first + n) % 24 in queue and queue[(first + n) % 24] >= 25:
            n += 1
        span = _span(first, first + max(n, 1))
    return round(delay, 1), span, hours


def _crossed_road(tx, x, used):
    """A crossed road: drawn geometry, predicted congestion for daytime work, and the recommended window."""
    pt = Point(*geo._to_utm().transform(x["point"]["lon"], x["point"]["lat"]))
    key = x.get("road_ref") or x.get("road_name") or x.get("osm_id")
    idxs = [i for i in tx.tree.query(pt.buffer(CROSSED_CLIP_M)) if _key(tx.props[i]) == key]
    delay, span, hours = _daytime_queue(x)
    level = _level(delay)
    # Quiet roads can be worked any time; otherwise the queue model's least-delay window.
    rec = "any time of day" if level == "light" else _clock(x.get("recommended_window"))
    used.update(idxs)
    return {
        "id": f"{x['id']}", "role": "crossed", "road": x.get("road_ref") or x.get("road_name") or "Unnamed road",
        "road_label": _label({"ref": x.get("road_ref"), "name": x.get("road_name")}), "road_class": x.get("road_class"),
        "level": level, "vehicles_per_day": x.get("aadt"), "traffic_count_source": x.get("aadt_source"),
        "daytime_closure": _window_label(DAY_START, hours), "daytime_delay_vehicle_hours": delay, "backed_up_hours": span,
        "recommended_window": rec, "recommended_delay_vehicle_hours": x.get("delay_veh_hours"),
        "point": x["point"], "lines": _clip(tx, idxs, pt, CROSSED_CLIP_M),
    }, pt, idxs


def _crossroads(tx, crossed, pt, idxs, used):
    """Major roads that meet the crossed road near the crossing: backed-up and detouring traffic spills onto them."""
    level = LOWER[crossed["level"]]
    if not level or not idxs:
        return []
    own = {_key(tx.props[i]) for i in idxs}
    near = tx.roads[idxs[0]]
    for i in idxs[1:]:
        near = near.union(tx.roads[i])
    near = near.intersection(pt.buffer(CROSSED_CLIP_M))
    found = {}
    for j in tx.tree.query(near.buffer(15)):
        pj = tx.props[j]
        k = _key(pj)
        if k in own or pj.get("highway") not in MAJOR or j in used:
            continue
        junction = tx.roads[j].intersection(near.buffer(15))
        if junction.is_empty:
            continue
        jp = junction.centroid
        d = jp.distance(pt)
        if k not in found or d < found[k][0]:
            found[k] = (d, j, jp)
    out = []
    for k, (d, j, jp) in sorted(found.items(), key=lambda kv: (-CLASS_RANK.get(tx.props[kv[1][1]].get("highway"), 0), kv[1][0]))[:MAX_CROSSROADS]:
        seg = [i for i in tx.tree.query(jp.buffer(CROSSROAD_CLIP_M)) if _key(tx.props[i]) == k]
        used.update(seg)
        aadt, src = tx.aadt_at(j, jp)
        out.append({"id": f"{crossed['id']}_X{len(out) + 1}", "role": "crossroad", "road": k if isinstance(k, str) else _label(tx.props[j]),
                    "road_label": _label(tx.props[j]), "road_class": tx.props[j].get("highway"), "level": level,
                    "vehicles_per_day": aadt, "traffic_count_source": src, "meets": crossed["road"],
                    "distance_km": round(d / 1000, 1), "backed_up_hours": crossed["backed_up_hours"],
                    "recommended_window": crossed["recommended_window"], "lines": _clip(tx, seg, jp, CROSSROAD_CLIP_M)})
    return out


def _access_roads(tx, project, used):
    """Sites with no road crossing (e.g. substations): the main roads trucks use to reach them, busy at rush hours."""
    out, seen = [], set()
    for e in geo.located(project.get("endpoints")):
        pt = Point(*geo._to_utm().transform(e["lon"], e["lat"]))
        cands = [i for i in tx.tree.query(pt.buffer(ACCESS_RADIUS_M)) if tx.props[i].get("highway") in MAJOR]
        by_key = {}
        for i in cands:
            k = _key(tx.props[i])
            d = tx.roads[i].distance(pt)
            if k not in by_key or d < by_key[k][0]:
                by_key[k] = (d, i)
        for k, (d, i) in sorted(by_key.items(), key=lambda kv: (-CLASS_RANK.get(tx.props[kv[1][1]].get("highway"), 0), kv[1][0]))[:3]:
            if k in seen:
                continue
            seen.add(k)
            aadt, src = tx.aadt_at(i, pt)
            near_pt = nearest_points(tx.roads[i], pt)[0]
            seg = [j for j in tx.tree.query(near_pt.buffer(ACCESS_CLIP_M)) if _key(tx.props[j]) == k]
            used.update(seg)
            level = "moderate" if aadt >= 15000 else "light"
            out.append({"id": f"ACC_{project['id']}_{len(out) + 1}", "role": "access", "road": k if isinstance(k, str) else _label(tx.props[i]),
                        "road_label": _label(tx.props[i]), "road_class": tx.props[i].get("highway"), "level": level,
                        "vehicles_per_day": aadt, "traffic_count_source": src, "near_site": e.get("name"),
                        "distance_km": round(d / 1000, 1), "backed_up_hours": "7 AM–9 AM and 4 PM–6 PM",
                        "recommended_window": "9 AM–3 PM", "lines": _clip(tx, seg, near_pt, ACCESS_CLIP_M)})
    return out


def popup(r):
    """One-line popup for a road on the map (template; numbers from the model)."""
    lvl = {"heavy": "Heavy", "moderate": "Moderate", "light": "Light"}[r["level"]]
    vpd = f"{r['vehicles_per_day']:,} vehicles/day"
    if r["role"] == "crossed":
        when = f"backups {r['backed_up_hours']}" if r.get("backed_up_hours") else "little queueing"
        return (f"{lvl} congestion expected on {r['road_label']} ({vpd}) if a lane is closed during the day: {when}. "
                f"Best time to close it: {r['recommended_window']}.")
    if r["role"] == "crossroad":
        return (f"{lvl} congestion expected on {r['road_label']} where it meets {r['meets']}: traffic backing up and "
                f"detouring from the work zone{', ' + r['backed_up_hours'] if r.get('backed_up_hours') else ''}.")
    return (f"{lvl} extra traffic expected on {r['road_label']} ({vpd}) from work trucks near {r.get('near_site') or 'the site'}, "
            f"mostly at rush hours ({r['backed_up_hours']}). Schedule deliveries {r['recommended_window']}.")


def _facts(p, roads, best, nearby):
    w = p.get("construction_window") or {}
    return {
        "project": p.get("short_name") or p["name"], "construction": f"{w.get('start')} to {w.get('end')}",
        "roads": [{k: r.get(k) for k in ("road_label", "role", "level", "vehicles_per_day", "backed_up_hours", "recommended_window", "meets")}
                  for r in roads],
        "best_time_to_work": (best or {}).get("headline"),
        "other_construction_nearby": [n.get("short_name") for n in nearby],
    }


def summary_fallback(facts):
    roads = facts["roads"]
    heavy = [r["road_label"] for r in roads if r["level"] == "heavy"]
    moderate = [r["road_label"] for r in roads if r["level"] == "moderate"]
    parts = []
    if heavy:
        parts.append(f"Expect heavy congestion on {', '.join(heavy[:3])} if lanes are closed during the day.")
    if moderate:
        parts.append(f"Expect moderate congestion on {', '.join(moderate[:3])}.")
    if not parts:
        parts.append("The roads around this project are quiet enough that work should cause little congestion.")
    if facts.get("best_time_to_work"):
        parts.append(facts["best_time_to_work"])
    if facts["other_construction_nearby"]:
        parts.append(f"{len(facts['other_construction_nearby'])} other project(s) nearby are under construction at the same time, "
                     "adding trucks to these roads.")
    return " ".join(parts)


PROMPT = ("You write a short traffic warning for a utility construction planner. In 2 or 3 plain-English sentences, say "
          "which roads and crossroads will be congested because of this project's work, when (the hours), and the best "
          "time to do the work. Name the heavy and moderate roads first; mention light roads only briefly or not at all. "
          "Write hours exactly as they appear in FACTS (12-hour clock, e.g. 7 PM–3 AM). Write vehicle counts with commas "
          "(55,500). Use ONLY the roads, hours and numbers in FACTS; do not add any other numbers or road names. "
          "No bullet points, no headings.\n\nFACTS:\n")


def _summary(facts):
    import json
    if gemini.available():
        try:
            text = gemini.generate_text(PROMPT + json.dumps(facts, indent=1, ensure_ascii=False), temperature=0.3, fake=lambda: None)
            known = {m for r in facts["roads"] for m in ROAD_RE.findall(r.get("road_label") or "")} | \
                    {m for r in facts["roads"] for m in ROAD_RE.findall(r.get("meets") or "")}
            if text and not number_check(text, facts) and not (set(ROAD_RE.findall(text)) - known):
                return text, "gemini"
        except gemini.GeminiUnavailable:
            pass
    return summary_fallback(facts), "template"


# ---------------- results cache
# One result per project, keyed on everything it depends on: the project (window, geometry, roads), the user projects
# that add nearby construction, and the date. Gemini summaries are also stored in Mongo (gemini_cache), so after the
# first warm-up a restart recomputes everything quickly.
_results = {}
_lock = threading.Lock()


def _fingerprint(p, others, today):
    users = sorted((o["id"], str(o.get("updated_at"))) for o in others if o.get("company_id"))
    return json.dumps([p["id"], p.get("construction_window"), p.get("endpoints"), p.get("roads_affected"),
                       str(p.get("updated_at")), users, today.isoformat()], sort_keys=True, default=str)


def project_congestion(pid, today=None):
    p = psvc.get_project(pid)
    if STATE.traffic is None:
        raise ApiError("TRAFFIC_UNAVAILABLE", "Traffic data is still loading. Try again in a minute.", 503)
    today = today or date.today()
    others = [o for o in psvc.all_projects(with_ids=False) if o["id"] != p["id"]]
    key = _fingerprint(p, others, today)
    with _lock:
        hit = _results.get(p["id"])
    if hit and hit[0] == key:
        return hit[1]
    result = _compute(p, others, today)
    with _lock:
        _results[p["id"]] = (key, result)
    return result


def warm_all(stop=None, pause_s=0.2):
    """Compute congestion for every project in the background so clicks on the map are instant."""
    t0, done, failed = time.time(), 0, 0
    ids = [p["id"] for p in psvc.all_projects(with_ids=False)]
    log.info("congestion warm-up: %d projects", len(ids))
    for pid in ids:
        if stop is not None and stop.is_set():
            return
        try:
            project_congestion(pid)
            done += 1
        except Exception as e:  # one bad project must not stop the warm-up
            failed += 1
            log.warning("congestion warm-up failed for %s: %s", pid, e)
        if done % 25 == 0:
            log.info("congestion warm-up: %d/%d", done, len(ids))
        time.sleep(pause_s)
    log.info("congestion warm-up finished: %d done, %d failed in %.0fs", done, failed, time.time() - t0)


def cached_count():
    with _lock:
        return len(_results)


def _compute(p, others, today):
    tx = STATE.traffic
    xs = tx.crossings(p)
    used, roads = set(), []
    seen_roads = set()
    for x in xs:
        crossed, pt, idxs = _crossed_road(tx, x, used)
        if crossed["road"] in seen_roads:
            continue
        seen_roads.add(crossed["road"])
        roads.append(crossed)
        roads.extend(_crossroads(tx, crossed, pt, idxs, used))
    # Nothing drawable (no crossing, or crossed roads not mapped near the site): show the site's access roads too.
    if not any(r["lines"] for r in roads):
        roads.extend(_access_roads(tx, p, used))
    order = {"heavy": 0, "moderate": 1, "light": 2}
    roads.sort(key=lambda r: (order[r["level"]], {"crossed": 0, "access": 1, "crossroad": 2}[r["role"]], -(r["vehicles_per_day"] or 0)))
    for r in roads:
        r["popup"] = popup(r)
    best = timing.best_time(p, xs, others, tx.crossings, today)
    nearby = best.get("nearby_active") or []
    facts = _facts(p, roads, best, nearby)
    text, source = _summary(facts)
    return {
        "project_id": p["id"], "summary": text, "summary_source": source, "best_time": best, "roads": roads,
        "other_construction": nearby,
        "levels": {"heavy": f"over {LEVELS[0][1]} vehicle-hours of delay for a daytime lane closure",
                   "moderate": f"{LEVELS[1][1]}–{LEVELS[0][1]} vehicle-hours", "light": f"under {LEVELS[1][1]} vehicle-hours"},
        "basis": ("Traffic counts from SCDOT/GDOT (else estimated by road class), a work-zone queue model for a lane closure "
                  f"starting {_hour(DAY_START)}, and OpenStreetMap roads. Crossroads get one level less than the road they meet. "
                  "Levels are predictions, not live traffic."),
    }
