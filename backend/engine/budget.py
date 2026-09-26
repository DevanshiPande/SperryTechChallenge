"""Reference budgets (spec update U2.2): uploaded contract > DESC filing > MISO per-mile estimate for redacted GPC lines."""
import re

from engine import geo, sources

MILES_RE = re.compile(r"(\d+(?:\.\d+)?)\s*miles?\b", re.I)
EQUIPMENT_WORK = ("equipment", "reactor", "breaker", "switch", "relay", "capacitor", "statcom", "transformer")


def line_miles(project):
    """Stated miles in the description, else straight-line endpoint distance x route factor. None if not a located line."""
    m = MILES_RE.search(project.get("description") or "")
    if m:
        return round(float(m.group(1)), 2), "description"
    pts = geo.located(project.get("endpoints"))
    if project.get("project_type") == "line" and len(pts) == 2:
        rf = sources.get("route_factor")["point"]
        return round(geo.haversine_mi(pts[0], pts[1]) * rf, 2), "straight-line x route factor"
    return None, None


def estimate(project):
    """-> {budget_usd, budget_source, budget_note}. Never invents a budget for substation/equipment-only work."""
    if project.get("budget_source") == "contract" and project.get("budget_usd"):
        return {"budget_usd": project["budget_usd"], "budget_source": "contract", "budget_note": "Stated in the uploaded contract"}
    cost = project.get("cost")
    if project.get("utility") == "DESC" and cost and cost.get("total"):
        return {"budget_usd": cost["total"], "budget_source": "filing", "budget_note": "Dominion Energy SC filing, total estimated cost"}
    if project.get("utility") != "GPC":
        return {"budget_usd": None, "budget_source": None, "budget_note": "No budget available"}
    work = (project.get("work_type_label") or "").lower() + " " + (project.get("name") or "").lower()
    if project.get("project_type") != "line" or any(w in work for w in EQUIPMENT_WORK):
        return {"budget_usd": None, "budget_source": None, "budget_note": "Substation or equipment-only work: no per-mile estimate"}
    per_mile, kv_class = sources.by_voltage("line_cost_per_mile", project.get("voltage_kv"))
    miles, how = line_miles(project)
    if not per_mile or not miles:
        return {"budget_usd": None, "budget_source": None, "budget_note": "Voltage or line length unknown"}
    return {"budget_usd": int(round(per_mile * miles, -3)), "budget_source": "estimated_miso",
            "budget_note": f"Estimate: {miles} mi ({how}) x ${per_mile:,}/mi (MISO {kv_class} kV new single circuit). "
                           "Georgia Power budgets are redacted."}


def attach(project):
    """Adds budget_usd / budget_source / budget_note to a project dict (in place) and returns it."""
    project.update(estimate(project))
    return project
