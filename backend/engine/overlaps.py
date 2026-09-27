"""Pair generation, overlap objects, score, potential and rank. Pure functions."""
from engine import cost, geo, windows

THRESHOLD_MI = 25
# Score v2 (spec update U1): proximity 40 + savings 40 + timing 20.
PROXIMITY_BASE = {"crossing": 40, "shared_land": 34, "shared_site": 26, "shared_crews": 14}
SAVINGS_FULL_PCT = 0.05  # savings of 5% or more of the smaller budget earn full points
SHIFT_MONTHS = 12
POTENTIAL_LEVELS = [
    {"code": "high", "label": "High potential", "min_score": 60},
    {"code": "moderate", "label": "Moderate potential", "min_score": 35},
    {"code": "lower", "label": "Lower potential", "min_score": 0},
]
METHOD_NOTES = [
    "Pairs match when their closest points (edge to edge) are under 25 miles: the distance crews and equipment "
    "actually travel. Sperry's rule (center points under 25 miles) is kept as center_distance_mi and "
    "within_sperry_rule; every pair under Sperry's rule also matches here.",
    "Score = proximity 40 + savings 40 + timing 20. Savings already shrink with distance and when timing does not line "
    "up, so distance and timing partly count twice: proximity measures how practical coordination is, savings how much "
    "it is worth.",
    "Savings use Dominion's filed budgets, MISO per-mile estimates for Georgia Power's redacted budgets, the MoDOT "
    "mobilization benchmark, ATRI trucking costs, BLS wages, and USDA land values. The shareable fraction is an "
    "assumption, shown as a range.",
    "Traffic uses OpenStreetMap roads, SCDOT (2025) and GDOT (2017) traffic counts where available, MoDOT work-zone "
    "capacity, and USDOT value of time. Hourly profiles and closure durations are assumptions.",
    "Lines are straight-line approximations between substations, so crossings are approximate.",
]


def overlap_id(a_id, b_id):
    return f"OVL_{a_id}__{b_id}"


def origin(project):
    """'public_filing', 'user' or 'contract'. The contract's `source` is {document, page}; origin lives in source.type."""
    s = project.get("source")
    if isinstance(s, dict):
        return s.get("type") or "public_filing"
    return s or "public_filing"


def is_user(project):
    return origin(project) in ("user", "contract")


def owner(project):
    """Public projects are owned by their utility; user projects by their company."""
    return project.get("company_id") if is_user(project) else project.get("utility")


def proximity_points(tier, closest_km):
    base = PROXIMITY_BASE.get(tier, 0)
    return base * (1 - min(closest_km if closest_km is not None else 40, 40) / 80)


def savings_points(savings_point, reference_budget):
    if not reference_budget:
        return 0.0
    pct = max(0, savings_point or 0) / reference_budget
    return min(pct / SAVINGS_FULL_PCT, 1) * 40


def timing_points(window_overlap_months, shift_possible):
    if window_overlap_months > 0:
        return min(window_overlap_months, 12) / 12 * 20
    return 6.0 if shift_possible else 0.0


def score_v2(tier, closest_km, savings_point, reference_budget, window_overlap_months, shift_possible):
    b = {"proximity": round(proximity_points(tier, closest_km), 1),
         "savings": round(savings_points(savings_point, reference_budget), 1),
         "timing": round(timing_points(window_overlap_months, shift_possible), 1)}
    return round(b["proximity"] + b["savings"] + b["timing"], 1), b


def potential_for(score):
    if score >= 60:
        return "high"
    if score >= 35:
        return "moderate"
    return "lower"


def shift_possible(wa, wb, today=None, max_months=SHIFT_MONTHS):
    """Can moving one window by up to +-12 months (never starting in the past) make the two windows overlap?"""
    from datetime import date
    if not wa or not wb:
        return False
    today = (today or date.today()).isoformat()
    for m in range(-max_months, max_months + 1):
        if m == 0:
            continue
        for moved, other in ((wa, wb), (wb, wa)):
            win = {"start": windows.add_months(moved["start"], m), "end": windows.add_months(moved["end"], m)}
            if win["start"] >= today and windows.overlap_days(win, other) >= 1:
                return True
    return False


def time_gap_days(a, b):
    da, db = windows.to_date(a.get("in_service_date")), windows.to_date(b.get("in_service_date"))
    if da is None or db is None:
        return None
    return abs((da - db).days)


def build_overlap(a, b, kind, traffic=None, today=None):
    """Overlap object for projects a and b (a is DESC for cross_utility, the user project for user_project).
    traffic: optional callable (a, b) -> traffic savings dict (merged closures on shared roads).
    Returns None when either project has no center or their closest points are 25 mi or more apart
    (center distance is used when a geometry is missing)."""
    if not a.get("center") or not b.get("center"):
        return None
    mi = geo.center_distance_mi(a["center"], b["center"])
    km, points = geo.closest(a["endpoints"], b["endpoints"])
    edge_mi = geo.km_to_mi(km)
    # Edge distance decides; Sperry's center-rule pairs always stay in (rounding can put an edge a hair past a center).
    if min(edge_mi if edge_mi is not None else mi, mi) >= THRESHOLD_MI:
        return None
    tier, expl = geo.tier_for(km)
    wa, wb = a.get("construction_window"), b.get("construction_window")
    months = windows.overlap_months(wa, wb)
    shiftable = months == 0 and shift_possible(wa, wb, today)
    traffic_info = traffic(a, b) if traffic else None
    est = cost.cost_estimate_v2(a, b, tier, km, mi, months, shiftable, traffic_info)
    score, breakdown = score_v2(tier, km, est["total_estimated_savings_usd"], est["reference_budget_usd"], months, shiftable)
    sc = cost.cost_scenario(months, km, (wa or {}).get("start"), (wb or {}).get("start"),
                            cost.sandbox_rates(est["reference_budget_usd"], a.get("state") or b.get("state")))
    return {
        "id": overlap_id(a["id"], b["id"]),
        "project_a": a["id"],
        "project_b": b["id"],
        "center_distance_mi": mi,
        "closest_distance_mi": edge_mi if edge_mi is not None else mi,
        "closest_distance_km": km,
        "within_sperry_rule": mi < THRESHOLD_MI,
        "closest_points": points,
        "tier": tier,
        "tier_explanation": expl,
        "shared_endpoint": geo.shared_endpoint(a["endpoints"], b["endpoints"]),
        "time_gap_days": time_gap_days(a, b),
        "window_overlap_months": months,
        "schedule_shift_possible": shiftable,
        "timing_confidence": "predicted" if "predicted" in ((wa or {}).get("source"), (wb or {}).get("source")) else "filed",
        "score": score,
        "score_breakdown": breakdown,
        "rank": None,
        "cost_estimate": est,
        "brief": None,
        "label": f'{a.get("short_name") or a["name"]} ↔ {b.get("short_name") or b["name"]}',
        "potential": potential_for(score),
        "cost_scenario": sc,
        "kind": kind,
    }


def cross_utility_overlaps(projects, traffic=None, today=None):
    """Every DESC x GPC public pair whose closest points are under 25 mi (includes all of Sperry's center-rule pairs)."""
    desc = [p for p in projects if p.get("utility") == "DESC" and not is_user(p)]
    gpc = [p for p in projects if p.get("utility") == "GPC" and not is_user(p)]
    out = [o for a in desc for b in gpc if (o := build_overlap(a, b, "cross_utility", traffic, today))]
    return rank(out)


def user_project_overlaps(user_project, projects, traffic=None, today=None):
    """A user project against every project with a different owner."""
    me = owner(user_project)
    out = []
    for p in projects:
        if p["id"] == user_project["id"] or owner(p) == me:
            continue
        o = build_overlap(user_project, p, "user_project", traffic, today)
        if o:
            out.append(o)
    return out


def edge_mi(o):
    """Edge distance of an overlap; records saved before edge matching only have the center distance."""
    return o.get("closest_distance_mi", o["center_distance_mi"])


def rank(overlaps):
    """Assign rank 1..N by score desc, then edge distance asc, then id. Returns a new sorted list."""
    ordered = sorted(overlaps, key=lambda o: (-o["score"], edge_mi(o), o["id"]))
    for i, o in enumerate(ordered, 1):
        o["rank"] = i
    return ordered


def rank_by_kind(overlaps):
    by_kind = {}
    for o in overlaps:
        by_kind.setdefault(o.get("kind", "cross_utility"), []).append(o)
    out = []
    for kind in sorted(by_kind):
        out.extend(rank(by_kind[kind]))
    return out
