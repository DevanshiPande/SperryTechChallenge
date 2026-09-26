"""Offline: download major roads (OSM Overpass) and traffic counts (SCDOT / GDOT ArcGIS) for the GA/SC border study area.

Writes data/traffic/roads.geojson and data/traffic/aadt_points.geojson (committed; the API never calls these services).
Run from backend/:  python -m pipeline.fetch_traffic [--roads] [--aadt]
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND / "data" / "traffic"
BOX = {"south": 31.8, "west": -83.5, "north": 34.9, "east": -80.5}  # study area (spec U3.1)
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
HEADERS = {"User-Agent": f"Gridlock-ShellHacks/1.0 ({os.environ.get('NOMINATIM_EMAIL', 'gridlock@example.com')})"}
CLASSES = "motorway|trunk|primary|secondary|tertiary"


def fetch_roads():
    b = BOX
    q = (f'[out:json][timeout:600][bbox:{b["south"]},{b["west"]},{b["north"]},{b["east"]}];'
         f'way["highway"~"^({CLASSES})$"];out tags geom;')
    data = None
    for ep in OVERPASS:
        try:
            print(f"roads: querying {ep} (this can take a few minutes)")
            r = requests.post(ep, data={"data": q}, headers=HEADERS, timeout=900)
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:  # try the mirror
            print("  failed:", e)
            time.sleep(5)
    if data is None:
        raise RuntimeError("Overpass failed")
    feats = []
    for el in data.get("elements", []):
        g = el.get("geometry") or []
        if len(g) < 2:
            continue
        t = el.get("tags", {})
        feats.append({"type": "Feature",
                      "geometry": {"type": "LineString", "coordinates": [[round(p["lon"], 5), round(p["lat"], 5)] for p in g]},
                      "properties": {"osm_id": el["id"], "name": t.get("name"), "ref": t.get("ref"), "highway": t.get("highway"),
                                     "lanes": t.get("lanes"), "oneway": t.get("oneway"), "maxspeed": t.get("maxspeed")}})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "roads.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")),
                                       encoding="utf-8", newline="\n")
    print(f"roads: {len(feats)} ways -> {OUT / 'roads.geojson'}")


SCDOT = {  # SCDOT's own ArcGIS account (gallowayra_SCDOT), 2025 statewide count stations
    "url": "https://services1.arcgis.com/VaY7cY9pvUYUP1Lf/arcgis/rest/services/2025_Statewide_Traffic_Points/FeatureServer/0",
    "source": "SCDOT 2025 statewide traffic counts"}
GDOT = {  # newest public GDOT station layer we could reach (no route field; matched by proximity)
    "url": "https://services5.arcgis.com/buITjRsK0rZsAXbQ/arcgis/rest/services/GDOT_AADT_and_TruckPct_2008to2017/FeatureServer/0",
    "source": "GDOT traffic counts (2017 AADT)"}


def _query_all(url, fields):
    b = BOX
    env = f'{b["west"]},{b["south"]},{b["east"]},{b["north"]}'
    out, offset = [], 0
    while True:
        r = requests.get(url + "/query", params={
            "where": "1=1", "outFields": fields, "geometry": env, "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outSR": 4326, "resultOffset": offset, "resultRecordCount": 2000,
            "f": "json"}, headers=HEADERS, timeout=120)
        r.raise_for_status()
        feats = r.json().get("features", [])
        out += feats
        if len(feats) < 2000:
            return out
        offset += len(feats)


def sc_ref(a):
    t, n = (a.get("RouteTypeN") or "").lower(), a.get("RouteNumbe")
    if not n:
        return None
    if "interstate" in t:
        return f"I-{n}"
    if t.startswith("us"):
        return f"US-{n}"
    if t.startswith("sc"):
        return f"SC-{n}"
    return None  # secondary / local roads have county-level numbers that OSM does not carry


def fetch_aadt():
    feats = []
    for f in _query_all(SCDOT["url"], "RouteTypeN,RouteNumbe,FactoredAA,FactoredA1"):
        a, g = f["attributes"], f.get("geometry") or {}
        if a.get("FactoredAA") and "x" in g:
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(g["x"], 6), round(g["y"], 6)]},
                          "properties": {"aadt": a["FactoredAA"], "year": a.get("FactoredA1"), "route": sc_ref(a),
                                         "route_type": a.get("RouteTypeN"), "state": "SC", "source": SCDOT["source"]}})
    n_sc = len(feats)
    for f in _query_all(GDOT["url"], "Station_ID,Functional_Class,AADT_2017"):
        a, g = f["attributes"], f.get("geometry") or {}
        if a.get("AADT_2017") and "x" in g:
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(g["x"], 6), round(g["y"], 6)]},
                          "properties": {"aadt": a["AADT_2017"], "year": 2017, "route": None,
                                         "route_type": a.get("Functional_Class"), "state": "GA", "source": GDOT["source"]}})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "aadt_points.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                                                        separators=(",", ":")), encoding="utf-8", newline="\n")
    print(f"aadt: {n_sc} SC + {len(feats) - n_sc} GA count points -> {OUT / 'aadt_points.geojson'}")


if __name__ == "__main__":
    if "--roads" in sys.argv or len(sys.argv) == 1:
        fetch_roads()
    if "--aadt" in sys.argv or len(sys.argv) == 1:
        fetch_aadt()
