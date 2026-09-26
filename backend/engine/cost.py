"""Illustrative cost scenario and cost estimate. Formula is shared with the frontend; do not change it."""
import copy

from engine import geo

UNIT_RATES = {"mobilization_per_event": 3000, "bucket_truck_per_day": 1500, "laydown_per_site": 5000}

# Typical right-of-way widths, not from the filings.
CORRIDOR_WIDTH_FT = {115: 100, 230: 150, 500: 200}
DEFAULT_CORRIDOR_FT = 100
FT_TO_M = 0.3048
SQM_PER_ACRE = 4046.86

FORMULA = (
    "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + "
    "laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + "
    "shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project."
)


def _yn(b):
    return "yes" if b else "no"


def scenario_assumptions(window_overlap_months, closest_km):
    return [
        "Unit rates are placeholders; replace with real bids.",
        f"Trucks are shared only when construction windows overlap ({_yn(window_overlap_months > 0)} for this pair).",
        f"One laydown yard is shared only when projects are under 8 km apart ({_yn(closest_km is not None and closest_km < 8)} for this pair).",
    ]


def compute_totals(sc):
    """Recompute totals and ranges from a scenario's inputs."""
    r = sc["unit_rates"]
    mob, truck, lay = r["mobilization_per_event"], r["bucket_truck_per_day"], r["laydown_per_site"]

    def per_project(x):
        return x["mobilization_events"] * mob + x["truck_days"] * truck + x["laydown_sites"] * lay

    sep_a, sep_b = per_project(sc["separate"]["a"]), per_project(sc["separate"]["b"])
    c = sc["coordinated"]
    shared = c["shared_truck_days"] * truck + c["laydown_sites"] * lay
    coord_a = c["mobilization_events_a"] * mob + shared / 2
    coord_b = c["mobilization_events_b"] * mob + shared / 2
    separate, coordinated = sep_a + sep_b, coord_a + coord_b
    savings = separate - coordinated

    def num(x):
        return int(x) if float(x).is_integer() else round(x, 2)

    totals = {
        "separate": num(separate),
        "coordinated": num(coordinated),
        "savings": num(savings),
        "savings_pct": round(savings / separate * 100, 1) if separate else 0,
        "separate_by_project": {"a": num(sep_a), "b": num(sep_b)},
        "coordinated_by_project": {"a": num(coord_a), "b": num(coord_b)},
    }
    rng = {
        "separate": [round(separate * 0.85), round(separate * 1.15)],
        "coordinated": [round(coordinated * 0.85), round(coordinated * 1.15)],
        "savings": [round(savings * 0.75), round(savings * 1.25)],
    }
    return totals, rng


def sandbox_rates(reference_budget=None, state=None):
    """Sandbox defaults from cost_sources.json (spec update U2.4). Truck rate stays the placeholder while the USACE
    schedule is unverified; mobilization per event = reference budget x mobilization % / 2 when a budget is known."""
    from engine import sources
    rates = dict(UNIT_RATES)
    eq = sources.get("equipment_rate_per_hour")
    if eq.get("verified") and eq.get("bucket_truck"):
        rates["bucket_truck_per_day"] = round(eq["bucket_truck"] * 8)
    if reference_budget:
        rates["mobilization_per_event"] = int(round(reference_budget * sources.get("mobilization_pct")["point"] / 2, -2))
    wage = sources.get("lineworker_wage_per_hour").get(state or "SC") or sources.get("lineworker_wage_per_hour")["SC"]
    rates["crew_size"] = 4
    rates["crew_cost_per_day"] = int(round(wage * 8 * 4))
    return rates


def cost_scenario(window_overlap_months, closest_km, start_a, start_b, unit_rates=None):
    sc = {
        "illustrative": True,
        "defaults_source": "cost_sources.json",
        "unit_rates": dict(unit_rates or UNIT_RATES),
        "separate": {
            "a": {"mobilization_events": 1, "truck_days": 10, "laydown_sites": 1, "start_date": start_a},
            "b": {"mobilization_events": 1, "truck_days": 10, "laydown_sites": 1, "start_date": start_b},
        },
        "coordinated": {
            "mobilization_events_a": 1,
            "mobilization_events_b": 1,
            "shared_truck_days": 12 if window_overlap_months > 0 else 20,
            "laydown_sites": 1 if (closest_km is not None and closest_km < 8) else 2,
            "start_date_a": start_a,
            "start_date_b": start_b,
        },
    }
    sc["totals"], sc["range"] = compute_totals(sc)
    sc["formula"] = FORMULA
    sc["assumptions"] = scenario_assumptions(window_overlap_months, closest_km)
    return sc


def apply_changes(scenario, changes):
    """Return a copy of the scenario with {path, value} changes applied and totals recomputed."""
    sc = copy.deepcopy(scenario)
    for ch in changes:
        node = sc
        parts = ch["path"].split(".")
        for p in parts[:-1]:
            node = node[p]
        node[parts[-1]] = ch["value"]
    sc["totals"], sc["range"] = compute_totals(sc)
    return sc


def corridor_width_ft(voltage_kv):
    if voltage_kv is None:
        return DEFAULT_CORRIDOR_FT
    return CORRIDOR_WIDTH_FT.get(int(voltage_kv), DEFAULT_CORRIDOR_FT)


def shared_row_acres(project_a, project_b, tier):
    """Shared right-of-way acres for two line projects in the crossing/shared_land tiers, else None."""
    if tier not in ("crossing", "shared_land"):
        return None, None
    if project_a.get("project_type") != "line" or project_b.get("project_type") != "line":
        return None, None
    length_m = geo.shared_length_m(project_a["endpoints"], project_b["endpoints"])
    if length_m is None:
        return None, None
    volts = [v for v in (project_a.get("voltage_kv"), project_b.get("voltage_kv")) if v is not None]
    width_ft = corridor_width_ft(max(volts) if volts else None)
    acres = round(length_m * width_ft * FT_TO_M / SQM_PER_ACRE, 1)
    return acres, width_ft


def cost_estimate(scenario, project_a, project_b, tier):
    acres, width_ft = shared_row_acres(project_a, project_b, tier)
    assumptions = list(scenario["assumptions"])
    if acres is not None:
        assumptions.append(
            f"Shared right-of-way assumes a {width_ft} ft corridor (typical values, not from the filings) "
            f"along the part of one line within 1.6 km of the other."
        )
    return {
        "shared_row_acres": acres,
        "mobilization_savings_usd": None,
        "total_estimated_savings_usd": scenario["totals"]["savings"],
        "assumptions": assumptions,
    }


# ---------------------------------------------------------------- cost model v2 (spec update U2)
def _rng(low, point, high):
    lo, hi = sorted((low, high))
    return {"low": int(round(lo)), "point": int(round(point)), "high": int(round(hi))}


def _zero(applies=False, **extra):
    return {"low": 0, "point": 0, "high": 0, "applies": applies, **extra}


def reference_budget(a, b):
    """Smaller known budget of the two projects -> (usd, source, project_id) or (None, None, None)."""
    known = [(p.get("budget_usd"), p.get("budget_source"), p["id"]) for p in (a, b) if p.get("budget_usd")]
    return min(known) if known else (None, None, None)


def _state_of(a, b):
    for p in (a, b):
        if p.get("state") in ("GA", "SC"):
            return p["state"]
    return "SC"


def cost_estimate_v2(a, b, tier, closest_km, center_mi, window_overlap_months, shift_possible, traffic=None):
    """Sourced savings estimate for coordinating projects a and b. Every component is {low, point, high}.
    traffic: optional {"delay_usd": point, "setup_usd": point, "veh_hours": ...} from the traffic module."""
    from engine import sources as S
    budget, budget_src, budget_pid = reference_budget(a, b)
    timing_ok = window_overlap_months > 0 or shift_possible
    shift_only = window_overlap_months == 0 and shift_possible
    assumptions, cites = [], []

    # a) mobilization avoided
    mob_pct, share = S.get("mobilization_pct"), S.get("shareable_fraction")
    if budget and closest_km is not None and closest_km < 40 and timing_ok:
        k = 0.5 if shift_only else 1.0
        mob = {**_rng(budget * mob_pct["low"] * share["low"] * k, budget * mob_pct["point"] * share["point"] * k,
                      budget * mob_pct["high"] * share["high"] * k), "applies": True, "requires_schedule_shift": shift_only}
        cites.append(S.cite("mobilization_pct", f"{mob_pct['low']:.0%}–{mob_pct['high']:.0%} of the budget"))
        assumptions.append(f"Share of one mobilization that can be shared: {share['low']:.0%}–{share['high']:.0%} (assumption)")
        if shift_only:
            assumptions.append("Mobilization savings halved: the construction windows only overlap after a schedule shift")
    else:
        why = ("no budget available" if not budget else "projects more than 40 km apart" if (closest_km if closest_km is not None else 99) >= 40
               else "construction windows cannot overlap within 12 months")
        mob = _zero(False, reason=why)
        if not budget:
            assumptions.append("No budget available for either project: mobilization savings not estimated")

    # b) logistics (hauling). Can be negative when sites are far apart.
    loads, base, cpm, rf = S.get("haul_loads_per_project"), S.get("base_to_site_miles"), S.get("truck_cost_per_mile")["point"], \
        S.get("route_factor")["point"]
    between = (center_mi or 0) * rf

    def haul(L, B):
        return L * 2 * cpm * (B - between)  # separate - coordinated

    if timing_ok:
        logi = {**_rng(haul(loads["low"], base["low"]), haul(loads["point"], base["point"]), haul(loads["high"], base["high"])),
                "applies": True, "site_to_site_road_miles": round(between, 1)}
        cites.append(S.cite("truck_cost_per_mile", f"${cpm}/mile"))
        assumptions.append(f"Hauling: {loads['low']}–{loads['high']} equipment loads per project, contractor base "
                           f"{base['low']}–{base['high']} miles from site, road miles = {rf} x straight-line (assumptions)")
        if logi["point"] < 0:
            assumptions.append("Logistics savings are negative: moving shared equipment between these sites costs more than "
                               "two separate mobilizations")
    else:
        logi = _zero(False, reason="construction windows cannot overlap")

    # c) shared land (right-of-way)
    acres, width_ft = shared_row_acres_v2(a, b, tier)
    # Sharing right-of-way means coordinating the work, so (like crews) it needs windows that overlap or can.
    if acres and timing_ok:
        st = _state_of(a, b)
        price = S.get("land_value_per_acre")[st]
        r = S.get("shared_land_range")
        land = {**_rng(acres * price * r["low"], acres * price, acres * price * r["high"]), "applies": True, "acres": acres}
        cites += [S.cite("row_width_ft", f"{width_ft} ft corridor"), S.cite("land_value_per_acre", f"${price:,}/acre ({st})")]
        assumptions.append("Shared land value shown as ±20% (assumption)")
    else:
        land = _zero(False, **({"reason": "construction windows cannot overlap", "acres": acres} if acres else {}))

    # d) traffic delay avoided by merging closures on a shared road
    if traffic and (traffic.get("delay_usd") is not None or traffic.get("setup_usd")):
        pt = (traffic.get("delay_usd") or 0) + (traffic.get("setup_usd") or 0)
        tdel = {**_rng(pt * 0.5, pt, pt * 1.5), "applies": True, "veh_hours": traffic.get("veh_hours"),
                "delay_usd": traffic.get("delay_usd"), "setup_usd": traffic.get("setup_usd"), "roads": traffic.get("roads", [])}
        cites.append(S.cite("value_of_travel_time", f"${S.get('value_of_travel_time')['per_vehicle_hour']}/vehicle-hour"))
        assumptions.append("Traffic savings shown as 50–150% of the point estimate (hourly profile and closure hours are assumptions)")
    else:
        tdel = _zero(False)

    comps = {"mobilization": mob, "logistics": logi, "shared_land": land, "traffic_delay": tdel}
    low = sum(c["low"] for c in comps.values())
    point = sum(c["point"] for c in comps.values())
    high = sum(c["high"] for c in comps.values())
    if low < 0:
        assumptions.append("The low end is shown as $0: coordinating would not cost more than working separately")
    if budget:
        pb = a if a["id"] == budget_pid else b
        label = {"filing": "Dominion Energy SC filing (budget)", "contract": "Uploaded contract (budget)",
                 "estimated_miso": "MISO per-mile estimate (Georgia Power budget is redacted)"}.get(budget_src, budget_src)
        cites.insert(0, {"name": f"{label}: {pb.get('short_name') or pb['id']}", "value_used": f"${budget:,}"})
    return {
        "total_estimated_savings_usd": max(0, int(point)),
        "range_usd": [max(0, int(low)), max(0, int(high))],
        "components": comps,
        "reference_budget_usd": budget,
        "reference_budget_source": budget_src,
        "shared_row_acres": acres,
        "mobilization_savings_usd": mob["point"] if mob["applies"] else None,
        "assumptions": assumptions,
        "sources": cites,
    }


def shared_row_acres_v2(a, b, tier):
    """Acres of line A within 1.6 km of line B x MISO corridor width (both lines; crossing/shared_land tiers only)."""
    from engine import sources as S
    if tier not in ("crossing", "shared_land") or a.get("project_type") != "line" or b.get("project_type") != "line":
        return None, None
    length_m = geo.shared_length_m(a["endpoints"], b["endpoints"])
    if not length_m:
        return None, None
    volts = [v for v in (a.get("voltage_kv"), b.get("voltage_kv")) if v]
    width_ft, _ = S.by_voltage("row_width_ft", max(volts) if volts else 115)
    return round(length_m * width_ft * FT_TO_M / SQM_PER_ACRE, 1), width_ft
