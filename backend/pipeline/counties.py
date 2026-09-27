"""County lookup via the FCC Area API, cached in data/county_cache.json. Offline pipeline only."""
import json
import time
from pathlib import Path

import requests

BACKEND = Path(__file__).resolve().parents[1]
CACHE = BACKEND / "data" / "county_cache.json"
URL = "https://geo.fcc.gov/api/census/area"
SOURCE = "FCC Census Area API (2020 census blocks)"


class CountyLookup:
    def __init__(self, path=CACHE, offline=False):
        self.path = Path(path)
        self.offline = offline
        self.cache = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.dirty = False

    @staticmethod
    def key(lat, lon):
        return f"{lat:.6f},{lon:.6f}"

    def county(self, lat, lon):
        """'Jasper County, SC' or None."""
        if lat is None or lon is None:
            return None
        k = self.key(lat, lon)
        if k in self.cache:
            return self.cache[k]
        if self.offline:
            return None
        val = None
        for attempt in range(2):
            try:
                r = requests.get(URL, params={"lat": lat, "lon": lon, "format": "json"}, timeout=15)
                r.raise_for_status()
                res = r.json().get("results") or []
                if res and res[0].get("county_name"):
                    val = f'{res[0]["county_name"]}, {res[0]["state_code"]}'
                self.cache[k] = val  # cache definitive answers, including "no county" (offshore)
                self.dirty = True
                break
            except (requests.RequestException, ValueError):
                time.sleep(1)
        return val

    def save(self):
        if self.dirty:
            self.path.write_text(json.dumps(self.cache, indent=1, sort_keys=True), newline="\n")
            self.dirty = False
