"""Traffic management (spec update U3): road crossings, traffic volumes, closure plans and closure conflicts.

Roads (OSM) and traffic counts (SCDOT 2025, GDOT 2017) are loaded once from data/traffic/*.geojson. Line projects are
straight lines between substations, so crossing points are approximate."""
import json
import logging
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from engine import geo, sources, traffic as T, windows
from engine.closures import normalize_road, normalize_roads
from engine.overlaps import owner

log = logging.getLogger("gridlock.traffic")

CLASS_RANK = {"motorway": 5, "trunk": 4, "primary": 3, "secondary": 2, "tertiary": 1}
DEFAULT_LANES = {"motorway": (2, True), "trunk": (4, False), "primary": (2, False), "secondary": (2, False), "tertiary": (2, False)}
DEDUPE_M = 300          # two carriageways of one divided road = one crossing
ROUTE_MATCH_M = 2000    # count station with the same route
MOTORWAY_ROUTE_MATCH_M = 8000
NEAREST_STATION_M = 300  # count station without a route (GDOT, SC secondary)
CONFLICT_KM = 3.0
ACCESS_KM = 1.0


def _utm(geoms):
    tr = geo._to_utm()

    def f(coords):
        x, y = tr.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])
    return shapely.transform(geoms, f)


def _int(v):
    m = re.match(r"\d+", str(v or ""))
    return int(m.group()) if m else None


def _refs(ref):
    return [r for r in (normalize_road(x) for x in re.split(r"[;,]", ref or "")) if r]


class TrafficIndex:
    def __init__(self, roads, stations):
        self.props = [f["properties"] for f in roads["features"]]
        wgs = np.array([LineString(f["geometry"]["coordinates"]) for f in roads["features"]], dtype=object)
        self.roads = _utm(wgs)
        self.tree = STRtree(self.roads)
        self.st_props = [f["properties"] for f in stations["features"]]
        pts = np.array([Point(f["geometry"]["coordinates"]) for f in stations["features"]], dtype=object)
        self.stations = _utm(pts)
        self.st_tree = STRtree(self.stations)
        self._cache = {}
        log.info("traffic: %d road segments, %d count stations", len(self.props), len(self.st_props))

    # ---------------- road attributes
    def aadt_at(self, i, pt):
        """(aadt, source label) for road i near UTM point pt."""
        p = self.props[i]
        refs = set(_refs(p.get("ref")))
        if refs:
            # Interstate count stations are sparse; along the same route a farther station is still representative.
            radius = MOTORWAY_ROUTE_MATCH_M if p.get("highway") == "motorway" else ROUTE_MATCH_M
            best = None
            for j in self.st_tree.query(pt.buffer(radius)):
                sp = self.st_props[j]
                d = self.stations[j].distance(pt)
                if sp.get("route") in refs and d <= radius and (best is None or d < best[0]):
                    best = (d, sp)
            if best:
                return best[1]["aadt"], f'{best[1]["source"]} ({best[1]["route"]}, station {best[0] / 1000:.1f} km away)'
        best = None
        key = (_refs(p.get("ref")) or [None])[0] or p.get("name") or p.get("osm_id")
        for j in self.st_tree.query(pt.buffer(NEAREST_STATION_M)):
            sp = self.st_props[j]
            if sp.get("route") and sp["route"] not in refs:
                continue
            d = self.stations[j].distance(pt)
            if d > NEAREST_STATION_M or (best is not None and d >= best[0]):
                continue
            # A station without a route counts only if this road is the road it sits on (its nearest road).
            k = int(self.tree.query_nearest(self.stations[j])[0])
            kp = self.props[k]
            if ((_refs(kp.get("ref")) or [None])[0] or kp.get("name") or kp.get("osm_id")) != key:
                continue
            best = (d, sp)
        if best:
            return best[1]["aadt"], f'{best[1]["source"]} (station {best[0]:.0f} m away)'
        fb = sources.get("fallback_aadt")
        return fb.get(p.get("highway"), 2500), "estimated by road class"

    def road_info(self, i, pt):
        p = self.props[i]
        lanes, oneway = _int(p.get("lanes")), p.get("oneway") in ("yes", "-1", "true")
        lanes_assumed = lanes is None
        if lanes is None:
            lanes, oneway = DEFAULT_LANES.get(p.get("highway"), (2, False))
        aadt, aadt_src = self.aadt_at(i, pt)
        refs = _refs(p.get("ref"))
        return {"road_name": p.get("name"), "road_ref": refs[0] if refs else None, "road_refs": refs, "road_class": p.get("highway"),
                "lanes": lanes, "lanes_assumed": lanes_assumed, "oneway": oneway, "aadt": aadt, "aadt_source": aadt_src,
                "osm_id": p.get("osm_id")}

    def _plan_summary(self, road, hours=None):
        pl = T.plan(road["aadt"], road["lanes"], road["oneway"], hours)
        return pl, {k: pl[k] for k in ("closure_type", "closure_hours", "recommended_window", "delay_veh_hours", "vehicles_affected",
                                       "delay_cost_usd", "worst_window", "worst_delay_veh_hours")}

    # ---------------- crossings
    def crossings(self, project):
        key = (project["id"], json.dumps(project.get("endpoints"), sort_keys=True, default=str),
               json.dumps(project.get("roads_affected")), json.dumps(project.get("construction_window")))
        if key in self._cache:
            return self._cache[key]
        line = self._line_crossings(project)
        crossed = {r for x in line for r in (x.get("road_refs") or [])}
        # A road the user listed that the line already crosses is the same closure: don't count it twice.
        typed = [x for x in self._typed_road_crossings(project) if x["road_ref"] not in crossed]
        out = line + typed
        self._cache[key] = out
        return out

    def _line_crossings(self, project):
        line = geo.utm_geometry(project.get("endpoints"))
        if not isinstance(line, LineString):
            return []
        found = []
        for i in self.tree.query(line, predicate="intersects"):
            inter = line.intersection(self.roads[i])
            pts = [inter] if inter.geom_type == "Point" else list(getattr(inter, "geoms", []))
            for pt in pts:
                if pt.geom_type != "Point":
                    continue
                p = self.props[i]
                k = (_refs(p.get("ref")) or [None])[0] or p.get("name") or p.get("osm_id")
                if any(f[0] == k and f[1].distance(pt) < DEDUPE_M for f in found):
                    continue
                found.append((k, pt, i))
        found.sort(key=lambda f: line.project(f[1]))
        inv = geo._to_wgs().transform
        out = []
        for n, (_, pt, i) in enumerate(found, 1):
            lon, lat = inv(pt.x, pt.y)
            road = self.road_info(i, pt)
            _, summ = self._plan_summary(road)
            out.append({"id": f"XING_{project['id']}_{n}", "project_id": project["id"], **road,
                        "point": {"lat": round(lat, 6), "lon": round(lon, 6)}, "point_approximate": True,
                        "est_closure_hours": summ["closure_hours"], "work_window": project.get("construction_window"),
                        "owner": owner(project), **summ})
        return out

    def _typed_road_crossings(self, project):
        """User projects: each road they list counts as a crossing at the project center."""
        refs = list(dict.fromkeys(normalize_roads(project.get("roads_affected"))))
        c = project.get("center")
        if not refs or not c:
            return []
        x, y = geo._to_utm().transform(c["lon"], c["lat"])
        pt = Point(x, y)
        out = []
        for n, ref in enumerate(refs, 1):
            near = [i for i in self.tree.query(pt.buffer(5000)) if ref in _refs(self.props[i].get("ref"))]
            if near:
                i = min(near, key=lambda k: self.roads[k].distance(pt))
                road = self.road_info(i, pt)
            else:
                cls = "motorway" if ref.startswith("I-") else "trunk" if ref.startswith("US-") else "primary"
                lanes, oneway = DEFAULT_LANES[cls]
                road = {"road_name": None, "road_ref": ref, "road_refs": [ref], "road_class": cls, "lanes": lanes, "lanes_assumed": True,
                        "oneway": oneway, "aadt": sources.get("fallback_aadt")[cls], "aadt_source": "estimated by road class",
                        "osm_id": None}
            _, summ = self._plan_summary(road)
            out.append({"id": f"XING_{project['id']}_R{n}", "project_id": project["id"], **road, "point": dict(c),
                        "point_approximate": True, "user_typed_road": True, "lane_closures": project.get("lane_closures"),
                        "work_hours": project.get("work_hours"), "est_closure_hours": summ["closure_hours"],
                        "work_window": project.get("construction_window"), "owner": owner(project), **summ})
        return out

    def access_roads(self, project):
        """Substation work: major roads within 1 km of each located endpoint (delivery impact, no closure analysis)."""
        out, seen = [], set()
        for e in geo.located(project.get("endpoints")):
            x, y = geo._to_utm().transform(e["lon"], e["lat"])
            pt = Point(x, y)
            for i in self.tree.query(pt.buffer(ACCESS_KM * 1000)):
                p = self.props[i]
                k = (_refs(p.get("ref")) or [None])[0] or p.get("name")
                if not k or k in seen:
                    continue
                seen.add(k)
                aadt, src = self.aadt_at(i, pt)
                out.append({"road_name": p.get("name"), "road_ref": (_refs(p.get("ref")) or [None])[0], "road_class": p.get("highway"),
                            "aadt": aadt, "aadt_source": src, "distance_km": round(self.roads[i].distance(pt) / 1000, 2),
                            "near_endpoint": e["name"]})
        return sorted(out, key=lambda r: (-CLASS_RANK.get(r["road_class"], 0), r["distance_km"]))[:10]

    # ---------------- conflicts
    @staticmethod
    def _same_road(a, b):
        ra, rb = set(a.get("road_refs") or []), set(b.get("road_refs") or [])
        if ra or rb:
            return bool(ra & rb)
        return a.get("osm_id") is not None and a.get("osm_id") == b.get("osm_id")

    def conflict(self, xa, xb):
        """Closure conflict / coordination opportunity between two crossings, or None."""
        if xa["owner"] == xb["owner"] or not self._same_road(xa, xb):
            return None
        wa, wb = xa.get("work_window"), xb.get("work_window")
        if not wa or not wb or windows.overlap_days(wa, wb) < 1:
            return None
        km = geo.haversine_km(xa["point"], xb["point"])
        if km > CONFLICT_KM:
            return None
        road = xa if (xa["aadt"] or 0) >= (xb["aadt"] or 0) else xb
        m = T.merged_savings({"aadt": road["aadt"], "lanes": road["lanes"], "oneway": road["oneway"]},
                             xa["est_closure_hours"], xb["est_closure_hours"])
        start = max(windows.to_date(wa["start"]), windows.to_date(wb["start"]))
        end = min(windows.to_date(wa["end"]), windows.to_date(wb["end"]))
        return {"id": f"CONF_{xa['id']}__{xb['id']}", "road_ref": road.get("road_ref"), "road_name": road.get("road_name"),
                "crossing_a": xa["id"], "crossing_b": xb["id"], "project_a": xa["project_id"], "project_b": xb["project_id"],
                "distance_km": round(km, 2), "overlap_start": start.isoformat(), "overlap_end": end.isoformat(),
                "aadt": road["aadt"], "aadt_source": road["aadt_source"], **m}

    def conflicts_between(self, a, b):
        return [c for xa in self.crossings(a) for xb in self.crossings(b) if (c := self.conflict(xa, xb))]

    def pair_savings(self, a, b):
        """Traffic input for cost_estimate v2 (engine.overlaps traffic callable)."""
        cs = self.conflicts_between(a, b)
        if not cs:
            return None
        return {"veh_hours": round(sum(c["traffic_delay_avoided_veh_hours"] for c in cs), 1),
                "delay_usd": sum(c["delay_avoided_usd"] for c in cs), "setup_usd": sum(c["setup_cost_avoided_usd"] for c in cs),
                "roads": sorted({c["road_ref"] or c["road_name"] or "unnamed road" for c in cs})}

    def all_conflicts(self, projects):
        xs = [x for p in projects for x in self.crossings(p)]
        by_road = {}
        for x in xs:
            for r in (x.get("road_refs") or [f"osm:{x.get('osm_id')}"]):
                by_road.setdefault(r, []).append(x)
        out, seen = [], set()
        for group in by_road.values():
            for i, xa in enumerate(group):
                for xb in group[i + 1:]:
                    c = self.conflict(xa, xb)
                    if c and c["id"] not in seen:
                        seen.add(c["id"])
                        out.append(c)
        return sorted(out, key=lambda c: -c["traffic_delay_avoided_veh_hours"])

    def plan_for_point(self, lat, lon, road_ref=None, lanes=None, aadt=None, closure_hours=None, closure_type=None):
        """POST /traffic/plan: nearest matching road to the point, with overrides."""
        x, y = geo._to_utm().transform(lon, lat)
        pt = Point(x, y)
        cands = list(self.tree.query(pt.buffer(3000)))
        if road_ref:
            ref = normalize_road(road_ref)
            cands = [i for i in cands if ref in _refs(self.props[i].get("ref"))] or cands
        if cands:
            i = min(cands, key=lambda k: (self.roads[k].distance(pt), -CLASS_RANK.get(self.props[k].get("highway"), 0)))
            road = self.road_info(i, pt)
        else:
            road = {"road_name": None, "road_ref": normalize_road(road_ref) if road_ref else None, "road_class": None, "lanes": 2,
                    "lanes_assumed": True, "oneway": False, "aadt": sources.get("fallback_aadt")["secondary"],
                    "aadt_source": "estimated by road class"}
        if lanes:
            road.update(lanes=int(lanes), lanes_assumed=False)
        if aadt:
            road.update(aadt=int(aadt), aadt_source="provided")
        pl = T.plan(road["aadt"], road["lanes"], road["oneway"], closure_hours, closure_type)
        return {"road": road, **pl}


@lru_cache(maxsize=4)
def load(directory):
    d = Path(directory)
    rf, af = d / "roads.geojson", d / "aadt_points.geojson"
    if not rf.exists():
        log.warning("traffic data missing (%s): traffic features off", rf)
        return None
    roads = json.loads(rf.read_text(encoding="utf-8"))
    stations = json.loads(af.read_text(encoding="utf-8")) if af.exists() else {"features": []}
    return TrafficIndex(roads, stations)


# ---------------------------------------------------------------- API-facing helpers (use the loaded index in STATE)
def _index():
    from services.errors import ApiError
    from services.state import STATE
    if STATE.traffic is None:
        raise ApiError("TRAFFIC_UNAVAILABLE", "Road and traffic data are not loaded on this server.", 503)
    return STATE.traffic


def _projects():
    from services.projects import all_projects
    return all_projects(with_ids=False)


def list_crossings(project_id=None, road_ref=None, min_aadt=None):
    t, ps = _index(), _projects()
    if project_id:
        ps = [p for p in ps if p["id"] == project_id]
    xs = [x for p in ps for x in t.crossings(p)]
    if road_ref:
        ref = normalize_road(road_ref)
        xs = [x for x in xs if ref in (x.get("road_refs") or [])]
    if min_aadt not in (None, ""):
        xs = [x for x in xs if (x.get("aadt") or 0) >= float(min_aadt)]
    return sorted(xs, key=lambda x: (-(x.get("worst_delay_veh_hours") or 0), x["id"]))


def get_crossing(crossing_id):
    from services.errors import not_found
    t = _index()
    pid = crossing_id[len("XING_"):].rsplit("_", 1)[0] if crossing_id.startswith("XING_") else None
    ps = _projects()
    cand = [p for p in ps if p["id"] == pid] or ps
    for p in cand:
        for x in t.crossings(p):
            if x["id"] == crossing_id:
                plan = T.plan(x["aadt"], x["lanes"], x["oneway"], x["est_closure_hours"], x["closure_type"])
                conflicts = [c for c in t.all_conflicts(ps) if crossing_id in (c["crossing_a"], c["crossing_b"])]
                return {**x, "plan": plan, "conflicts": conflicts}
    raise not_found("Crossing", crossing_id)


def list_conflicts(kind=None, min_delay=None):
    from engine.overlaps import is_user
    t, ps = _index(), _projects()
    byid = {p["id"]: p for p in ps}
    cs = t.all_conflicts(ps)
    if kind == "cross_utility":
        cs = [c for c in cs if not is_user(byid[c["project_a"]]) and not is_user(byid[c["project_b"]])]
    elif kind == "user_project":
        cs = [c for c in cs if is_user(byid[c["project_a"]]) or is_user(byid[c["project_b"]])]
    if min_delay not in (None, ""):
        cs = [c for c in cs if c["traffic_delay_avoided_veh_hours"] >= float(min_delay)]
    return cs


def plan_request(body):
    from services.errors import bad_request
    t = _index()
    pt = body.get("point") or {}
    try:
        lat, lon = float(pt["lat"]), float(pt["lon"])
    except (KeyError, TypeError, ValueError):
        raise bad_request("point {lat, lon} is required")
    hours = body.get("closure_hours")
    try:
        hours = int(hours) if hours not in (None, "") else None
    except (TypeError, ValueError):
        raise bad_request("closure_hours must be a whole number")
    if hours is not None and not 1 <= hours <= 24:
        raise bad_request("closure_hours must be between 1 and 24")
    ctype = body.get("closure_type")
    if ctype not in (None, "", "lane_closure", "flagging"):
        raise bad_request("closure_type must be lane_closure or flagging")
    return t.plan_for_point(lat, lon, body.get("road_ref"), body.get("lanes"), body.get("aadt"), hours, ctype or None)


def summary():
    t, ps = _index(), _projects()
    xs = [x for p in ps for x in t.crossings(p)]
    cs = t.all_conflicts(ps)
    return {"crossings_count": len(xs), "projects_with_crossings": len({x["project_id"] for x in xs}),
            "high_volume_crossings": sum(1 for x in xs if (x.get("aadt") or 0) >= 20000),
            "conflicts_count": len(cs),
            "total_delay_avoidable_veh_hours": round(sum(max(0, c["traffic_delay_avoided_veh_hours"]) for c in cs), 1),
            "daytime_vs_night_delay_veh_hours": {"worst_windows": round(sum(x.get("worst_delay_veh_hours") or 0 for x in xs), 1),
                                                  "recommended_windows": round(sum(x.get("delay_veh_hours") or 0 for x in xs), 1)},
            "data_sources": ["OpenStreetMap roads (Overpass)", "SCDOT 2025 statewide traffic counts", "GDOT traffic counts (2017 AADT)"]}
