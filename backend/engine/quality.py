"""Quality flags. Pure functions."""
from datetime import date

from engine import geo

MESSAGES = {
    "ENDPOINT_NOT_FOUND": "One endpoint could not be located; center uses the located endpoint only.",
    "ENDPOINT_NOT_FOUND_ALL": "No endpoint could be located; the project has no map position.",
    "POSSIBLY_COMPLETE": "In-service date is in the past; project may already be complete.",
    "LOW_CONFIDENCE_MATCH": "At least one endpoint location is a low-confidence match; review before relying on it.",
    "DATE_PARSE_FAILED": "The in-service date in the filing could not be parsed.",
    "MULTI_PHASE_DATE": "The filing lists several phase in-service dates; the final phase date is used.",
    "DATE_MISMATCH": "The project list and the project detail page give different need dates; the detail page date is used.",
    "MULTI_SEGMENT": "The project covers more than one line or site; only the first segment is mapped.",
    "ENDPOINT_SPLIT_FAILED": "Endpoint names could not be read from the project title.",
    "WINDOW_INVALID": "Construction start was after the end date; start set to 12 months before the end.",
    "AMBIGUOUS_NAME": "Several substations share this name and nothing in the filing picks between them.",
    "LINE_TOO_LONG": "The two located endpoints are more than 150 km apart; one match may be wrong.",
    "COST_PARSE_FAILED": "The cost row in the filing could not be read.",
    "MANUAL_OVERRIDE": "Location set by manual review.",
}
CODES = ["ENDPOINT_NOT_FOUND", "COORD_CONFLICT", "POSSIBLY_COMPLETE", "LOW_CONFIDENCE_MATCH", "DATE_PARSE_FAILED",
         "DATE_MISMATCH", "MULTI_SEGMENT", "ENDPOINT_SPLIT_FAILED", "WINDOW_INVALID", "AMBIGUOUS_NAME", "LINE_TOO_LONG"]


def flag(code, message=None):
    return {"code": code, "message": message or MESSAGES.get(code, code)}


def add_flag(project, code, message=None):
    flags = project.setdefault("quality_flags", [])
    if not any(f["code"] == code and (message is None or f["message"] == message) for f in flags):
        flags.append(flag(code, message))


def location_flags(project, today=None):
    """Flags derived from the located endpoints and the in-service date."""
    eps = project.get("endpoints") or []
    located = geo.located(eps)
    if eps and len(located) < len(eps):
        add_flag(project, "ENDPOINT_NOT_FOUND",
                 MESSAGES["ENDPOINT_NOT_FOUND"] if located else MESSAGES["ENDPOINT_NOT_FOUND_ALL"])
    if any(e.get("confidence") == "low" for e in eps):
        add_flag(project, "LOW_CONFIDENCE_MATCH")
    isd = project.get("in_service_date")
    if isd and isd < (today or date.today()).isoformat():
        add_flag(project, "POSSIBLY_COMPLETE")


def coord_conflicts(projects, normalize, km=0.5):
    """COORD_CONFLICT: the same normalized endpoint name (same utility) resolves to points > 0.5 km apart."""
    seen = {}
    for p in projects:
        for e in geo.located(p.get("endpoints")):
            key = (p.get("utility"), normalize(e["name"]))
            if key[1]:
                seen.setdefault(key, []).append((p, e))
    flagged = set()  # one COORD_CONFLICT per (project, endpoint)
    for (_, _), items in seen.items():
        for i, (pa, ea) in enumerate(items):
            for pb, eb in items[i + 1:]:
                if geo.haversine_km(ea, eb) > km:
                    msg = (f'{ea["name"]} substation appears at two different positions '
                           f'({ea["lat"]}, {ea["lon"]} vs {eb["lat"]}, {eb["lon"]}) across projects.')
                    for p, e in ((pa, ea), (pb, eb)):
                        if (p["id"], e["name"]) not in flagged:
                            flagged.add((p["id"], e["name"]))
                            add_flag(p, "COORD_CONFLICT", msg)


def flat_list(projects):
    return [{"project_id": p["id"], "code": f["code"], "message": f["message"]}
            for p in projects for f in p.get("quality_flags", [])]
