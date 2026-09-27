"""Distances, closest points and proximity tiers. Pure functions, no I/O."""
import math
from functools import lru_cache

from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, transform

EARTH_RADIUS_MI = 3958.8
SHARED_ENDPOINT_KM = 0.05

TIERS = [  # (code, max_km, inclusive, label, explanation)
    ("crossing", 0.05, True, "Touching / crossing", "Touching/crossing: must coordinate outages and crossing structures"),
    ("shared_land", 1.6, False, "Under 1.6 km", "Under 1.6 km: can share right-of-way, access roads, permits"),
    ("shared_site", 8, False, "Under 8 km", "Under 8 km: can share laydown yards and deliveries"),
    ("shared_crews", 40, False, "Under 40 km", "Under 40 km: can share crews and equipment"),
]
TIER_EXPLANATIONS = {code: expl for code, _, _, _, expl in TIERS}


@lru_cache(maxsize=1)
def _to_utm():
    return Transformer.from_crs("EPSG:4326", "EPSG:32617", always_xy=True)


@lru_cache(maxsize=1)
def _to_wgs():
    return Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True)


def haversine_mi(a, b):
    """a, b: {lat, lon}. Unrounded miles."""
    r = math.radians
    dlat, dlon = r(b["lat"] - a["lat"]), r(b["lon"] - a["lon"])
    h = math.sin(dlat / 2) ** 2 + math.cos(r(a["lat"])) * math.cos(r(b["lat"])) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def haversine_km(a, b):
    return haversine_mi(a, b) * 1.609344


def center_distance_mi(a, b):
    """Sperry's official metric: haversine between centers, 2 decimals."""
    return round(haversine_mi(a, b), 2)


def located(endpoints):
    return [e for e in (endpoints or []) if e.get("lat") is not None and e.get("lon") is not None]


def center_of(endpoints):
    pts = located(endpoints)
    if not pts:
        return None
    return {"lat": round(sum(p["lat"] for p in pts) / len(pts), 6), "lon": round(sum(p["lon"] for p in pts) / len(pts), 6)}


def wgs_geometry(endpoints):
    """shapely geometry in lon/lat from located endpoints, or None."""
    pts = located(endpoints)
    if not pts:
        return None
    if len(pts) == 1:
        return Point(pts[0]["lon"], pts[0]["lat"])
    return LineString([(p["lon"], p["lat"]) for p in pts[:2]])


def utm_geometry(endpoints):
    g = wgs_geometry(endpoints)
    return transform(_to_utm().transform, g) if g is not None else None


def geojson(endpoints):
    pts = located(endpoints)
    if not pts:
        return None
    if len(pts) == 1:
        return {"type": "Point", "coordinates": [pts[0]["lon"], pts[0]["lat"]]}
    return {"type": "LineString", "coordinates": [[p["lon"], p["lat"]] for p in pts[:2]]}


def km_to_mi(km):
    return None if km is None else round(km / 1.609344, 2)


def closest(endpoints_a, endpoints_b):
    """Closest distance (km, 2 decimals) and closest points ({a:{lat,lon}, b:{lat,lon}}) between two projects."""
    ga, gb = utm_geometry(endpoints_a), utm_geometry(endpoints_b)
    if ga is None or gb is None:
        return None, None
    km = round(ga.distance(gb) / 1000, 2)
    pa, pb = nearest_points(ga, gb)
    inv = _to_wgs().transform
    (lon_a, lat_a), (lon_b, lat_b) = inv(pa.x, pa.y), inv(pb.x, pb.y)
    return km, {"a": {"lat": round(lat_a, 6), "lon": round(lon_a, 6)}, "b": {"lat": round(lat_b, 6), "lon": round(lon_b, 6)}}


def tier_for(km):
    """(tier, explanation) or (None, None) beyond 40 km."""
    if km is None:
        return None, None
    for code, max_km, inclusive, _, expl in TIERS:
        if (km <= max_km) if inclusive else (km < max_km):
            return code, expl
    return None, None


def shared_endpoint(endpoints_a, endpoints_b):
    return any(haversine_km(a, b) <= SHARED_ENDPOINT_KM for a in located(endpoints_a) for b in located(endpoints_b))


def shared_length_m(endpoints_a, endpoints_b, buffer_m=1600):
    """Length of line A inside a buffer around line B, meters (UTM)."""
    ga, gb = utm_geometry(endpoints_a), utm_geometry(endpoints_b)
    if not isinstance(ga, LineString) or not isinstance(gb, LineString):
        return None
    return ga.intersection(gb.buffer(buffer_m)).length
