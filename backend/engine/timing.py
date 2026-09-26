"""'Best time to work' for a new project, in plain English (spec update 2, contract flow).

Code decides everything: which hours cause the least traffic trouble on the roads the work crosses, and which months
have the least other construction nearby. The sentences are templates filled from those results, so every statement is
backed by the traffic model and the project data."""
from calendar import monthrange
from datetime import date

from engine import geo, traffic as T, windows

DAY_START = 7          # a normal day shift starts at 7 AM
QUIET_DELAY = 20       # vehicle-hours: below this, a lane closure causes no real delay
NEAR_KM = 5            # another project's road work this close to ours counts as "the same area of road"
RADIUS_MI = 25


def clock(h):
    h %= 24
    return "midnight" if h == 0 else "noon" if h == 12 else f"{h} AM" if h < 12 else f"{h - 12} PM"


def window_label(start, hours):
    return f"{clock(start)} to {clock(start + hours)}"


def busy_words(aadt):
    if aadt >= 40000:
        return "one of the busiest roads in the area"
    if aadt >= 15000:
        return "a busy road"
    if aadt >= 5000:
        return "a moderately busy road"
    return "a quiet road"


def impact_words(delay_veh_hours):
    if delay_veh_hours < QUIET_DELAY:
        return "hardly any delay"
    if delay_veh_hours < 300:
        return "some slowdowns"
    if delay_veh_hours < 3000:
        return "long backups"
    return "very long backups, with traffic stopped for hours"


def road_name(x):
    return x.get("road_ref") or x.get("road_name") or "an unnamed road"


def _delay(x, start):
    return T.closure_delay(x["aadt"], x["lanes"], x["oneway"], x["closure_type"], start, x["est_closure_hours"])[0]


def _months(w):
    s, e = windows.to_date(w["start"]), windows.to_date(w["end"])
    y, m = s.year, s.month
    out = []
    while (y, m) <= (e.year, e.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _month_window(y, m):
    return {"start": date(y, m, 1).isoformat(), "end": date(y, m, monthrange(y, m)[1]).isoformat()}


def _month_label(y, m):
    return date(y, m, 1).strftime("%b %Y")


def _ranges(months):
    """[(y,m), ...] -> contiguous runs as labels, e.g. 'Jun–Aug 2027'."""
    runs, cur = [], []
    for ym in months:
        if cur and (ym[0] * 12 + ym[1]) != (cur[-1][0] * 12 + cur[-1][1]) + 1:
            runs.append(cur)
            cur = []
        cur.append(ym)
    if cur:
        runs.append(cur)
    labels = []
    for r in runs:
        a, b = r[0], r[-1]
        if a == b:
            labels.append(_month_label(*a))
        elif a[0] == b[0]:
            labels.append(f"{date(a[0], a[1], 1):%b}–{date(b[0], b[1], 1):%b %Y}")
        else:
            labels.append(f"{_month_label(*a)} – {_month_label(*b)}")
    return runs, labels


def _join(names):
    names = list(dict.fromkeys(names))
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def best_time(project, crossings, others, crossings_of, today=None):
    """project: the new work (with construction_window, center). crossings: its road crossings (services.traffic).
    others: all other projects. crossings_of: callable project -> its crossings. Returns the recommendation dict."""
    today = today or date.today()
    w = project["construction_window"]
    reasons = []

    # ---- 1. hours of the day
    xs = crossings
    by_label = {}
    for x in xs:  # one line per road, keep its busiest crossing
        k = road_name(x)
        if k not in by_label or x["aadt"] > by_label[k]["aadt"]:
            by_label[k] = x
    roads = sorted(by_label.values(), key=lambda x: -x["aadt"])
    hours_rec = None
    if not xs:
        headline_hours = "Your route doesn't cross any major road, so normal daytime hours are fine."
    else:
        hrs = max(x["est_closure_hours"] for x in xs)
        total = {s: sum(_delay(x, s) for x in xs) for s in range(24)}
        if total[DAY_START] < QUIET_DELAY:
            start = DAY_START
            headline_hours = "Daytime work is fine: the roads you cross are quiet enough that a lane closure won't cause real delays."
        else:
            start = min(total, key=lambda s: (total[s], s))
            headline_hours = f"Do the road-crossing work at night, {window_label(start, hrs)}."
        hours_rec = {"start_hour": start, "hours": hrs, "label": window_label(start, hrs)}
        busy = [x for x in roads if _delay(x, DAY_START) >= QUIET_DELAY]
        quiet = [x for x in roads if _delay(x, DAY_START) < QUIET_DELAY]
        for x in busy[:3]:
            best = min(range(24), key=lambda s: (_delay(x, s), s))
            reasons.append(f"{road_name(x)} is {busy_words(x['aadt'])}. Closing a lane there during the day would cause "
                           f"{impact_words(_delay(x, DAY_START))}; from {window_label(best, x['est_closure_hours'])} "
                           f"traffic keeps moving.")
        if quiet:
            reasons.append(f"{_join([road_name(x) for x in quiet[:5]])} {'is' if len(quiet) == 1 else 'are'} quiet enough "
                           f"to work on at any time of day.")

    # ---- 2. months: other construction within 25 miles during this window
    c = project.get("center")
    nearby = []
    for o in others:
        ow = o.get("construction_window")
        if o["id"] == project["id"] or not o.get("center") or not ow or not c:
            continue
        if geo.haversine_mi(c, o["center"]) >= RADIUS_MI or windows.overlap_days(w, ow) < 1:
            continue
        mine_pts = [x["point"] for x in xs] or [c]
        theirs = crossings_of(o)
        shared = [t for t in theirs if any(road_name(t) == road_name(x) for x in xs)
                  or any(geo.haversine_km(t["point"], p) <= NEAR_KM for p in mine_pts)]
        nearby.append({"project": o, "window": ow, "shared_roads": sorted({road_name(t) for t in shared})})

    months = [ym for ym in _months(w) if date(*ym, monthrange(*ym)[1]) >= today] or _months(w)
    load = {}
    for ym in months:
        mw = _month_window(*ym)
        active = [n for n in nearby if windows.overlap_days(mw, n["window"]) >= 0 and
                  windows.to_date(n["window"]["start"]) <= windows.to_date(mw["end"]) and
                  windows.to_date(n["window"]["end"]) >= windows.to_date(mw["start"])]
        load[ym] = (sum(3 if n["shared_roads"] else 1 for n in active), active)
    best_months, best_labels = [], []
    if not nearby:
        headline_months = "No other construction nearby overlaps your dates, so any month in your schedule works."
    else:
        low = min(v[0] for v in load.values())
        best_months = [ym for ym in months if load[ym][0] == low]
        _, best_labels = _ranges(best_months)
        busiest = max(months, key=lambda ym: load[ym][0])
        if low == load[busiest][0]:
            headline_months = "Other construction nearby runs through your whole schedule, so the month doesn't change much."
        else:
            headline_months = f"Best months for road work: {_join(best_labels)}."
        road_sharers = [n for n in nearby if n["shared_roads"]]
        for n in road_sharers[:3]:
            p = n["project"]
            _, lab = _ranges([ym for ym in _months(n["window"]) if ym in load])
            reasons.append(f"{p.get('short_name') or p['name']} ({p.get('utility_name')}) will also be working on "
                           f"{_join(n['shared_roads'])} during {_join(lab) if lab else 'part of your schedule'}. Avoid those "
                           f"months for that road, or agree on one shared closure with them so drivers are only "
                           f"disrupted once.")
        others_only = [n for n in nearby if not n["shared_roads"]]
        if others_only:
            names = [n["project"].get("short_name") or n["project"]["name"] for n in others_only[:3]]
            listed = (", ".join(names) + f" and {len(others_only) - 3} more") if len(others_only) > 3 else _join(names)
            reasons.append(f"{listed} {'is' if len(others_only) == 1 else 'are'} also under construction within "
                           f"25 miles during your schedule, which adds trucks and crews to the area's roads.")

    return {"headline": f"{headline_hours} {headline_months}".strip(), "best_hours": hours_rec,
            "best_months": best_labels, "reasons": reasons,
            "nearby_active": [{"project_id": n["project"]["id"], "short_name": n["project"].get("short_name"),
                               "window": n["window"], "shared_roads": n["shared_roads"]} for n in nearby],
            "basis": "Road traffic counts (SCDOT/GDOT, else road-class estimates), a work-zone queue model, and the "
                     "construction windows of every planned project within 25 miles."}
