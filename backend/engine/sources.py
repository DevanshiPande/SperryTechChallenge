"""Sourced constants (config/cost_sources.json). Every number used in cost/traffic estimates comes from here."""
import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "config" / "cost_sources.json"


@lru_cache(maxsize=1)
def all_sources():
    return json.loads(PATH.read_text(encoding="utf-8"))


def get(name):
    return all_sources()[name]


def cite(name, value_used):
    """{name, value_used, url?} entry for a `sources` list; assumptions are not cited here."""
    s = get(name)
    out = {"name": s["source"], "value_used": value_used}
    if s.get("url"):
        out["url"] = s["url"]
    if s.get("verified") is False:
        out["verified"] = False
    return out


def by_voltage(table_name, kv):
    """Value for a voltage class; nearest listed class when the exact one is missing (None if no voltage)."""
    if kv is None:
        return None, None
    t = {int(k): v for k, v in get(table_name).items() if k.isdigit() and v is not None}
    if not t:
        return None, None
    k = min(t, key=lambda x: (abs(x - int(kv)), x))
    return t[k], k
