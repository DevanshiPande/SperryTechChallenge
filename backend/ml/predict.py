"""
Prediction helpers for the backend. Load once at startup.
Every prediction returns a range and a label so the UI can mark it as predicted.
"""
import json, os, re
import numpy as np, pandas as pd, joblib

HERE = os.path.dirname(os.path.abspath(__file__))
_METRICS = json.load(open(os.path.join(HERE, "metrics.json")))
_DUR = joblib.load(os.path.join(HERE, "duration_model.joblib"))
_COST = joblib.load(os.path.join(HERE, "cost_model_log.joblib"))
FILING_YEAR = 2024

WORK_RULES = [
    (r"relay", "relay_protection"),
    (r"statcom|\bsvc\b|static var|capacitor|reactor", "reactive_equipment"),
    (r"reconductor", "reconductor"),
    (r"rebuild", "rebuild"),
    (r"breaker|switch", "breaker_switch"),
    (r"transformer|autobank", "transformer"),
    (r"new substation|substation:?\s*construct|construct.*substation", "new_substation"),
    (r"construct|\bnew\b", "new_line"),
    (r"\btap\b|fold-in|fold in", "tap"),
    (r"upgrade|moderniz|uprate", "upgrade"),
]

def work_type(title, desc=""):
    for text in (title, desc):
        for pat, lab in WORK_RULES:
            if re.search(pat, text or "", re.I):
                return lab
    return "other"

def _frame(project_type, work_type_, voltage_kv, line_miles, need_date=None, reference_year=FILING_YEAR):
    row = {"project_type": project_type, "work_type": work_type_,
           "voltage_kv": np.nan if voltage_kv is None else float(voltage_kv),
           "log_miles": np.nan if line_miles is None else float(np.log1p(line_miles)),
           "miles_missing": int(line_miles is None)}
    if need_date is not None:
        row["years_ahead"] = pd.Timestamp(need_date).year - reference_year
    return pd.DataFrame([row])

def predict_duration(project_type, work_type_, voltage_kv, line_miles, need_date, reference_year=FILING_YEAR):
    """Planned project window in months (start -> need date). reference_year: the year the plan was made
    (2024 for both filings; the current year for an uploaded contract)."""
    m = _METRICS["duration"]
    if m["used"].startswith("baseline"):
        months = float(m["target_stats_months"]["50%"])
    else:
        months = float(_DUR.predict(_frame(project_type, work_type_, voltage_kv, line_miles, need_date, reference_year))[0])
    err = m["prediction_interval_months"]["p50_abs_error"]
    return {"months": round(months, 1), "low": round(max(1.0, months - err), 1), "high": round(months + err, 1),
            "method": m["used"], "label": "predicted", "typical_error_months": err,
            "trained_on": f'{m["rows_used"]} Georgia Power projects (filed start and need dates)'}

def predict_start_date(need_date, not_before=None, **kw):
    """Only use when the start date is MISSING. not_before: e.g. today, for new/uploaded projects."""
    p = predict_duration(need_date=need_date, **kw)
    start = pd.Timestamp(need_date) - pd.DateOffset(months=int(round(p["months"])))
    flags = []
    if not_before is not None and start < pd.Timestamp(not_before):
        start = pd.Timestamp(not_before)
        flags.append("PREDICTED_START_CLAMPED_TO_TODAY")
    return {**p, "start_date": start.date().isoformat(), "flags": flags}

def predict_cost(project_type, work_type_, voltage_kv, line_miles):
    """Total project cost in USD, from Dominion's 44 filed budgets."""
    m = _METRICS["cost"]
    usd = float(np.exp(_COST.predict(_frame(project_type, work_type_, voltage_kv, line_miles))[0]))
    e = m["prediction_interval_pct"]["p50_abs_pct_error"] / 100
    return {"usd": int(round(usd, -3)), "low": int(round(usd / (1 + e), -3)), "high": int(round(usd * (1 + e), -3)),
            "method": m["used"], "label": "predicted", "typical_error_pct": round(e * 100, 1),
            "trained_on": f'{m["rows_used"]} Dominion Energy SC projects (filed budgets)'}

if __name__ == "__main__":
    # Sample contract (fictional): 230 kV new line, 4.2 miles, completes Oct 2027, uploaded in 2026
    print(predict_start_date(need_date="2027-10-29", not_before="2026-09-26", project_type="line", work_type_="new_line", voltage_kv=230, line_miles=4.2, reference_year=2026))
    print(predict_cost("line", "new_line", 230, 4.2))
    # A Dominion rebuild due end of 2026
    print(predict_duration("line", "rebuild", 115, None, "2026-12-31"))
