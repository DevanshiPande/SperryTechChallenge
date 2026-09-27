"""Work-zone traffic model (spec update U3.3-U3.5). Pure functions: hourly demand, a deterministic input-output queue,
the best closure window, and the delay avoided by merging two closures on the same road."""
from engine import sources as S


def lanes_per_direction(lanes, oneway):
    if not lanes:
        return None
    return lanes if oneway else max(1, lanes // 2)


def closure_type(lanes, oneway):
    """Flagging (alternating one-lane traffic) on two-lane or unknown roads; otherwise one lane closed per direction."""
    per_dir = lanes_per_direction(lanes, oneway)
    return "lane_closure" if per_dir and per_dir >= 2 else "flagging"


def hourly_demand(aadt, share=1.0):
    return [aadt * f * share for f in S.get("hourly_profile")["values"]]


def queue_delay(demand, cap_during, cap_after, start, hours):
    """Deterministic input-output queue. demand: 24 hourly volumes. Returns (delay_veh_hours, vehicles_affected, queue_by_hour)."""
    q, delay, affected, queue = 0.0, 0.0, 0.0, {}
    for i in range(hours):
        h = (start + i) % 24
        q_end = max(0.0, q + demand[h] - cap_during)
        delay += (q + q_end) / 2
        affected += demand[h]
        q = q_end
        queue[h] = q
    i = hours
    while q > 0 and i < hours + 48:  # drain at normal capacity
        h = (start + i) % 24
        q_end = max(0.0, q + demand[h] - cap_after)
        delay += (q + q_end) / 2
        q = q_end
        queue.setdefault(h, q)
        i += 1
    return delay, affected, queue


def _directions(aadt, lanes, oneway, ctype):
    """(demand profile, closure capacity, normal capacity) per modeled traffic stream."""
    wz = S.get("work_zone_capacity_per_lane")["point"]
    normal = S.get("normal_capacity_per_lane")["point"]
    if ctype == "flagging":
        return [(hourly_demand(aadt), S.get("flagging_capacity_total")["point"], 2 * normal)]
    per_dir = lanes_per_direction(lanes, oneway) or 1
    split = S.get("directional_split")["point"]
    shares = [split] if oneway else [split, 1 - split]
    return [(hourly_demand(aadt, s), (per_dir - 1) * wz, per_dir * normal) for s in shares]


def closure_delay(aadt, lanes, oneway, ctype, start, hours):
    total_delay, total_aff, queues = 0.0, 0.0, {}
    for demand, cap, cap_after in _directions(aadt, lanes, oneway, ctype):
        d, a, q = queue_delay(demand, cap, cap_after, start, hours)
        total_delay += d
        total_aff += a
        for h, v in q.items():
            queues[h] = queues.get(h, 0) + v
    return total_delay, total_aff, queues


def fmt_window(start, hours):
    return f"{start:02d}:00–{(start + hours) % 24:02d}:00"


def plan(aadt, lanes, oneway, hours=None, ctype=None):
    """Try every start hour; recommend the one with the least delay (ties: earlier start)."""
    hours = hours or S.get("closure_hours_per_crossing")["point"]
    ctype = ctype or closure_type(lanes, oneway)
    results = []
    for start in range(24):
        d, a, q = closure_delay(aadt, lanes, oneway, ctype, start, hours)
        results.append((round(d, 1), start, a, q))
    best = min(results, key=lambda r: (r[0], r[1]))
    worst = max(results, key=lambda r: (r[0], -r[1]))
    streams = _directions(aadt, lanes, oneway, ctype)
    closed = {(best[1] + i) % 24 for i in range(hours)}
    hourly = [{"hour": h, "demand": round(sum(s[0][h] for s in streams)),
               "capacity": round(sum((s[1] if h in closed else s[2]) for s in streams)), "queue": round(best[3].get(h, 0))}
              for h in range(24)]
    vtts = S.get("value_of_travel_time")
    return {
        "closure_type": ctype, "closure_hours": hours,
        "recommended_window": fmt_window(best[1], hours), "recommended_start_hour": best[1],
        "delay_veh_hours": best[0], "vehicles_affected": round(best[2]),
        "delay_cost_usd": round(best[0] * vtts["per_vehicle_hour"] * vtts["occupancy"]),
        "worst_window": fmt_window(worst[1], hours), "worst_delay_veh_hours": worst[0],
        "worst_delay_cost_usd": round(worst[0] * vtts["per_vehicle_hour"] * vtts["occupancy"]),
        "hourly": hourly,
        "sources": [S.cite("work_zone_capacity_per_lane", "1600 veh/h/lane in a work zone"),
                    S.cite("value_of_travel_time", f"${vtts['per_vehicle_hour']}/vehicle-hour ({vtts['dollar_year']}$)")],
        "assumptions": [f"{hours}-hour closure (assumption)", "Typical weekday hourly profile (assumption)",
                        f"Peak-direction split {S.get('directional_split')['point']:.0%} (assumption)"]
                       + (["Flagging capacity 1000 veh/h for both directions (assumption)"] if ctype == "flagging" else []),
    }


def merged_savings(road, hours_a, hours_b):
    """Two closures on the same road on different days vs one merged closure (one setup, both crews).
    road: {aadt, lanes, oneway}. Returns veh-hours avoided (can be <= 0; the sign is kept) and dollars."""
    ctype = closure_type(road.get("lanes"), road.get("oneway"))
    pa = plan(road["aadt"], road.get("lanes"), road.get("oneway"), hours_a, ctype)
    pb = plan(road["aadt"], road.get("lanes"), road.get("oneway"), hours_b, ctype)
    pm = plan(road["aadt"], road.get("lanes"), road.get("oneway"), max(hours_a, hours_b) + 2, ctype)
    separate = pa["delay_veh_hours"] + pb["delay_veh_hours"]
    avoided = round(separate - pm["delay_veh_hours"], 1)
    vtts = S.get("value_of_travel_time")
    wage = max(S.get("lineworker_wage_per_hour")[k] for k in ("GA", "SC"))
    setup_usd = round(S.get("flagger_crew")["people"] * min(hours_a, hours_b) * wage)
    return {"separate_delay_veh_hours": round(separate, 1), "merged_delay_veh_hours": pm["delay_veh_hours"],
            "merged_window": pm["recommended_window"], "traffic_delay_avoided_veh_hours": avoided,
            "delay_avoided_usd": round(avoided * vtts["per_vehicle_hour"] * vtts["occupancy"]),
            "closures_avoided": 1, "traffic_control_setups_avoided": 1, "setup_cost_avoided_usd": setup_usd}
