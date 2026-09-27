"""Suggested inventory for a project: what it needs, what you already have, and which other companies' listings fill
the rest, best first. All logic is in code (no Gemini):

1. Needs: the project's contract equipment list and crew size, else typical needs for its kind of work (services/needs).
2. Only listings for a needed category qualify; a crane smaller than the job needs is rejected.
3. Your own listings are applied to the needs first.
4. Other companies' listings are scored (out of 100): need fit 40 (share of the remaining need it covers), dates 25
   (share of the listing's availability inside the construction window), distance 20 (zero at 50 mi), coordination
   partner 15 (the owner has a project matched with this one). Listings are then assigned greedily, best first, until
   each need is covered; the coverage plan says what is still missing.
5. Hauling saved: a nearby listing avoids trucking the unit from a typical contractor base (ATRI cost per mile).
"""
from datetime import date

from engine import geo, sources as S
from services import needs as N
from services import projects as psvc
from services import resources as rsvc
from services.state import STATE

NEED_POINTS = 40
DATES_POINTS = 25
DISTANCE_POINTS = 20
DISTANCE_MAX_MI = 50
PARTNER_POINTS = 15


def _d(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _overlap_days(a_start, a_end, b_start, b_end):
    if not all((a_start, a_end, b_start, b_end)):
        return 0
    return max(0, (min(a_end, b_end) - max(a_start, b_start)).days + 1)


def _name(p):
    return p.get("short_name") or p.get("name") or p["id"]


def _partners(pid, company_id, by_id):
    """company_id -> (overlap, their project) for other companies' projects matched with project pid."""
    out = {}
    for o in psvc.user_overlaps():
        if pid not in (o["project_a"], o["project_b"]):
            continue
        tp = by_id.get(o["project_b"] if o["project_a"] == pid else o["project_a"])
        owner = tp and tp.get("company_id")
        if not owner or owner == company_id:
            continue
        if owner not in out or o.get("score", 0) > out[owner][0].get("score", 0):
            out[owner] = (o, tp)
    return out


def _distance_mi(loc, p):
    pts = geo.located(p.get("endpoints")) or ([p["center"]] if p.get("center") else [])
    return min(geo.haversine_mi(loc, q) for q in pts) if pts else None


def _haul_saved(mi, units, people=False):
    """Trucking avoided by picking the units up nearby instead of hauling them from a typical base (round trip).
    Crews travel in crew trucks: one per 4 workers (assumption)."""
    if people:
        units = -(-units // 4)
    base, rate, factor = S.get("base_to_site_miles")["point"], S.get("truck_cost_per_mile")["point"], S.get("route_factor")["point"]
    return round(max(0.0, base - mi * factor) * 2 * rate * max(1, units))


def _qty_text(n, unit, label):
    if unit == "people":
        return f"{n} {'person' if n == 1 else 'people'} ({label.lower()})"
    return f"{n} {label.lower() if n != 1 else label.lower().rstrip('s')}"


def suggested_resources(ident, limit=5, project_id=None):
    """project_id: the project selected on the map (any project). Without it: your most recent project."""
    company = ident.require_company()
    by_id = {p["id"]: p for p in psvc.all_projects(with_ids=False)}
    if project_id:
        target = by_id.get(project_id)
        if not target:
            from services.errors import not_found
            raise not_found("Project", project_id)
    else:
        mine = sorted((p for p in by_id.values() if p.get("company_id") == company["id"]),
                      key=lambda p: str(p.get("created_at") or ""), reverse=True)
        target = mine[0] if mine else None
    if not target or not target.get("center"):
        return {"project_count": 0, "project_id": project_id, "suggestions": [], "needs": [], "own": [],
                "note": "Upload a contract or add a project to get inventory suggestions for it."}

    needs, needs_basis = N.project_needs(target, STATE.db)
    remaining = {n["category"]: n["quantity"] for n in needs}
    need_by = {n["category"]: n for n in needs}
    w = target.get("construction_window") or {}
    w_start, w_end = _d(w.get("start")), _d(w.get("end"))
    partners = _partners(target["id"], company["id"], by_id)
    yours = target.get("company_id") == company["id"]
    pname = ("your " if yours else "") + _name(target)

    own, candidates = [], []
    for r in rsvc.list_resources():
        loc = r.get("location") or {}
        cat, tons = N.listing_offer(r)
        need = need_by.get(cat)
        if not need or loc.get("lat") is None:
            continue
        if need.get("tons") and tons and tons < need["tons"]:
            continue  # too small for the job
        mi = _distance_mi(loc, target)
        a_from, a_to = _d(r.get("available_from")), _d(r.get("available_to"))
        days = _overlap_days(a_from, a_to, w_start, w_end)
        item = {"r": r, "cat": cat, "tons": tons, "mi": mi, "days": days,
                "span": max(1, (a_to - a_from).days + 1) if a_from and a_to else 1}
        (own if r.get("company_id") == company["id"] else candidates).append(item)

    # 3. your own listings first
    own_out = []
    for it in own:
        take = min(it["r"]["quantity"], remaining[it["cat"]])
        if take <= 0 or not it["days"]:
            continue
        remaining[it["cat"]] -= take
        need = need_by[it["cat"]]
        own_out.append({"resource_id": it["r"]["id"], "resource_name": it["r"]["name"], "category": it["cat"], "covers": take,
                        "text": f"You already listed {it['r']['name']} ({it['r']['quantity']} available): covers "
                                f"{_qty_text(take, need['unit'], need['label'])}."})

    # 4. score other companies' listings against what is still needed, then assign greedily
    def score(it):
        need_left = remaining[it["cat"]]
        fit = min(1.0, it["r"]["quantity"] / need_left) if need_left > 0 else 0.0
        dates = min(1.0, it["days"] / it["span"])
        dist = max(0.0, 1 - (it["mi"] or DISTANCE_MAX_MI) / DISTANCE_MAX_MI)
        partner = 1.0 if it["r"].get("company_id") in partners else 0.0
        return round(NEED_POINTS * fit + DATES_POINTS * dates + DISTANCE_POINTS * dist + PARTNER_POINTS * partner, 1)

    out = []
    pool = list(candidates)
    while pool:
        pool.sort(key=lambda it: (-score(it), it["mi"] or 999))
        it = pool.pop(0)
        r, need = it["r"], need_by[it["cat"]]
        take = min(r["quantity"], remaining[it["cat"]]) if it["days"] else 0
        s = score(it)
        remaining[it["cat"]] -= take
        reasons = []
        if take:
            reasons.append(f"Covers {_qty_text(take, need['unit'], need['label'])} of the {need['quantity']} needed"
                           f" ({need['why']}).")
        elif it["days"]:
            reasons.append(f"Extra {need['label'].lower()}: the need is already covered by better matches.")
        else:
            reasons.append(f"Needed ({need['why']}), but not available during the construction window.")
        if it["tons"] and need.get("tons"):
            reasons.append(f"{it['tons']}-ton capacity meets the {need['tons']}-ton requirement.")
        partner = partners.get(r.get("company_id"))
        if partner:
            o, tp = partner
            reasons.append(f"{r.get('company_name')} is a coordination partner: their {_name(tp)} is "
                           f"{o.get('closest_distance_mi', o.get('center_distance_mi'))} mi from {pname}.")
        haul = _haul_saved(it["mi"], take, need["unit"] == "people") if take else 0
        reasons.append(f"Pickup in {(r.get('location') or {}).get('label') or 'the area'}, {it['mi']:.0f} mi from {pname}"
                       + (f": about ${haul:,} less trucking than hauling from a typical {S.get('base_to_site_miles')['point']}-mile base." if haul else "."))
        if it["days"]:
            reasons.append(f"Available {r.get('date_label') or ''}: {it['days']} days inside the construction window.".replace("  ", " "))
        out.append({
            "resource_id": r["id"], "resource_name": r.get("name"), "company_id": r.get("company_id"),
            "company_name": r.get("company_name"), "category": it["cat"], "category_label": need["label"],
            "score": s, "covers": take, "for_project_id": target["id"], "for_project_name": _name(target),
            "distance_mi": round(it["mi"], 1), "overlap_days": it["days"], "partner": bool(partner),
            "haul_saved_usd": haul, "reasons": reasons,
        })
    out.sort(key=lambda s: (-(s["covers"] > 0), -s["score"], s["distance_mi"]))

    plan = []
    for n in needs:
        covered = n["quantity"] - max(0, remaining[n["category"]])
        by = [o["resource_name"] + (" (yours)" if o in own_out else f" ({o.get('company_name')})")
              for o in own_out + out if o["category"] == n["category"] and o["covers"] > 0]
        plan.append({**n, "covered": covered, "missing": max(0, remaining[n["category"]]), "covered_by": by})
    return {
        "project_count": 1, "project_id": target["id"], "project_name": _name(target), "needs": plan,
        "needs_basis": needs_basis, "own": own_out, "suggestions": out[:limit],
        "missing": [f"{_qty_text(n['missing'], n['unit'], n['label'])}" for n in plan if n["missing"]],
        "hauling_saved_usd": sum(o["haul_saved_usd"] for o in out),
        "basis": (f"Only listings for something the project needs qualify. Score out of 100: need fit {NEED_POINTS}, "
                  f"dates {DATES_POINTS}, distance {DISTANCE_POINTS} (zero at {DISTANCE_MAX_MI} mi), coordination partner "
                  f"{PARTNER_POINTS}. Your own listings are used first; trucking cost {S.get('truck_cost_per_mile')['point']} "
                  "$/mile (ATRI)."),
    }
