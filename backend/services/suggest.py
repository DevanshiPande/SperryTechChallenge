"""Suggested inventory: listings from other companies that fit your projects, best first.
A listing ranks higher when its owner is a coordination partner (their project is matched with yours), when its
pickup is near your project, and when it is available during your construction window. Scores and reasons come
from code; nothing here uses Gemini."""
from datetime import date

from engine import geo
from services import projects as psvc
from services import resources as rsvc

PARTNER_POINTS = 30        # owner has a project matched with yours
PROXIMITY_POINTS = 35      # full at the project, zero at PROXIMITY_MAX_MI
PROXIMITY_MAX_MI = 50
DATES_POINTS = 35          # share of the listing's availability that falls in your construction window
MIN_SCORE = 10


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


def _partners(my_ids, company_id, by_id):
    """company_id -> best (overlap, my project, their project) among overlaps between your projects and theirs."""
    out = {}
    for o in psvc.user_overlaps():
        if o["project_a"] in my_ids:
            mine, theirs = o["project_a"], o["project_b"]
        elif o["project_b"] in my_ids:
            mine, theirs = o["project_b"], o["project_a"]
        else:
            continue
        tp = by_id.get(theirs)
        owner = tp and tp.get("company_id")
        if not owner or owner == company_id:
            continue
        if owner not in out or o.get("score", 0) > out[owner][0].get("score", 0):
            out[owner] = (o, by_id[mine], tp)
    return out


def suggested_resources(ident, limit=5, project_id=None):
    """project_id: score against that one project (any project, e.g. the one selected on the map);
    otherwise against all of your company's projects."""
    company = ident.require_company()
    by_id = {p["id"]: p for p in psvc.all_projects(with_ids=False)}
    if project_id:
        target = by_id.get(project_id)
        if not target:
            from services.errors import not_found
            raise not_found("Project", project_id)
        mine = [target] if target.get("center") else []
    else:
        mine = [p for p in by_id.values() if p.get("company_id") == company["id"] and p.get("center")]
    if not mine:
        return {"project_count": 0, "project_id": project_id, "suggestions": [],
                "note": "Upload a contract or add a project to get inventory suggestions for it."}
    partners = _partners({p["id"] for p in mine}, company["id"], by_id)
    out = []
    for r in rsvc.list_resources():
        loc = r.get("location") or {}
        if r.get("company_id") == company["id"] or loc.get("lat") is None:
            continue
        a_from, a_to = _d(r.get("available_from")), _d(r.get("available_to"))
        best = None
        for p in mine:
            w = p.get("construction_window") or {}
            mi = geo.haversine_mi(loc, p["center"])
            days = _overlap_days(a_from, a_to, _d(w.get("start")), _d(w.get("end")))
            span = max(1, (a_to - a_from).days + 1) if a_from and a_to else 1
            prox = PROXIMITY_POINTS * max(0.0, 1 - mi / PROXIMITY_MAX_MI)
            fit = DATES_POINTS * min(1.0, days / span)
            partner = partners.get(r.get("company_id"))
            bonus = PARTNER_POINTS if partner else 0
            score = round(prox + fit + bonus, 1)
            if best is None or score > best["score"]:
                best = {"score": score, "project": p, "mi": mi, "days": days, "partner": partner}
        if not best or best["score"] < MIN_SCORE:
            continue
        p, partner = best["project"], best["partner"]
        reasons = []
        if partner:
            o, my_p, their_p = partner
            reasons.append(f"{r.get('company_name')} is a coordination partner: their {_name(their_p)} is "
                           f"{o.get('closest_distance_mi', o.get('center_distance_mi'))} mi from "
                           f"{'your ' if my_p.get('company_id') == company['id'] else ''}{_name(my_p)}"
                           + (f" and overlaps it for {o['window_overlap_months']} months" if o.get("window_overlap_months") else "")
                           + ". Sharing their crews and equipment saves a separate mobilization.")
        yours = "your " if p.get("company_id") == company["id"] else ""
        reasons.append(f"Pickup in {loc.get('label') or 'the area'}, {best['mi']:.0f} mi from {yours}{_name(p)}.")
        if best["days"]:
            reasons.append(f"Available {r.get('date_label') or ''} — {best['days']} days fall inside the construction window.".replace("  ", " "))
        else:
            reasons.append("Not available during the construction window (check if the dates can move).")
        out.append({
            "resource_id": r["id"], "resource_name": r.get("name"), "company_id": r.get("company_id"),
            "company_name": r.get("company_name"), "score": best["score"], "for_project_id": p["id"],
            "for_project_name": _name(p), "distance_mi": round(best["mi"], 1), "overlap_days": best["days"],
            "partner": bool(partner), "reasons": reasons,
        })
    out.sort(key=lambda s: (-s["score"], s["distance_mi"]))
    return {"project_count": len(mine), "project_id": project_id, "suggestions": out[:limit],
            "basis": (f"Score out of 100: coordination partner {PARTNER_POINTS}, distance to your project "
                      f"{PROXIMITY_POINTS} (zero at {PROXIMITY_MAX_MI} mi), availability during your construction window "
                      f"{DATES_POINTS}.")}
