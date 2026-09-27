import json

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.deps import ident, json_body
from db import mongo
from services import events, ml, projects as psvc
from services.common import new_id
from services.errors import bad_request
from services.state import STATE, require_db

router = APIRouter()


@router.post("/overlaps/{oid}/feedback")
def feedback(oid: str, body: dict = Depends(json_body), who=Depends(ident)):
    """Planner feedback on an opportunity (labels for a future ranking model)."""
    db = require_db()
    company = who.require_company()
    psvc.get_overlap(oid)
    if not isinstance(body.get("useful"), bool):
        raise bad_request("useful must be true or false")
    if body.get("contacted") is not None and not isinstance(body["contacted"], bool):
        raise bad_request("contacted must be true or false")
    note = body.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > 2000):
        raise bad_request("note must be text of at most 2000 characters")
    doc = mongo.insert(db, "feedback", {"id": new_id("FDB"), "overlap_id": oid, "company_id": company["id"],
                                        "useful": body["useful"], "contacted": body.get("contacted"), "note": note,
                                        "ts": mongo.now()})
    events.emit("feedback", "insert", doc["id"], f"Feedback on {oid}", company["id"], company["id"])
    return JSONResponse(doc, status_code=201)


@router.get("/ml/status")
def status():
    m = ml.metrics()
    d, c = m["duration"], m["cost"]
    curves = json.loads((ml.ML_DIR / "learning_curves.json").read_text(encoding="utf-8"))
    return {
        "models_loaded": ml.available(),
        "duration": {"target": d["target"], "rows_used": d["rows_used"], "model": d["used"], "cv": d["cv"],
                     "mae_months": d["results"][d["used"]]["mae_months"],
                     "baseline_mae_months": d["results"][d["best_baseline"]]["mae_months"],
                     "improvement_over_baseline_pct": d["improvement_over_best_baseline_pct"],
                     "typical_error_months": d["prediction_interval_months"]["p50_abs_error"],
                     "rows_excluded": len(d["rows_excluded_bad_dates"]), "note": d["note"]},
        "cost": {"target": c["target"], "rows_used": c["rows_used"], "model": c["used"], "cv": c["cv"],
                 "median_abs_pct_error": c["results"][c["used"]]["median_abs_pct_error"],
                 "baseline_median_abs_pct_error": c["results"][c["best_baseline"]]["median_abs_pct_error"],
                 "vs_miso_per_mile_on_lines_with_miles": c["subset_with_known_miles"]["median_abs_pct_error"],
                 "typical_error_pct": c["prediction_interval_pct"]["p50_abs_pct_error"], "caveat": c["caveat"]},
        "feedback_count": STATE.db.feedback.count_documents({}) if STATE.db is not None else 0,
        "ranking_model": "not trained: needs outcome data",
        "learning_curves": curves,
    }
