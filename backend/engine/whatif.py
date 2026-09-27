"""What-if: nearby projects and a schedule-shift suggestion for a proposed project. Nothing is saved.
Ported from contract/mock-server.js."""
from datetime import date

from engine import closures, geo, windows
from engine.overlaps import THRESHOLD_MI, is_user

CLOSURE_NOTE_NONE = "No public road-closure data is connected. Closure conflicts are not evaluated."
CLOSURE_NOTE_USER = ("Closure conflicts are checked only against user-submitted projects that list affected roads. "
                     "Public utility filings have no road-closure data.")


def nearby(proposed_endpoints, window, projects, utility=None):
    center = geo.center_of(proposed_endpoints)
    found = []
    for p in projects:
        if (utility and p.get("utility") == utility) or not p.get("center"):
            continue
        mi = geo.center_distance_mi(center, p["center"])
        km, _ = geo.closest(proposed_endpoints, p["endpoints"])
        edge_mi = geo.km_to_mi(km)
        edge_mi = edge_mi if edge_mi is not None else mi
        if min(edge_mi, mi) >= THRESHOLD_MI:
            continue
        tier, _ = geo.tier_for(km)
        found.append({
            "project_id": p["id"],
            "short_name": p.get("short_name"),
            "name": p["name"],
            "utility": p.get("utility"),
            "utility_name": p.get("utility_name"),
            "construction_window": p.get("construction_window"),
            "center_distance_mi": mi,
            "closest_distance_mi": edge_mi,
            "closest_distance_km": km,
            "tier": tier,
            "window_overlap_months": windows.overlap_months(window, p.get("construction_window")),
        })
    found.sort(key=lambda f: (f["closest_distance_mi"], f["project_id"]))
    return center, found


def suggest_shift(window, found, max_shift_months=24, today=None):
    today = (today or date.today()).isoformat()

    def total(win):
        return sum(windows.overlap_months(win, f["construction_window"]) for f in found)

    before = total(window)
    best_shift, best_months = 0, before
    for m in range(-max_shift_months, max_shift_months + 1):
        win = {"start": windows.add_months(window["start"], m), "end": windows.add_months(window["end"], m)}
        if m != 0 and win["start"] < today:
            continue  # never suggest starting in the past
        t = total(win)
        if t > best_months or (t == best_months and abs(m) < abs(best_shift)):
            best_shift, best_months = m, t

    if not found:
        explanation = "No projects from the other utility are within 25 miles, so no shift is needed."
    elif best_shift == 0:
        explanation = ("The current window already gives the most shared construction time with nearby projects."
                       if best_months > 0 else
                       "Nearby projects finish before this one could start, so no future shift creates shared "
                       "construction time. Coordinate on staging yards and permits instead.")
    else:
        explanation = (f"Moving the window {abs(best_shift)} months {'earlier' if best_shift < 0 else 'later'} "
                       f"increases shared construction time with nearby projects from {before} to {best_months} "
                       f"months, so crews and equipment can be shared.")
    return {
        "shift_months": best_shift,
        "suggested_window": {"start": windows.add_months(window["start"], best_shift),
                             "end": windows.add_months(window["end"], best_shift)},
        "window_overlap_months_before": before,
        "window_overlap_months_after": best_months,
        "explanation": explanation,
    }


def whatif(name, endpoints, window, projects, utility=None, voltage_kv=None, max_shift_months=24,
           geocoded=None, roads_affected=None, work_hours=None, today=None):
    center, found = nearby(endpoints, window, projects, utility)
    user_projects = [p for p in projects if is_user(p)]
    data_available = any(closures.has_closure_data(p) for p in user_projects)
    proposed_for_closures = {"roads_affected": roads_affected, "work_hours": work_hours,
                             "construction_window": window, "center": center}
    return {
        "proposed": {"name": name, "utility": utility, "voltage_kv": voltage_kv, "endpoints": endpoints,
                     "construction_window": {"start": window["start"], "end": window["end"]},
                     "center": center, "geocoded": geocoded},
        "overlaps": found,
        "closure_conflicts": closures.conflicts(proposed_for_closures, user_projects) if data_available else [],
        "closure_data_available": data_available,
        "closure_note": CLOSURE_NOTE_USER if data_available else CLOSURE_NOTE_NONE,
        "suggestion": suggest_shift(window, found, max_shift_months, today),
    }
