"""Locate project endpoints with the OSM matcher + overrides, and write the border review sheet."""
import csv
import json
import logging
import re
from pathlib import Path

from rapidfuzz import fuzz

from engine import geo
from pipeline import endpoints as ep
from pipeline.fetch_substations import CACHE_DIR, load_overrides, match_project, normalize, region_hint

log = logging.getLogger("gridlock.locate")

BACKEND = Path(__file__).resolve().parents[1]
REVIEW_CSV = BACKEND / "data" / "review" / "locations_to_review.csv"

# Savannah River line, approximated by points; "near the border" = within 60 km of any of them.
BORDER_POINTS = [(32.08, -81.10), (32.60, -81.60), (33.10, -81.85), (33.47, -82.01), (33.90, -82.40), (34.60, -82.85)]
BORDER_KM = 60


def load_features(cache_dir=CACHE_DIR):
    """DESC is matched against the SC extract (its bbox also covers the GA side of the river), GPC against GA."""
    feats = {}
    for util, state in (("DESC", "SC"), ("GPC", "GA")):
        path = Path(cache_dir) / f"substations_{state}.geojson"
        feats[util] = json.loads(path.read_text(encoding="utf-8"))["features"]
    return feats


def near_border(lat, lon):
    return any(geo.haversine_km({"lat": lat, "lon": lon}, {"lat": a, "lon": b}) <= BORDER_KM for a, b in BORDER_POINTS)


def gemini_split(name):
    """Name-split fallback (11.2). Accepted only if every returned endpoint is a substring of the title."""
    from ai import gemini, prompts
    if not gemini.available() or gemini.fake_mode():
        return None
    try:
        out = gemini.generate_json(prompts.split_prompt(name), prompts.SPLIT_SCHEMA, temperature=0)
    except gemini.GeminiUnavailable as e:
        log.warning("split fallback failed for %r: %s", name, e)
        return None
    names = [n.strip() for n in (out.get("endpoint_a"), out.get("endpoint_b")) if n and n.strip()]
    if ep.validate_fallback(name, names):
        return names
    log.info("split fallback rejected for %r: %r", name, names)
    return None


def split_name(name):
    s = ep.split_endpoints(name)
    flags = list(s["flags"])
    names = s["endpoints"]
    if s["needs_fallback"]:
        names = gemini_split(name) or []
        if not names:
            flags.append("ENDPOINT_SPLIT_FAILED")
    return names, s["voltage_kv"], flags


def _matcher_flags(results):
    flags = []
    for r in results:
        for f in r.get("flags") or []:
            if f == "AMBIGUOUS_NAME":
                flags.append("AMBIGUOUS_NAME")
            elif f.startswith("LINE_TOO_LONG"):
                flags.append("LINE_TOO_LONG")
    return list(dict.fromkeys(flags))


NAME_AGREEMENT_MIN = 80
_OSM_NAME_RE = re.compile(r'"(.*)"$')


def validate_name(endpoint_name, result):
    """The matcher's token_set_ratio scores a subset as 100 ("north spa" vs "North Substation") and accepts weak fuzzy
    hits ("riverport" vs "Airport"). Require the normalized names to agree as a whole; otherwise treat the endpoint as
    not found and keep the candidate for manual review."""
    if result.get("lat") is None or "MANUAL_OVERRIDE" in (result.get("flags") or []):
        return result
    m = _OSM_NAME_RE.search(result.get("source") or "")
    if not m:
        return result
    agreement = fuzz.token_sort_ratio(normalize(endpoint_name), normalize(m.group(1)))
    if agreement >= NAME_AGREEMENT_MIN:
        return result
    return reject(result, f"WEAK_NAME_MATCH({agreement:.0f})")


def reject(result, why):
    """Turn a match into not_found, keeping the rejected candidate for the review sheet."""
    cand = f'{result.get("source")} @ {result.get("lat")},{result.get("lon")}'
    return {**result, "lat": None, "lon": None, "confidence": "not_found", "source": None,
            "flags": (result.get("flags") or []) + [why], "rejected": cand,
            "candidates": [cand] + list(result.get("candidates") or [])}


def locate_project(pid, utility, name, features, zone=None, overrides=None):
    """-> {endpoint_names, voltage_kv, flags, endpoints: [{name, lat, lon, confidence, source, county}], match: [...]}"""
    names, kv, flags = split_name(name)
    results = match_project(name, names, utility, features, zone=zone, overrides=overrides) if names else []
    results = [validate_name(n, r) for n, r in zip(names, results)]
    eps = [{"name": n, "lat": r["lat"], "lon": r["lon"], "confidence": r["confidence"], "source": r.get("source"),
            "county": None} for n, r in zip(names, results)]
    return {"id": pid, "endpoint_names": names, "voltage_kv": kv, "flags": flags + _matcher_flags(results),
            "endpoints": eps, "match": results}


def locate_all(parsed, features=None, overrides=None):
    """parsed: [{id, utility, name, zone?}] -> {id: located}"""
    features = features or load_features()
    overrides = overrides if overrides is not None else load_overrides()
    out = {}
    for p in parsed:
        out[p["id"]] = locate_project(p["id"], p["utility"], p["name"], features[p["utility"]], p.get("zone"), overrides)
    return out


def review_rows(parsed, located):
    rows = []
    for p in parsed:
        loc = located[p["id"]]
        pts = geo.located(loc["endpoints"])
        border = any(near_border(e["lat"], e["lon"]) for e in pts)
        if not pts:  # nothing located: use the region hint (SAV prefix / Savannah or Augusta zones)
            hint = region_hint(p["name"], p.get("zone"))
            border = bool(hint and near_border(hint[0], hint[1]))
        if not border:
            continue
        for e, m in zip(loc["endpoints"], loc["match"]):
            if e["confidence"] == "high":
                continue
            rows.append({
                "project_id": p["id"], "project_name": p["name"], "endpoint_name": e["name"],
                "best_match": e.get("source") or m.get("rejected") or "", "lat": e["lat"], "lon": e["lon"],
                "confidence": e["confidence"],
                "flags": ";".join(m.get("flags") or []), "candidates": " | ".join(m.get("candidates") or []),
                "description": (p.get("description") or "")[:300], "override_lat": "", "override_lon": "",
            })
    return rows


def write_review(rows, path=REVIEW_CSV):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["project_id", "project_name", "endpoint_name", "best_match", "lat", "lon", "confidence", "flags",
            "candidates", "description", "override_lat", "override_lon"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def endpoint_key(utility, name):
    return utility, normalize(name)
