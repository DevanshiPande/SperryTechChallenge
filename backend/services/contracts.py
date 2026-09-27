"""Contract upload and match (spec update U4). The raw PDF is never stored: only its text hash and the reviewed fields.

Gemini reads the contract text and returns each field with an exact evidence snippet. Code keeps a field only when the
snippet is really in the document and every number in the value appears in it. Locations come from the substation
matcher or Nominatim, never from Gemini."""
import hashlib
import io
import logging
import re
from datetime import date

from dateutil import parser as dateparser

from ai import fakes, gemini
from db import mongo
from engine import budget, geo, overlaps as eng, whatif as wi
from engine.closures import normalize_roads
from services import events, ml, projects as psvc
from services.common import new_id
from services.errors import ApiError, bad_request, gemini_unavailable, not_found
from services.geocode import geocode
from services.state import STATE

log = logging.getLogger("gridlock.contracts")

MAX_BYTES = 10 * 1024 * 1024
MIN_TEXT = 200
FIELDS = ["project_name", "owner_company", "utility", "work_type", "voltage_kv", "endpoints", "location_text", "line_miles",
          "start_date", "end_date", "budget_usd", "crew_size", "equipment", "roads_affected", "lane_closures", "work_hours"]
NUMERIC = {"voltage_kv", "line_miles", "budget_usd", "crew_size"}
DATES = {"start_date", "end_date"}
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


# ---------------------------------------------------------------- extraction
def pdf_text(data):
    import pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        raise ApiError("UNSUPPORTED_FILE", "Could not read this file as a PDF.")


def _field(value_schema):
    return {"type": "object", "properties": {"value": value_schema, "confidence": {"type": ["string", "null"]},
                                             "evidence": {"type": ["string", "null"]}}, "required": ["value", "confidence", "evidence"]}


STR, NUM = {"type": ["string", "null"]}, {"type": ["number", "null"]}
SCHEMA = {"type": "object", "properties": {
    "project_name": _field(STR), "owner_company": _field(STR), "utility": _field(STR), "work_type": _field(STR),
    "voltage_kv": _field(NUM), "endpoints": _field({"type": ["array", "null"], "items": {"type": "string"}}),
    "location_text": _field(STR), "line_miles": _field(NUM), "start_date": _field(STR), "end_date": _field(STR),
    "budget_usd": _field(NUM), "crew_size": _field(NUM),
    "equipment": _field({"type": ["array", "null"], "items": {"type": "object", "properties": {
        "type": {"type": "string"}, "quantity": {"type": ["number", "null"]}}, "required": ["type", "quantity"]}}),
    "roads_affected": _field(STR), "lane_closures": _field(STR), "work_hours": _field(STR)},
    "required": FIELDS}


def extraction_prompt(text):
    return ("Extract these fields from the construction contract below. For every field return value, confidence "
            "(high = stated explicitly, medium = inferred) and evidence = the exact snippet copied character for character "
            "from the document that supports the value. Use null for value and evidence when the document does not say. "
            "Dates as YYYY-MM-DD. budget_usd = the total contract price in dollars as a plain number. endpoints = the "
            "substation names the line connects, as written. utility = the electric utility named, if any.\n"
            f"Fields: {', '.join(FIELDS)}\n\nCONTRACT TEXT:\n{text[:60000]}")


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _numbers(s):
    out = set()
    for m in re.finditer(r"\d[\d,]*\.?\d*", s or ""):
        try:
            out.add(float(m.group().replace(",", "").rstrip(".")))
        except ValueError:
            pass
    for w, n in WORDNUM.items():
        if re.search(rf"\b{w}\b", s or "", re.I):
            out.add(float(n))
    return out


def _number_supported(value, evidence):
    """The value's number must appear in the evidence (allowing 'thousand'/'million' scaling)."""
    nums = _numbers(evidence)
    v = float(value)
    scales = [1] + ([1e3] if re.search(r"thousand|\bk\b", evidence, re.I) else []) + ([1e6] if re.search(r"million|\bm\b", evidence, re.I) else [])
    return any(abs(n * s - v) < 0.5 for n in nums for s in scales)


def validate(raw, text):
    """Keep a field only if its evidence is in the text and its numbers are in the evidence. Returns (fields, dropped)."""
    doc = _norm(text)
    fields, dropped = {}, []
    for k in FIELDS:
        f = raw.get(k) if isinstance(raw.get(k), dict) else {}
        v, ev, conf = f.get("value"), f.get("evidence"), f.get("confidence")
        if v in (None, "", []):
            fields[k] = {"value": None, "confidence": None, "evidence": None}
            continue
        ok = bool(ev) and _norm(ev) in doc
        try:
            if ok and k in NUMERIC:
                v = float(v)
                ok = v > 0 and _number_supported(v, ev)
                v = int(v) if k in ("budget_usd", "crew_size", "voltage_kv") else round(v, 2)
            elif ok and k in DATES:
                v = dateparser.parse(str(v)).date().isoformat()
                ok = dateparser.parse(ev, fuzzy=True, default=dateparser.parse("2000-01-01")).date().isoformat() == v
            elif ok and k == "equipment":
                v = [{"type": str(e.get("type")), "quantity": e.get("quantity")} for e in v if isinstance(e, dict) and e.get("type")]
                ok = all(e["quantity"] is None or _number_supported(e["quantity"], ev) for e in v)
            elif ok and k == "endpoints":
                v = [str(x).strip() for x in v if str(x).strip()]
                ok = all(_norm(x) in doc for x in v)
            elif ok and k == "roads_affected":
                v = ", ".join(normalize_roads(v)) or str(v)
            elif ok:
                v = str(v).strip()
        except (TypeError, ValueError, OverflowError):
            ok = False
        if ok:
            fields[k] = {"value": v, "confidence": conf if conf in ("high", "medium") else "medium", "evidence": ev.strip()}
        else:
            dropped.append(k)
            fields[k] = {"value": None, "confidence": None, "evidence": None}
    return fields, dropped


FOLLOW = {"project_name": "What is the project called?", "start_date": "When does construction start?",
          "end_date": "When does construction end?", "budget_usd": "What is the contract price?",
          "location_text": "Where is the work (town or county)?", "endpoints": "Which substations does the line connect?"}


def _save_contract(doc):
    if STATE.db is not None:
        existing = STATE.db.contracts.find_one({"_id": doc["id"]})
        if existing:
            mongo.update(STATE.db, "contracts", doc["id"], {k: v for k, v in doc.items() if k != "id"})
        else:
            mongo.insert(STATE.db, "contracts", doc)
    else:
        STATE.contracts[doc["id"]] = doc


def get_contract(ident, cid):
    doc = mongo.clean(STATE.db.contracts.find_one({"_id": cid})) if STATE.db is not None else STATE.contracts.get(cid)
    if doc is None:
        raise not_found("Contract", cid)
    if doc.get("company_id") and ident.company_id and doc["company_id"] != ident.company_id:
        raise ApiError("FORBIDDEN", "This contract belongs to another company")
    return doc


def analyze(ident, filename, data):
    if not data:
        raise bad_request("Upload a PDF in the form field `file`.")
    if len(data) > MAX_BYTES:
        raise bad_request("The PDF is larger than 10 MB.")
    if not data[:5].startswith(b"%PDF"):
        raise ApiError("UNSUPPORTED_FILE", "Only PDF files are supported.")
    text = pdf_text(data)
    if len(text.strip()) < MIN_TEXT:
        raise ApiError("NO_TEXT_LAYER", "This PDF looks scanned. Upload a text PDF or fill the form manually.")
    if not gemini.available():
        raise gemini_unavailable("Gemini is not responding. Fill the form manually.")
    try:
        raw = gemini.generate_json(extraction_prompt(text), SCHEMA, temperature=0.1, fake=lambda: fakes.contract(text))
    except gemini.GeminiUnavailable:
        raise gemini_unavailable("Gemini is not responding. Fill the form manually.")
    fields, dropped = validate(raw, text)
    missing = [k for k in FIELDS if fields[k]["value"] in (None, "", [])]
    doc = {"id": new_id("CTR"), "company_id": ident.company_id, "filename": filename,
           "text_hash": hashlib.sha256(text.encode()).hexdigest(), "text_chars": len(text), "extracted": fields,
           "dropped_fields": dropped, "status": "needs_review", "created": mongo.now()}
    _save_contract(doc)
    return {"contract_id": doc["id"], "filename": filename, "status": doc["status"], "fields": fields, "missing": missing,
            "dropped_fields": dropped, "ready": not any(k in missing for k in ("project_name", "start_date", "end_date")),
            "follow_up_questions": [FOLLOW[k] for k in missing if k in FOLLOW][:3], "source": "gemini",
            "note": "Review every field against its evidence snippet. Fields whose snippet was not found in the document were dropped."}


# ---------------------------------------------------------------- match
def _val(fields, k):
    f = fields.get(k)
    return f.get("value") if isinstance(f, dict) else f


def _locate(fields):
    """Substation matcher first (stated utility, else both), then Nominatim on location_text."""
    from pipeline import locate as L
    from pipeline.fetch_substations import load_overrides, match_project
    names = [n for n in (_val(fields, "endpoints") or []) if n][:2]
    title = _val(fields, "project_name") or " - ".join(names)
    if names:
        util = {"dominion energy south carolina": "DESC", "desc": "DESC", "georgia power": "GPC", "gpc": "GPC"}.get(
            _norm(_val(fields, "utility")), None)
        feats = _features()
        best = None
        for u in ([util] if util else ["DESC", "GPC"]):
            res = [L.validate_name(n, r) for n, r in zip(names, match_project(title, names, u, feats[u], overrides=load_overrides()))]
            located = [r for r in res if r["lat"] is not None]
            rank = (len(located), sum({"high": 3, "medium": 2, "low": 1}.get(r["confidence"], 0) for r in res))
            if best is None or rank > best[0]:
                best = (rank, res)
        eps = [{"name": n, "lat": r["lat"], "lon": r["lon"], "confidence": r["confidence"], "source": r.get("source"), "county": None}
               for n, r in zip(names, best[1]) if r["lat"] is not None]
        if eps:
            return eps, None
    loc = _val(fields, "location_text")
    g = geocode(loc) if loc else None
    if g:
        return [{"name": g["label"], "lat": g["lat"], "lon": g["lon"], "confidence": "medium", "source": g["source"], "county": None}], g
    raise bad_request("Could not locate this contract. Add substation names or a town in the location field.")


_FEATS = {}


def _features():
    if not _FEATS:
        from pipeline import locate as L
        _FEATS.update(L.load_features())
    return _FEATS


def contract_project(cid, company, fields, today=None):
    eps, geocoded = _locate(fields)
    start = _val(fields, "start_date")
    end = _val(fields, "end_date")
    try:
        start = dateparser.parse(str(start)).date().isoformat() if start else None
        end = dateparser.parse(str(end)).date().isoformat() if end else None
    except (ValueError, OverflowError):
        raise bad_request("start_date and end_date must be dates")
    if not end and not start:
        raise bad_request("A start date or an end date (completion or in-service date) is needed to find coordination partners.")
    if start and end and end <= start:
        raise bad_request("The end date must be after the start date.")
    name = _val(fields, "project_name") or "Uploaded contract"
    kv = _val(fields, "voltage_kv")
    window, start_flags = {"start": start, "end": end, "source": "contract"}, []
    if not start:
        # The contract gives no start date: predict it (ML_README U6), never before today.
        pw = ml.predicted_window({"id": cid, "name": name, "description": _val(fields, "work_type"), "voltage_kv": kv,
                                  "line_miles": _val(fields, "line_miles"), "in_service_date": end},
                                 reference_year=ml.this_year(), not_before=(today or date.today()).isoformat())
        if not pw or pw["start"] >= end:
            raise bad_request("The contract has no start date and one could not be predicted; add a start date.")
        window = {"start": pw["start"], "end": end, "source": "predicted", "prediction": pw["prediction"]}
        start_flags = pw["flags"]
    elif not end:
        # The contract gives a start but no end date: predict the end from the duration model (never replaces a document date).
        pe = ml.predicted_end({"id": cid, "name": name, "description": _val(fields, "work_type"), "voltage_kv": kv,
                               "line_miles": _val(fields, "line_miles")}, start, reference_year=ml.this_year())
        if not pe:
            raise bad_request("The contract has no end date and one could not be predicted; add an end date.")
        end = pe["end"]
        window = {"start": start, "end": end, "source": "predicted", "prediction": pe["prediction"]}
    p = {"id": cid, "utility": "USER", "utility_name": _val(fields, "owner_company") or (company or {}).get("name") or "Contract",
         "state": None, "name": name, "short_name": name if len(name) <= 40 else name[:39] + "…",
         "voltage_kv": int(kv) if kv else None, "project_type": "line" if len(eps) == 2 else "substation", "status": "Planned",
         "in_service_date": end, "construction_window": window,
         "endpoints": eps, "center": geo.center_of(eps), "geometry": geo.geojson(eps),
         "location_confidence": min((e["confidence"] for e in eps), key=["high", "medium", "low"].index) if eps else "not_found",
         "description": _val(fields, "work_type"), "cost": None, "source": {"document": "Uploaded contract", "page": None, "type": "contract"},
         "quality_flags": [], "overlap_ids": [], "work_type_label": _val(fields, "work_type") or "Contract work", "counties": [],
         "company_id": (company or {}).get("id") or "__contract__", "roads_affected": normalize_roads(_val(fields, "roads_affected")),
         "lane_closures": _val(fields, "lane_closures"), "work_hours": _val(fields, "work_hours"), "geocoded": geocoded,
         "line_miles": _val(fields, "line_miles")}
    for code in start_flags:
        p["quality_flags"].append({"code": code, "message": "The predicted start fell in the past, so it was set to today."})
    if _val(fields, "budget_usd"):
        p.update(budget_usd=int(float(_val(fields, "budget_usd"))), budget_source="contract")
    # No budget in the contract: predict it for transmission work (voltage stated or a two-substation line).
    budget.attach(p, predictor=ml.predicted_budget, predict_missing=bool(kv) or len(eps) == 2)
    return p


def _is_self(p, other, company_id, text_hash):
    """A project that is really this contract's own work: the company's own projects (never its own partner), or a
    saved copy of the same document (by text hash; older saves: same name and same dates)."""
    if eng.is_user(other) and company_id and other.get("company_id") == company_id:
        return True
    if text_hash and other.get("contract_text_hash") == text_hash:
        return True
    return (_norm(other.get("name")) == _norm(p.get("name"))
            and (other.get("construction_window") or {}).get("start") == p["construction_window"]["start"]
            and (other.get("construction_window") or {}).get("end") == p["construction_window"]["end"])


def match(ident, cid, reviewed):
    doc = get_contract(ident, cid)
    fields = {**doc["extracted"], **{k: ({"value": v, "confidence": "user", "evidence": None} if not isinstance(v, dict) else v)
                                     for k, v in (reviewed or {}).items() if k in FIELDS}}
    p = contract_project(cid, ident.company, fields)
    tx = STATE.traffic
    traffic_fn = tx.pair_savings if tx else None
    today = date.today()
    matches = []
    candidates = [o for o in psvc.all_projects(with_ids=False)
                  if o["id"] != cid and not _is_self(p, o, ident.company_id, doc.get("text_hash"))]
    for other in candidates:
        o = eng.build_overlap(p, other, "contract_match", traffic_fn, today)
        if not o:
            continue
        sug = wi.suggest_shift(p["construction_window"], [{"construction_window": other.get("construction_window")}], 12, today)
        roads = [{"road_ref": c.get("road_ref") or c.get("road_name"), "delay_avoided_veh_hours": c["traffic_delay_avoided_veh_hours"],
                  "merged_window": c["merged_window"]} for c in (tx.conflicts_between(p, other) if tx else [])]
        matches.append({"project_id": other["id"], "short_name": other.get("short_name"), "name": other["name"],
                        "utility": other.get("utility"), "utility_name": other.get("utility_name"),
                        "center_distance_mi": o["center_distance_mi"], "closest_distance_mi": o["closest_distance_mi"],
                        "closest_distance_km": o["closest_distance_km"],
                        "tier": o["tier"], "tier_explanation": o["tier_explanation"], "window_overlap_months": o["window_overlap_months"],
                        "schedule_shift_possible": o["schedule_shift_possible"], "score": o["score"],
                        "score_breakdown": o["score_breakdown"], "potential": o["potential"], "cost_estimate": o["cost_estimate"],
                        "suggestion": {"shift_months": sug["shift_months"], "suggested_window": sug["suggested_window"],
                                       "explanation": sug["explanation"]}, "shared_roads": roads})
    matches.sort(key=lambda m: (-m["score"], m["closest_distance_mi"]))
    # Savings from different partners do not add up: each estimate is mostly the SAME mobilization of this contract,
    # which can only be shared once. The summary is the best single partner's range.
    best_sav = max(matches, key=lambda m: m["cost_estimate"]["total_estimated_savings_usd"], default=None)
    xs = tx.crossings(p) if tx else []
    conflicts = [c for o in candidates for c in (tx.conflicts_between(p, o) if tx else [])]
    from engine import timing
    # Other construction nearby: everything except copies of this same document (own other projects still add traffic).
    others = [o for o in psvc.all_projects(with_ids=False)
              if o["id"] != cid and not (_is_self(p, o, None, doc.get("text_hash")))]
    work_timing = timing.best_time(p, xs, others, tx.crossings if tx else (lambda _p: []), today)
    result = {
        "contract_id": cid, "project": p, "work_timing": work_timing,
        "matches": matches, "best_match": matches[0]["project_id"] if matches else None,
        "traffic": {"crossings": xs, "access_roads": tx.access_roads(p) if tx and not xs else [], "conflicts": conflicts},
        "summary": {"matches_count": len(matches),
                    "total_savings_range_usd": best_sav["cost_estimate"]["range_usd"] if best_sav else [0, 0],
                    "best_savings_usd": best_sav["cost_estimate"]["total_estimated_savings_usd"] if best_sav else 0,
                    "best_savings_project_id": best_sav["project_id"] if best_sav else None,
                    "savings_range_basis": "best single partner (savings from several partners are not added: they "
                                           "mostly share the same mobilization of this contract, which happens once)",
                    "high_potential": sum(1 for m in matches if m["potential"] == "high")},
    }
    doc.update(reviewed_fields=fields, status="matched", project_preview={k: p[k] for k in ("name", "endpoints", "construction_window")})
    _save_contract(doc)
    return result


def _saved_copy(company_id, doc):
    """This company's project already saved from this contract or from the same document."""
    if doc.get("project_id"):
        try:
            psvc.get_project(doc["project_id"])
            return doc["project_id"]
        except ApiError:
            pass
    for p in psvc.user_projects():
        if p.get("company_id") == company_id and doc.get("text_hash") and p.get("contract_text_hash") == doc["text_hash"]:
            return p["id"]
    return None


def save(ident, cid):
    """Turn a reviewed contract into a user project (POST /projects logic, events emitted)."""
    company = ident.require_company()
    doc = get_contract(ident, cid)
    existing = _saved_copy(company["id"], doc)
    if existing:
        return {"contract_id": cid, "project": psvc.get_project(existing), "overlaps": [o for o in psvc.user_overlaps()
                if existing in (o["project_a"], o["project_b"])], "closure_conflicts": [], "already_saved": True}
    fields = doc.get("reviewed_fields") or doc["extracted"]
    p = contract_project(cid, company, fields)
    predicted = ml.predicted_field(p["construction_window"])
    body = {"name": p["name"], "description": p.get("description"),
            "start_date": None if predicted == "start" else p["construction_window"]["start"],
            "end_date": None if predicted == "end" else p["construction_window"]["end"], "endpoints": [{"name": e["name"], "lat": e["lat"], "lon": e["lon"]} for e in p["endpoints"]],
            "voltage_kv": p.get("voltage_kv"), "work_type": p.get("work_type_label"), "roads_affected": p.get("roads_affected"),
            "lane_closures": p.get("lane_closures"), "work_hours": p.get("work_hours"),
            "budget_usd": p.get("budget_usd") if p.get("budget_source") == "contract" else None,
            "line_miles": p.get("line_miles"),
            "contract_text_hash": doc.get("text_hash")}
    out = psvc.create_user_project(ident, body)
    doc.update(status="saved", project_id=out["project"]["id"])
    _save_contract(doc)
    events.emit("contracts", "update", cid, f"Contract saved as project {out['project']['name']}", company["id"], company["id"])
    return {"contract_id": cid, **out}
