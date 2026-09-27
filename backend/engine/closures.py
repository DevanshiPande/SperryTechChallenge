"""Lane-closure conflicts between user projects. Pure functions."""
import re

from engine import geo, windows

CONFLICT_KM = 16

_ROAD_RE = re.compile(r"\b(US|I|SC|GA|SR)\s*-?\s*(\d+[A-Z]?)\b", re.I)


def normalize_road(text):
    """'US 17' / 'us17' / 'US-17' -> 'US-17'. Unknown formats are uppercased and trimmed."""
    if not text:
        return None
    m = _ROAD_RE.search(str(text))
    if m:
        return f"{m.group(1).upper()}-{m.group(2).upper()}"
    return re.sub(r"\s+", " ", str(text)).strip().upper() or None


def normalize_roads(value):
    """Accepts a string (comma/semicolon separated) or list; returns a list of normalized IDs."""
    if not value:
        return []
    items = value if isinstance(value, list) else re.split(r"[;,/]|\band\b", str(value))
    out = []
    for it in items:
        found = [f"{a.upper()}-{b.upper()}" for a, b in _ROAD_RE.findall(str(it))]
        for r in found or ([normalize_road(it)] if str(it).strip() else []):
            if r and r not in out:
                out.append(r)
    return out


def _parse_clock(s):
    """'21:00', '9 PM', '9:30pm' -> minutes after midnight, or None."""
    s = s.strip().lower().replace(".", "")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", s)
    if not m:
        return None
    h, mnt, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and h != 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if h > 24 or mnt > 59:
        return None
    return (h % 24) * 60 + mnt


def parse_hours(text):
    """'21:00-05:00' or '9 PM – 5 AM' -> list of (start, end) minute intervals within one day, or None."""
    if not text:
        return None
    parts = re.split(r"\s*(?:-|–|—|to)\s*", str(text).strip(), maxsplit=1)
    if len(parts) != 2:
        return None
    a, b = _parse_clock(parts[0]), _parse_clock(parts[1])
    if a is None or b is None:
        return None
    if a == b:
        return [(0, 1440)]
    if a < b:
        return [(a, b)]
    return [(a, 1440), (0, b)]  # crosses midnight


def hours_overlap(h1, h2):
    """True when two work-hour strings overlap. Missing or unparseable hours are assumed to overlap."""
    i1, i2 = parse_hours(h1), parse_hours(h2)
    if i1 is None or i2 is None:
        return True
    return any(max(a0, b0) < min(a1, b1) for a0, a1 in i1 for b0, b1 in i2)


def has_closure_data(project):
    return bool(normalize_roads(project.get("roads_affected")))


def conflicts(proposed, others):
    """proposed/others: dicts with roads_affected, work_hours, construction_window, center (and id/short_name).
    Returns conflict items for every other project that shares a road, dates, hours and is within 16 km."""
    roads = set(normalize_roads(proposed.get("roads_affected")))
    w = proposed.get("construction_window")
    c = proposed.get("center")
    if not roads or not w or not c:
        return []
    out = []
    for p in others:
        if p.get("id") and p.get("id") == proposed.get("id"):
            continue
        common = roads & set(normalize_roads(p.get("roads_affected")))
        pw, pc = p.get("construction_window"), p.get("center")
        if not common or not pw or not pc:
            continue
        if windows.overlap_days(w, pw) < 1:
            continue
        if not hours_overlap(proposed.get("work_hours"), p.get("work_hours")):
            continue
        if geo.haversine_km(c, pc) > CONFLICT_KM:
            continue
        start = max(windows.to_date(w["start"]), windows.to_date(pw["start"]))
        end = min(windows.to_date(w["end"]), windows.to_date(pw["end"]))
        out.append({
            "project_id": p.get("id"),
            "short_name": p.get("short_name") or p.get("name"),
            "road": sorted(common)[0],
            "overlap_start": start.isoformat(),
            "overlap_end": end.isoformat(),
            "hours": p.get("work_hours"),
            "severity": "requires_review",
        })
    return out
