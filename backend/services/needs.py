"""What a project needs (equipment and crew) and what a listing offers, in shared categories.
Needs come from the project's own contract (equipment list, crew size) when there is one, otherwise from typical
needs for its kind of work (config/equipment_norms.json), scaled by line length and voltage. No Gemini."""
import json
import math
import re
from functools import lru_cache
from pathlib import Path

from engine import geo

# Order matters: the first pattern that matches wins ("wire-stringing puller" is a puller, not materials).
CATEGORIES = [
    ("bucket_truck", "Bucket trucks", r"bucket"),
    ("digger_derrick", "Digger derricks", r"digger|derrick|auger|pole[- ]?setter"),
    ("crane", "Cranes", r"crane"),
    ("puller_tensioner", "Puller-tensioner sets", r"puller|tensioner|stringing"),
    ("excavator", "Excavators", r"excavat|backhoe"),
    ("trencher", "Trenchers", r"trench"),
    ("line_crew", "Line crew", r"line ?workers?|line ?crew|linem[ae]n|journeyman|line crew"),
    ("electricians", "Electricians", r"electrician"),
    ("materials", "Materials", r"\bpoles?\b|conductor|\bwire\b|transformer|material"),
]
LABELS = {k: label for k, label, _ in CATEGORIES}
PEOPLE = {"line_crew", "electricians"}


def categorize(text):
    t = (text or "").lower()
    for key, _, pat in CATEGORIES:
        if re.search(pat, t):
            return key
    return None


def tonnage(text):
    m = re.search(r"(\d{2,3})\s*-?\s*ton", text or "", re.I)
    return int(m.group(1)) if m else None


def listing_offer(r):
    """(category, tons) for a resource listing, from its name, notes and type."""
    text = " ".join(str(r.get(k) or "") for k in ("name", "notes"))
    m = re.search(r"Category: ([^.]+)\.", r.get("notes") or "")  # set by the frontend's listing form
    cat = categorize(m.group(1)) if m else None
    cat = cat or categorize(text) or ("line_crew" if r.get("type") == "crew" else None)
    return cat, tonnage(text)


@lru_cache(maxsize=1)
def norms():
    return json.loads((Path(__file__).resolve().parents[1] / "config" / "equipment_norms.json").read_text(encoding="utf-8"))


def line_miles(p):
    if p.get("line_miles"):
        return float(p["line_miles"])
    eps = geo.located(p.get("endpoints"))
    if len(eps) >= 2:
        return round(geo.haversine_mi(eps[0], eps[1]) * 1.1, 1)  # a line runs a little longer than straight
    return None


def _work(p):
    t = f"{p.get('name') or ''} {p.get('description') or ''} {p.get('work_type') or ''} {p.get('work_type_label') or ''}".lower()
    if "reconductor" in t:
        return "reconductor"
    if "rebuild" in t:
        return "rebuild"
    return "new" if re.search(r"construct|new|tap line|install", t) else "other"


def typical_needs(p):
    kind = "line" if p.get("project_type") == "line" or len(geo.located(p.get("endpoints"))) >= 2 else "substation"
    miles = line_miles(p) or (5.0 if kind == "line" else 0)
    kv = p.get("voltage_kv") or 0
    work = _work(p)
    out = []
    for cat, n in norms()[kind].items():
        if work in n.get("skip_for", []) or kv < n.get("min_kv", 0):
            continue
        steps = math.ceil(miles / n["per_miles"]) if n.get("per_miles") else 0
        qty = min(n["cap"], n["base"] + steps * n.get("per_step", 1))
        tons = None
        if n.get("tons_by_kv"):
            tons = max(t for v, t in n["tons_by_kv"].items() if kv >= int(v)) if any(kv >= int(v) for v in n["tons_by_kv"]) else None
        out.append({"category": cat, "label": LABELS[cat], "quantity": qty, "unit": n.get("unit", "units"), "tons": tons,
                    "why": n["note"], "source": "typical"})
    basis = (f"Typical for {'a ' + str(round(miles, 1)) + '-mile ' if kind == 'line' else 'a '}"
             f"{str(kv) + ' kV ' if kv else ''}{'line ' + work if kind == 'line' and work != 'other' else kind} project "
             "(planning assumption; the project has no equipment list of its own).")
    return out, basis


def contract_needs(p, db):
    """Needs from the contract this project was saved from (equipment list + crew size), or None."""
    if db is None or not p.get("contract_text_hash"):
        return None
    doc = db.contracts.find_one({"text_hash": p["contract_text_hash"], "company_id": p.get("company_id")}) \
        or db.contracts.find_one({"text_hash": p["contract_text_hash"]})
    if not doc:
        return None
    fields = {**(doc.get("extracted") or {}), **(doc.get("reviewed_fields") or {})}
    val = lambda k: (fields.get(k) or {}).get("value") if isinstance(fields.get(k), dict) else fields.get(k)
    out = []
    for item in val("equipment") or []:
        name = item.get("type") if isinstance(item, dict) else str(item)
        cat = categorize(name)
        if not cat:
            continue
        qty = (item.get("quantity") if isinstance(item, dict) else None) or 1
        prev = next((n for n in out if n["category"] == cat), None)
        if prev:
            prev["quantity"] += int(qty)
            continue
        out.append({"category": cat, "label": LABELS[cat], "quantity": int(qty), "unit": "units", "tons": tonnage(name),
                    "why": f"contract lists: {name}", "source": "contract"})
    crew = val("crew_size")
    if crew and not any(n["category"] in PEOPLE for n in out):
        out.append({"category": "line_crew", "label": LABELS["line_crew"], "quantity": int(crew), "unit": "people",
                    "tons": None, "why": f"contract crew size: {int(crew)}", "source": "contract"})
    return out or None


def project_needs(p, db):
    from_contract = contract_needs(p, db)
    if from_contract:
        return from_contract, "From the project's contract (equipment list and crew size)."
    return typical_needs(p)
