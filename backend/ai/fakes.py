"""Deterministic stand-ins for Gemini when FAKE_GEMINI=1 (tests, offline demos). Ported from contract/mock-server.js.
They return the same JSON shapes the real prompts ask for; all post-processing and guards still run."""
import re
from calendar import monthrange

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"], 1)}
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "a": 1, "an": 1}
TOWNS = ["north augusta", "hardeeville", "savannah", "okatie", "bluffton", "ridgeland", "pooler", "rincon", "augusta",
         "evans", "charleston", "jasper"]


def _num(w):
    if not w:
        return None
    return int(w) if w.isdigit() else WORDNUM.get(w.lower())


def parse_dates(text):
    rx = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:\s+(\d{1,2})(?!\d))?"
                    r"(?:\s*[-–]\s*(\d{1,2})(?!\d))?(?:,?\s+(20\d\d))?", re.I)
    hits = [{"m": MONTHS[m.group(1).lower()[:3]], "d": int(m.group(2)) if m.group(2) else None,
             "d2": int(m.group(3)) if m.group(3) else None, "y": int(m.group(4)) if m.group(4) else None}
            for m in rx.finditer(text)]
    if not hits:
        return None, None
    yr = re.search(r"\b(20\d\d)\b", text)
    yr = int(yr.group(1)) if yr else None

    def fmt(h, day):
        y = h["y"] or yr
        return f"{y}-{h['m']:02d}-{day:02d}" if y else None

    first, last = hits[0], hits[-1]
    if len(hits) == 1:
        y = first["y"] or yr
        end = fmt(first, first["d2"]) if first["d2"] else (fmt(first, first["d"] or monthrange(y, first["m"])[1])
                                                            if y else None)
        return fmt(first, first["d"] or 1), end
    y2 = last["y"] or yr
    return fmt(first, first["d"] or 1), (fmt(last, last["d"] or monthrange(y2, last["m"])[1]) if y2 else None)


def _field(v, conf="high"):
    return {"value": v, "confidence": conf if v not in (None, "") else None}


def _town(text):
    t = text.lower()
    town = next((k for k in TOWNS if k in t), None)
    return town.title() if town else None


def draft(kind, text):
    t = text.lower()
    start, end = parse_dates(text)
    town = _town(text)
    if kind == "project":
        name = ("Corridor upgrade" if "corridor" in t else "Substation upgrade" if "substation" in t
                else "Bridge replacement" if "bridge" in t else "Road resurfacing" if "resurfac" in t else None)
        hrs = re.search(r"(\d{1,2}\s*(?:am|pm))\s*(?:to|-|–)\s*(\d{1,2}\s*(?:am|pm))", text, re.I)
        road = re.search(r"\b(US-?\s?\d+|I-?\s?\d+|SC-?\s?\d+|GA-?\s?\d+)\b", text, re.I)
        lane = None
        if "lane closure" in t:
            lane = ("Lane closure (northbound)" if "north" in t else "Lane closure (southbound)" if "south" in t
                    else "Lane closure, direction not stated")
        out = {
            "name": _field(name),
            "description": _field(text[:160] if len(text) > 20 else None, "medium"),
            "location": _field(f"Near {town}" if town else None),
            "start_date": _field(start), "end_date": _field(end),
            "work_type": _field("Roadway improvement" if re.search(r"road|corridor|resurfac|lane", t) else
                                "Utility construction" if re.search(r"line|transmission|substation", t) else None,
                                "medium"),
            "lane_closures": _field(lane, "high" if re.search(r"north|south", t) else "medium"),
            "work_hours": _field(f"{hrs.group(1).upper()} – {hrs.group(2).upper()}" if hrs else
                                 ("Nighttime (hours not stated)" if "night" in t else None), "high" if hrs else "medium"),
            "roads_affected": _field(road.group(1).upper() if road else None),
        }
    elif kind == "resource":
        q = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an)\s+(?:bucket|truck|crane|lineworker|"
                      r"worker|crew)", t)
        rate = re.search(r"\$[\d,]+", text)
        out = {
            "name": _field("Bucket trucks with operators" if "bucket truck" in t else "Crane" if "crane" in t else
                           "Certified lineworkers" if "lineworker" in t else None),
            "quantity": _field(_num(q.group(1)) if q else None),
            "location": _field(town),
            "dates": _field(f"{start} to {end}" if start and end else start, "medium"),
            "rate": _field(rate.group(0) if rate else None),
        }
    else:
        q = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an)\s+(?:certified\s+)?(?:lineworker|"
                      r"worker|operator|electrician)", t)
        out = {
            "role": _field("Transmission lineworker" if "lineworker" in t else "Bucket truck operator" if "operator" in t
                           else "Substation electrician" if "electrician" in t else None),
            "openings": _field(_num(q.group(1)) if q else None),
            "project": _field(None),
            "dates": _field(f"{start} to {end}" if start and end else start, "medium"),
            "requirements": _field("Relevant certification required" if "certified" in t else None, "medium"),
        }
    out["follow_up_questions"] = []
    return out


def scenario(message):
    t = message.lower()
    changes = []
    m1 = re.search(r"(\d+)\s*(?:shared\s+)?(?:bucket\s+)?trucks?\s+for\s+(\d+)\s*days?", t)
    m2 = re.search(r"(\d+)\s*truck[- ]days?", t)
    if m1:
        n = int(m1.group(1)) * int(m1.group(2))
        changes.append({"path": "coordinated.shared_truck_days", "value": n,
                        "label": f"Use {m1.group(1)} shared bucket trucks for {m1.group(2)} days ({n} truck-days)"})
    elif m2:
        changes.append({"path": "coordinated.shared_truck_days", "value": int(m2.group(1)),
                        "label": f"Use {m2.group(1)} shared truck-days"})
    if re.search(r"yard|laydown", t):
        changes.append({"path": "coordinated.laydown_sites", "value": 1, "label": "Share a single laydown yard"})
    return {"changes": changes, "note": "These are inputs only; totals are recomputed by Gridlock."}


def agent_turn(messages, read_only=False):
    """Keyword-routed stand-in for the tool-calling model: picks a tool for a user turn, then summarizes results."""
    last = messages[-1] if messages else {"role": "user", "text": ""}
    if last["role"] == "tool":
        parts = []
        for r in last.get("results") or []:
            res = r.get("response") or {}
            if "error" in res:
                parts.append(f"I couldn't do that: {res['error']['message']}")
            elif "pending_action_id" in res:
                parts.append(f"{res['summary']} Please confirm below.")
            elif res.get("overlaps"):
                o = res["overlaps"][0]
                parts.append(f"The top match is {o['label']}, {o['center_distance_mi']} mi apart with "
                             f"{o['window_overlap_months']} months of overlapping construction.")
            elif "totals" in res:
                parts.append(f"Coordinating {res['label']} saves about ${res['totals']['savings']:,} (illustrative).")
            elif "count" in res:
                parts.append(f"I found {res['count']} result(s).")
        return {"text": " ".join(parts) or "Done.", "calls": []}
    t = (last.get("text") or "").lower()
    m = re.search(r"\b(?:have|got|list|add)\s+(\d+|one|two|three|four|five|a|an)\s+([a-z ]+?)s?\b(?:$|[.,!]| at| in| near"
                  r"| available| for)", t)
    if m and not read_only:
        name = m.group(2).strip().split()[-1]
        crew = name in ("lineworker", "crew", "worker", "electrician")
        return {"calls": [{"name": "add_resource", "args": {"name": name.capitalize(), "type": "crew" if crew else
                                                            "equipment", "quantity": _num(m.group(1))}}]}
    if re.search(r"sav(e|es|ing|ings)|cost|money", t):
        return {"calls": [{"name": "list_overlaps", "args": {"kind": "cross_utility", "sort": "savings", "limit": 3}}]}
    if re.search(r"crane|truck|equipment|resource|crew", t):
        return {"calls": [{"name": "find_resources", "args": {}}]}
    if re.search(r"\bjobs?\b|hire|worker", t):
        return {"calls": [{"name": "search_jobs", "args": {}}]}
    return {"calls": [{"name": "list_overlaps", "args": {"kind": "cross_utility", "limit": 3}}]}


CONTRACT_LABELS = {
    "project_name": r"project name", "owner_company": r"owner|contractor", "utility": r"utility", "work_type": r"work type",
    "voltage_kv": r"voltage", "endpoints": r"endpoints|substations", "location_text": r"location", "line_miles": r"line length",
    "start_date": r"start date|commencement", "end_date": r"completion date|end date", "budget_usd": r"contract price|budget",
    "crew_size": r"crew size", "equipment": r"equipment", "roads_affected": r"roads affected", "lane_closures": r"lane closures",
    "work_hours": r"work hours",
}


def contract(text):
    """Stand-in for Gemini contract extraction: reads 'Label: value' lines. Evidence = the exact line from the document."""
    from dateutil import parser as dp
    out = {}
    lines = [l.strip() for l in text.splitlines() if ":" in l]
    for key, lab in CONTRACT_LABELS.items():
        line = next((l for l in lines if re.match(rf"^({lab})\s*:", l, re.I)), None)
        if not line:
            out[key] = {"value": None, "confidence": None, "evidence": None}
            continue
        raw = line.split(":", 1)[1].strip()
        v = raw
        if key in ("voltage_kv", "line_miles", "crew_size", "budget_usd"):
            m = re.search(r"\d[\d,]*\.?\d*", raw)
            v = float(m.group().replace(",", "")) if m else None
        elif key in ("start_date", "end_date"):
            try:
                v = dp.parse(raw, fuzzy=True).date().isoformat()
            except (ValueError, OverflowError):
                v = None
        elif key == "endpoints":
            v = [s.strip() for s in re.split(r"\s+to\s+|\s+-\s+|,", raw) if s.strip()]
        elif key == "equipment":
            v = []
            for part in raw.split(","):
                m = re.match(r"\s*(\d+)\s+(.*)", part)
                if m:
                    v.append({"type": m.group(2).strip(), "quantity": int(m.group(1))})
        out[key] = {"value": v, "confidence": "high", "evidence": line}
    return out
