"""Free-text location -> {lat, lon, label, query, source} via Nominatim. Never Gemini.

At most 1 request/second (global lock). Results cached in memory and in Mongo when connected.
FAKE_GEOCODER=1 uses a small built-in gazetteer (tests and offline demos)."""
import hashlib
import os
import re
import threading
import time

import requests

from services.state import STATE

URL = "https://nominatim.openstreetmap.org/search"
VIEWBOX = "-85.7,35.3,-78.5,30.3"
STATE_ABBR = {"South Carolina": "SC", "Georgia": "GA", "North Carolina": "NC", "Florida": "FL", "Alabama": "AL",
              "Tennessee": "TN"}

_lock = threading.Lock()
_last = [0.0]
_memory = {}

# Same towns as the mock gazetteer, for tests / FAKE_GEOCODER=1 only.
GAZETTEER = {
    "hardeeville": (32.2871, -81.079, "Hardeeville, SC"), "savannah": (32.0809, -81.0912, "Savannah, GA"),
    "okatie": (32.3338, -81.0325, "Okatie, SC"), "bluffton": (32.2371, -80.8604, "Bluffton, SC"),
    "ridgeland": (32.4802, -80.9801, "Ridgeland, SC"), "pooler": (32.1155, -81.247, "Pooler, GA"),
    "rincon": (32.296, -81.2354, "Rincon, GA"), "augusta": (33.4735, -82.0105, "Augusta, GA"),
    "north augusta": (33.5018, -81.9651, "North Augusta, SC"), "evans": (33.5337, -82.1307, "Evans, GA"),
    "charleston": (32.7765, -79.9311, "Charleston, SC"), "jasper": (32.3591, -81.1246, "Jasper County, SC"),
}


def _fake(text):
    t = (text or "").lower()
    key = next((k for k in sorted(GAZETTEER, key=len, reverse=True) if k in t), None)
    if not key:
        return None
    lat, lon, label = GAZETTEER[key]
    return {"lat": lat, "lon": lon, "label": label, "query": text, "source": "gazetteer (test)"}


def _clean_query(text):
    """'Near Hardeeville, SC' -> 'Hardeeville, SC'."""
    q = re.sub(r"^\s*(near|around|by|close to|outside( of)?|in|at)\s+", "", text.strip(), flags=re.I)
    return q.strip(" .")


STREET_WORDS = r"(st|street|rd|road|ave|avenue|dr|drive|hwy|highway|blvd|boulevard|ln|lane|way|pkwy|parkway|ct|court|pl|place|cir|circle|trl|trail|route|i-\d+|us-\d+|sc-\d+|ga-\d+)"
PLACE_FIELDS = ("city", "town", "village", "hamlet", "suburb", "municipality", "county", "neighbourhood", "quarter")


def _place_matches(query, item):
    """The search is limited to the service area, so for a place outside it Nominatim returns the closest thing
    inside it ('Tampa, FL' -> Tampa Drive in Tallahassee). Accept a result only if the place named first in the
    query is in it: for a town, in the result's town/city/county names (not a street that shares the name)."""
    first = re.split(r",", query)[0].strip().lower()
    is_street = bool(re.match(r"^\d+\s", first) or re.search(STREET_WORDS, first))
    first = re.sub(r"^\d+\s+", "", first)
    words = [w for w in re.findall(r"[a-z0-9]+", first) if len(w) > 2 and w not in {"the", "and", "near", "county", "city"}]
    if not words:
        return True
    a = item.get("address") or {}
    if is_street or not a:
        hay = " ".join(str(v) for v in a.values()) + " " + (item.get("display_name") or "")
    else:
        hay = " ".join(str(a.get(k) or "") for k in PLACE_FIELDS) + " " + (item.get("name") if item.get("addresstype") in PLACE_FIELDS else "") 
    hay = hay.lower()
    return all(w in hay for w in words)


def _label(item):
    a = item.get("address") or {}
    town = a.get("city") or a.get("town") or a.get("village") or a.get("hamlet") or a.get("suburb") or a.get("county")
    st = STATE_ABBR.get(a.get("state"), a.get("state"))
    if town and st:
        return f"{town}, {st}"
    return ", ".join((item.get("display_name") or "").split(", ")[:2]) or None


def _cache_get(key):
    if key in _memory:
        return _memory[key]
    if STATE.db is not None:
        doc = STATE.db.geocode_cache.find_one({"key": key})
        if doc:
            _memory[key] = doc.get("result")
            return _memory[key]
    return "MISS"


def _cache_set(key, result):
    _memory[key] = result
    if STATE.db is not None:
        STATE.db.geocode_cache.update_one({"key": key}, {"$set": {"key": key, "result": result}}, upsert=True)


def geocode(text):
    if not text or not text.strip():
        return None
    if os.environ.get("FAKE_GEOCODER") == "1":
        return _fake(text)
    q = _clean_query(text)
    key = hashlib.sha256(q.lower().encode()).hexdigest()
    hit = _cache_get(key)
    # Answers cached before the place check could be a wrong town (e.g. Tampa -> Tallahassee): re-check them.
    if hit and hit != "MISS" and not _place_matches(q, {"display_name": hit.get("label") or ""}):
        hit = "MISS"
    if hit != "MISS":
        return {**hit, "query": text} if hit else None
    email = os.environ.get("NOMINATIM_EMAIL", "")
    headers = {"User-Agent": f"Gridlock-ShellHacks/1.0 ({email})"}
    params = {"format": "json", "limit": 5, "countrycodes": "us", "viewbox": VIEWBOX, "bounded": 1,
              "addressdetails": 1, "q": q}
    with _lock:
        wait = 1.0 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(URL, params=params, headers=headers, timeout=10)
            r.raise_for_status()
            items = r.json()
        except (requests.RequestException, ValueError):
            return None  # not cached: a transient failure should not stick
        finally:
            _last[0] = time.time()
    items = [it for it in items if _place_matches(q, it)]
    if not items:
        _cache_set(key, None)
        return None
    it = items[0]
    result = {"lat": round(float(it["lat"]), 6), "lon": round(float(it["lon"]), 6), "label": _label(it) or q,
              "source": "nominatim"}
    _cache_set(key, result)
    return {**result, "query": text}
