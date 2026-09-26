"""Build data/projects.json and data/overlaps.json from the filings. Offline.

Run from backend/:  python -m pipeline.build            (uses caches; calls FCC for new county lookups)
                    python -m pipeline.build --offline  (no network: counties only from cache)
"""
import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from engine import budget, geo, quality, windows
from engine.overlaps import cross_utility_overlaps
from pipeline import endpoints as ep
from pipeline import locate, parse_desc, parse_gpc
from pipeline.counties import SOURCE as COUNTY_SOURCE
from pipeline.counties import CountyLookup
from pipeline.fetch_substations import normalize, region_hint
from pipeline.starter import load_starter_rows, weakest_confidence

BACKEND = Path(__file__).resolve().parents[1]
DATA = BACKEND / "data"
STARTER = DATA / "raw" / "Projects_Overlaps.xlsx"

UTILITY_NAMES = {"DESC": "Dominion Energy South Carolina", "GPC": "Georgia Power"}
STATES = {"DESC": "SC", "GPC": "GA"}
DOCUMENTS = {"DESC": "DESC 2024-2028 $2 million and above project descriptions",
             "GPC": "Georgia Power 2025 IRP Volume 3 (2024 GA ITS Ten-Year Plan)"}
COST_NOTE = "Dominion only; Georgia Power costs are redacted"
COORD_CONFLICT_KM = 0.5


def parsed_inputs():
    desc = parse_desc.parse()
    gpc_rows, _ = parse_gpc.parse()
    parse_desc.write_review(desc)
    parse_gpc.write_review(gpc_rows)
    items = [{"id": d["id"], "utility": "DESC", "name": d["title"], "raw": d, "description": d["description"]} for d in desc]
    items += [{"id": g["id"], "utility": "GPC", "name": g["name"], "zone": g["zone"], "raw": g,
               "description": g["description"]} for g in gpc_rows if g["included"]]
    return items


def desc_cost(c):
    if not c:
        return None
    return {"currency": "USD",
            "by_year": {"2024": c["2024"], "2025": c["2025"], "2026": c["2026"], "2027": c["2027"], "2028": c["2028"],
                        "previous": c["previous"]},
            "total": c["total"], "note": COST_NOTE}


def check_states(item, loc, counties):
    """Look up counties. An endpoint in the other state must be in the border band (a tie line across the river);
    for GPC the project must also carry a Savannah/Augusta region hint (SAV prefix, zone 219 or 215).
    Otherwise the match is a same-name substation in the other state: reject it."""
    home = STATES[item["utility"]]
    hint = region_hint(item["name"], item.get("zone")) if item["utility"] == "GPC" else True
    for i, e in enumerate(loc["endpoints"]):
        if e["lat"] is None:
            continue
        county = counties.county(e["lat"], e["lon"])
        state = county.rsplit(", ", 1)[-1] if county else None
        if state and state != home and not (hint and locate.near_border(e["lat"], e["lon"])):
            loc["match"][i] = locate.reject(loc["match"][i], f"WRONG_STATE({state})")
            e.update(lat=None, lon=None, confidence="not_found", source=None, county=None)
        else:
            e["county"] = county


def assemble(item, loc, counties, today):
    util, raw = item["utility"], item["raw"]
    names = loc["endpoint_names"]
    ptype = ep.project_type(names)
    eps = loc["endpoints"]
    flags = list(raw.get("flags") or []) + loc["flags"]

    if util == "DESC":
        isd = raw["in_service_date"]
        cost = desc_cost(raw["cost"])
        window, wflags = windows.desc_window(cost, isd, ptype)
        status = raw["status"]
        extra = {"project_ref": raw["project_ref"], "need": raw["need"]}
    else:
        isd = raw["need_date"]
        cost = None
        window, wflags = windows.gpc_window(raw["start_date"], raw["need_date"], ptype)
        status = "Planned"  # the ITS plan has no status column
        extra = {"teams": raw["teams"], "zone": raw["zone"], "sponsor": raw["sponsor"]}
    flags += wflags

    confs = [e["confidence"] for e in eps]
    counties_list = list(dict.fromkeys(e["county"] for e in eps if e["county"]))
    p = {
        "id": item["id"],
        "utility": util,
        "utility_name": UTILITY_NAMES[util],
        "state": STATES[util],
        "name": item["name"],
        "voltage_kv": loc["voltage_kv"],
        "project_type": ptype,
        "status": status,
        "in_service_date": isd,
        "construction_window": window,
        "endpoints": eps,
        "center": geo.center_of(eps),
        "geometry": geo.geojson(eps),
        "location_confidence": weakest_confidence(confs),
        "description": item["description"] or None,
        "cost": cost,
        "source": {"document": DOCUMENTS[util], "page": raw.get("page"), "type": "public_filing"},
        "quality_flags": [],
        "overlap_ids": [],
        "short_name": ep.short_name(names, item["name"]),
        "work_type_label": ep.work_type_label(item["name"], ptype),
        "counties": counties_list,
        "county_source": COUNTY_SOURCE if counties_list else None,
        **extra,
    }
    for code in dict.fromkeys(flags):
        if code in quality.MESSAGES or code in quality.CODES:
            quality.add_flag(p, code)
    quality.location_flags(p, today)
    budget.attach(p)
    return p


def starter_reference():
    """(utility, normalized endpoint name) -> [(lat, lon, label)] from Sperry's starter workbook."""
    ref = {}
    for r in load_starter_rows(STARTER):
        util = r["project_id"].split("_")[0]
        for side in ("a", "b"):
            if r[f"name_{side}"] and r[f"lat_{side}"] is not None:
                ref.setdefault((util, normalize(r[f"name_{side}"])), []).append(
                    (r[f"lat_{side}"], r[f"lon_{side}"], r[f"name_{side}"]))
    return ref


def starter_conflicts(projects, ref):
    """COORD_CONFLICT when our position for a name differs from Sperry's starter file by > 0.5 km.
    Returns the answer-key comparison rows for the build report."""
    report = []
    for p in projects:
        for e in geo.located(p["endpoints"]):
            for lat, lon, label in ref.get((p["utility"], normalize(e["name"])), []):
                km = geo.haversine_km(e, {"lat": lat, "lon": lon})
                report.append((p["id"], e["name"], round(km, 3)))
                if km > COORD_CONFLICT_KM:
                    quality.add_flag(p, "COORD_CONFLICT",
                                     f'{e["name"]} substation appears at two different positions ({e["lat"]}, {e["lon"]} '
                                     f"from OSM vs {lat}, {lon} in Sperry's starter file, {km:.2f} km apart).")
    return report


def build(offline=False, today=None, write=True):
    today = today or date.today()
    items = parsed_inputs()
    located = locate.locate_all(items)
    counties = CountyLookup(offline=offline)
    for it in items:
        check_states(it, located[it["id"]], counties)
    counties.save()
    locate.write_review(locate.review_rows(items, located))
    projects = [assemble(it, located[it["id"]], counties, today) for it in items]

    quality.coord_conflicts(projects, normalize, COORD_CONFLICT_KM)
    report = starter_conflicts(projects, starter_reference())

    from services import traffic as traffic_svc
    tix = traffic_svc.load(str(DATA / "traffic"))
    overlaps = cross_utility_overlaps(projects, tix.pair_savings if tix else None, today)
    by_id = {p["id"]: p for p in projects}
    for o in overlaps:
        by_id[o["project_a"]]["overlap_ids"].append(o["id"])
        by_id[o["project_b"]]["overlap_ids"].append(o["id"])

    if write:
        (DATA / "projects.json").write_text(json.dumps(projects, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
        (DATA / "overlaps.json").write_text(json.dumps(overlaps, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    return projects, overlaps, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    projects, overlaps, report = build(offline=args.offline)
    conf = {}
    for p in projects:
        conf[p["location_confidence"]] = conf.get(p["location_confidence"], 0) + 1
    print(f"projects: {len(projects)} (DESC {sum(p['utility'] == 'DESC' for p in projects)}, "
          f"GPC {sum(p['utility'] == 'GPC' for p in projects)})  location_confidence: {conf}")
    print(f"cross-utility overlaps: {len(overlaps)}")
    for o in overlaps[:15]:
        print(f"  #{o['rank']:>2} {o['label']:<45} {o['center_distance_mi']:>6} mi  {o['closest_distance_km']:>6} km "
              f"{o['tier']:<13} gap {o['time_gap_days']} d  win {o['window_overlap_months']} mo  score {o['score']}")
    print("answer-key endpoints vs Sperry's starter file (km):")
    for pid, name, km in report:
        print(f"  {'OK ' if km <= 1 else 'FAR'} {pid:<10} {name:<24} {km}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
