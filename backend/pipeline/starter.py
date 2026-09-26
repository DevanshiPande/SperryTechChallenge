"""Load Sperry's starter workbook (Projects_Overlaps.xlsx) into Project-shaped dicts.
Used by the answer-key test and as fixture data for contract tests."""
from datetime import date, datetime

import openpyxl
from dateutil import parser as dateparser

from engine import geo, quality, windows
from pipeline import endpoints as ep

UTILITY_NAMES = {"DESC": "Dominion Energy South Carolina", "GPC": "Georgia Power"}
STATES = {"DESC": "SC", "GPC": "GA"}
DOCUMENTS = {"DESC": "DESC 2024-2028 project descriptions", "GPC": "Georgia Power 2025 IRP Volume 3 (2024 GA ITS Ten-Year Plan)"}


def parse_mixed_date(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return dateparser.parse(str(v), dayfirst=False).date().isoformat()


def load_starter_rows(path):
    wb = openpyxl.load_workbook(path, data_only=False)
    ws = wb["projects"]
    rows = list(ws.iter_rows(values_only=True))
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:] if r[0]]


def starter_projects(path, today=None):
    out = []
    for r in load_starter_rows(path):
        utility = r["project_id"].split("_")[0]
        eps = []
        for side in ("a", "b"):
            name = r[f"name_{side}"]
            if not name:
                continue
            lat, lon = r[f"lat_{side}"], r[f"lon_{side}"]
            found = lat is not None and lon is not None
            eps.append({"name": name, "lat": lat if found else None, "lon": lon if found else None,
                        "confidence": "high" if found else "not_found",
                        "source": "Sperry starter file" if found else None, "county": None})
        split = ep.split_endpoints(r["project_name"])
        ptype = ep.project_type(split["endpoints"]) if split["endpoints"] else ("line" if len(eps) == 2 else "substation")
        isd = parse_mixed_date(r["in_service_date"])
        window, wflags = windows.estimated_window(isd, ptype)
        located = geo.located(eps)
        confs = [e["confidence"] for e in eps]
        p = {
            "id": r["project_id"],
            "utility": utility,
            "utility_name": UTILITY_NAMES[utility],
            "state": STATES[utility],
            "name": r["project_name"],
            "short_name": ep.short_name(split["endpoints"] or [e["name"] for e in eps], r["project_name"]),
            "work_type_label": ep.work_type_label(r["project_name"], ptype),
            "voltage_kv": split["voltage_kv"],
            "project_type": ptype,
            "status": "Planned",
            "in_service_date": isd,
            "construction_window": window,
            "endpoints": eps,
            "counties": [],
            "center": geo.center_of(eps),
            "geometry": geo.geojson(eps),
            "location_confidence": weakest_confidence(confs),
            "description": None,
            "cost": None,
            "source": {"document": DOCUMENTS[utility], "page": None},
            "quality_flags": [],
            "overlap_ids": [],
            "county_source": None,
        }
        if not located:
            p["location_confidence"] = "not_found"
        for code in split["flags"] + wflags:
            quality.add_flag(p, code)
        quality.location_flags(p, today)
        out.append(p)
    quality.coord_conflicts(out, ep_normalize)
    return out


def ep_normalize(name):
    from pipeline.fetch_substations import normalize
    return normalize(name)


ORDER = ["high", "medium", "low", "not_found"]


def weakest_confidence(confs):
    """Weakest among endpoints; a not_found end next to a located one caps the project at medium."""
    if not confs:
        return "not_found"
    located = [c for c in confs if c != "not_found"]
    if not located:
        return "not_found"
    worst = max(located, key=ORDER.index)
    if len(located) < len(confs) and ORDER.index(worst) < ORDER.index("medium"):
        worst = "medium"
    return worst
