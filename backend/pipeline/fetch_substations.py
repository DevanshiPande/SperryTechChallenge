"""
Gridlock: pull substations from OpenStreetMap and match them to project endpoint names.

Based on Sperry's Overpass snippet, with four changes:
  1. Only power=substation (their query pulled every power feature, including thousands of towers and poles).
  2. No operator filter by default. Many substations in OSM have no operator tag, so filtering by operator
     silently drops real matches. We keep the operator tag and use it as a confidence signal instead.
  3. Results are cached to disk, so Overpass is hit once, not on every run (it rate-limits).
  4. A name matcher that turns "THURMOND DAM (USA) #5" into a coordinate with a confidence level.

Setup:   pip install requests rapidfuzz
Run:     python fetch_substations.py            (fetches once, then uses the cache)
         python fetch_substations.py --refresh  (force a new download)
"""
import json, os, re, sys, time
import requests
from rapidfuzz import fuzz, process

# Put a real contact email here. Overpass etiquette, and it helps avoid being blocked.
HEADERS = {"User-Agent": f"GridLockChallenge-ShellHacks/1.0 ({os.environ.get('NOMINATIM_EMAIL', 'gridlock@example.com')})"}
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

# (south, west, north, east). SC also covers DESC's plant in Martinez, GA.
BBOXES = {
    "SC": "32.0,-83.5,35.3,-78.5",
    "GA": "30.3,-85.7,35.1,-80.8",
}
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "osm_cache")

UTILITY_OPERATORS = {
    "DESC": r"dominion|south carolina electric|sce&g",
    "GPC": r"georgia power|southern company|georgia transmission|meag",
}


def fetch_substations(state, bbox, refresh=False, timeout=180):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"substations_{state}.geojson")
    if os.path.exists(path) and not refresh:
        return json.load(open(path))

    query = f'[out:json][timeout:{timeout}][bbox:{bbox}];nwr["power"="substation"];out center tags;'
    for ep in ENDPOINTS:
        try:
            print(f"[{state}] querying {ep} ...")
            r = requests.get(ep, params={"data": query}, headers=HEADERS, timeout=timeout + 15)
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            print(f"  failed: {e}")
            time.sleep(3)
    else:
        raise RuntimeError(f"All Overpass endpoints failed for {state}")

    features = []
    for el in data.get("elements", []):
        lat, lon = (el.get("lat"), el.get("lon")) if "lat" in el else (el.get("center", {}).get("lat"), el.get("center", {}).get("lon"))
        if lat is None:
            continue
        tags = el.get("tags", {})
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "osm_id": f'{el["type"]}/{el["id"]}',
                "name": tags.get("name"),
                "operator": tags.get("operator"),
                "voltage": tags.get("voltage"),
                "state": state,
                "tags": tags,
            },
        })
    fc = {"type": "FeatureCollection", "features": features}
    json.dump(fc, open(path, "w"), indent=1)
    named = sum(1 for f in features if f["properties"]["name"])
    print(f"[{state}] saved {len(features)} substations ({named} named) -> {path}")
    return fc


# ---------- name matching ----------
NOISE = r"\b(sub|substation|primary|pri|switching|station|switchyard|dam|plant|steam|tap|sav|gtc|meag|usa|kv|\d+\s*kv)\b"

ABBREV = {"ft": "fort", "mt": "mount", "n": "north", "s": "south", "e": "east", "w": "west", "st": "saint", "cr": "creek", "jct": "junction"}

def normalize(name):
    """'THURMOND DAM (USA) #5' -> 'thurmond'   'Okatie Sub' -> 'okatie'"""
    s = (name or "").lower()
    s = re.sub(r"^[a-z]{2,4}:\s*", "", s)   # prefixes like 'SAV:' or 'GTC:'
    s = re.sub(r"\(.*?\)", " ", s)          # anything in parentheses
    s = re.sub(r"#\s*\d+", " ", s)          # '#5'
    s = re.sub(NOISE, " ", s)
    s = re.sub(r"[^a-z ]", " ", s)
    words = [ABBREV.get(w, w) for w in s.split()]
    return " ".join(words)


import csv, math

def dist_km(a_lat, a_lon, b_lat, b_lon):
    r = math.radians
    h = math.sin(r(b_lat - a_lat) / 2) ** 2 + math.cos(r(a_lat)) * math.cos(r(b_lat)) * math.sin(r(b_lon - a_lon) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))

# Region hints. "SAV:" / "(SAV)" in Georgia Power names means the Savannah area.
# Zone anchors come from the examples in Sperry's files (219 = Savannah, 215 = Augusta). Add others once confirmed.
REGIONS = {"SAV": (32.08, -81.10, "Savannah area"), "AUG": (33.47, -82.01, "Augusta area")}
ZONE_ANCHORS = {219: REGIONS["SAV"], 215: REGIONS["AUG"]}
REGION_KM = 60        # a project's endpoints must be within this distance of its region anchor
SIBLING_KM = 80       # the two ends of one line are rarely farther apart than this
AMBIGUOUS_KM = 20     # same-name candidates farther apart than this are different substations


def region_hint(project_name, zone=None):
    n = (project_name or "").upper()
    if re.search(r"(^SAV:|\(SAV\))", n):
        return REGIONS["SAV"]
    if zone is not None and int(zone) in ZONE_ANCHORS:
        return ZONE_ANCHORS[int(zone)]
    return None


def load_overrides(path=os.path.join(os.path.dirname(CACHE_DIR), "overrides.csv")):
    """utility,endpoint_name,lat,lon,source,note  ->  {(utility, normalized_name): record}"""
    out = {}
    if os.path.exists(path):
        for row in csv.DictReader(open(path, encoding="utf-8")):
            out[(row["utility"].strip(), normalize(row["endpoint_name"]))] = row
    return out


def _not_found(name, why):
    return {"name": name, "lat": None, "lon": None, "confidence": "not_found", "source": None, "flags": [why]}


def match_endpoint(endpoint_name, utility, features, anchor=None, max_km=REGION_KM, overrides=None, min_score=85):
    """
    Match one endpoint name to an OSM substation.
    anchor: (lat, lon, label) or None. Candidates farther than max_km from the anchor are rejected.
    confidence:
      high   = strong name match, operator matches, and location is consistent (anchor) or unambiguous
      medium = strong name match but operator missing, or no anchor to confirm location
      low    = weak name match, or several same-name substations and nothing to pick between them
    """
    target = normalize(endpoint_name)
    if not target:
        return _not_found(endpoint_name, "EMPTY_NAME")
    if overrides and (utility, target) in overrides:
        o = overrides[(utility, target)]
        return {"name": endpoint_name, "lat": float(o["lat"]), "lon": float(o["lon"]), "confidence": "high",
                "source": o.get("source") or "manual review", "flags": ["MANUAL_OVERRIDE"]}

    named = [f for f in features if f["properties"]["name"]]
    choices = {i: normalize(f["properties"]["name"]) for i, f in enumerate(named)}
    hits = [h for h in process.extract(target, choices, scorer=fuzz.token_set_ratio, limit=25) if h[1] >= 70]
    if not hits:
        return _not_found(endpoint_name, "NO_NAME_MATCH")

    op_re = re.compile(UTILITY_OPERATORS[utility], re.I)
    cands = []
    for _, score, idx in hits:
        f = named[idx]
        lon, lat = f["geometry"]["coordinates"]
        d = dist_km(anchor[0], anchor[1], lat, lon) if anchor else None
        cands.append({"f": f, "lat": lat, "lon": lon, "score": score, "dist": d,
                      "op_ok": bool(op_re.search(f["properties"]["operator"] or ""))})

    flags = []
    if anchor:
        near = [c for c in cands if c["dist"] <= max_km]
        if not near:
            far = min(cands, key=lambda c: c["dist"])
            return {**_not_found(endpoint_name, "ONLY_FAR_MATCHES"),
                    "candidates": [f'{c["f"]["properties"]["name"]} ({c["dist"]:.0f} km from {anchor[2]})' for c in sorted(cands, key=lambda c: c["dist"])[:3]]}
        cands = near

    top = max(c["score"] for c in cands)
    best_pool = [c for c in cands if c["score"] >= top - 5]
    # Same-name substations far apart = genuinely different places.
    spread = max((dist_km(a["lat"], a["lon"], b["lat"], b["lon"]) for a in best_pool for b in best_pool), default=0)
    ambiguous = spread > AMBIGUOUS_KM and not anchor
    if ambiguous:
        flags.append("AMBIGUOUS_NAME")

    best = max(best_pool, key=lambda c: (c["score"] + (8 if c["op_ok"] else 0) - ((c["dist"] or 0) / 10)))
    if best["score"] < min_score or ambiguous:
        conf = "low"
    elif best["op_ok"] and (anchor or spread <= AMBIGUOUS_KM):
        conf = "high"
    else:
        conf = "medium"
    f = best["f"]
    return {
        "name": endpoint_name, "lat": round(best["lat"], 6), "lon": round(best["lon"], 6), "confidence": conf,
        "source": f'OSM {f["properties"]["osm_id"]} "{f["properties"]["name"]}"', "osm_id": f["properties"]["osm_id"],
        "score": best["score"], "flags": flags,
        "anchor": anchor[2] if anchor else None, "dist_to_anchor_km": round(best["dist"], 1) if best["dist"] is not None else None,
        "candidates": [f'{c["f"]["properties"]["name"]} @ {c["lat"]:.3f},{c["lon"]:.3f}' for c in sorted(cands, key=lambda c: -c["score"])[:3]],
    }


def match_project(project_name, endpoint_names, utility, features, zone=None, overrides=None):
    """
    Match both endpoints of one project, using geography:
      1. Region hint (SAV prefix, known zones) constrains both endpoints.
      2. If one endpoint is confidently located, the other must be within SIBLING_KM of it.
    """
    region = region_hint(project_name, zone)
    results = [match_endpoint(n, utility, features, anchor=region, overrides=overrides) for n in endpoint_names]
    if len(results) == 2:
        for i, j in ((0, 1), (1, 0)):
            a, b = results[i], results[j]
            if a["confidence"] in ("high", "medium") and b["confidence"] in ("low", "not_found"):
                sib = (a["lat"], a["lon"], f'{a["name"]} (other end of this line)')
                retry = match_endpoint(endpoint_names[j], utility, features, anchor=sib, max_km=SIBLING_KM, overrides=overrides)
                if retry["confidence"] != "not_found":
                    retry["flags"] = retry.get("flags", []) + ["LOCATED_VIA_SIBLING"]
                    results[j] = retry
        a, b = results
        if a["lat"] is not None and b["lat"] is not None:
            d = dist_km(a["lat"], a["lon"], b["lat"], b["lon"])
            if d > 150:
                for r in results:
                    r["flags"] = r.get("flags", []) + [f"LINE_TOO_LONG_{d:.0f}KM"]
                    if r["confidence"] == "high":
                        r["confidence"] = "medium"
    return results


if __name__ == "__main__":
    refresh = "--refresh" in sys.argv
    feats = {st: fetch_substations(st, bb, refresh)["features"] for st, bb in BBOXES.items()}
    everything = feats["SC"] + feats["GA"]
    overrides = load_overrides()

    # Smoke test on Sperry's answer-key projects. Expected coordinates are Sperry's.
    tests = [
        ("DESC", "Jasper - Okatie 230 kV #2: Construct", ["Jasper Sub", "Okatie Sub"], None),
        ("DESC", "Okatie-Bluffton 115 kV: Rebuild", ["Okatie Sub", "Bluffton Sub"], None),
        ("GPC", "EVANS PRIMARY - THURMOND DAM (USA) #5 115KV REBUILD", ["EVANS PRIMARY", "THURMOND DAM #5"], 215),
        ("GPC", "SAV: MCINTOSH - PURRYSBURG 230KV REACTORS", ["MCINTOSH", "PURRYSBURG"], 219),
        ("GPC", "SAV: GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD", ["GOSHEN (SAV)", "MCINTOSH"], 219),
    ]
    for util, pname, eps, zone in tests:
        print(f"\n{util} {pname}")
        for m in match_project(pname, eps, util, everything, zone=zone, overrides=overrides):
            print(f"   {m['name']:18} -> {m['confidence']:9} {m['lat']}, {m['lon']}  {m.get('source')}  flags={m.get('flags')}  "
                  f"anchor={m.get('anchor')} {m.get('dist_to_anchor_km')}km  alts={m.get('candidates')}")
