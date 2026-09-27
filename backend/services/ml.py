"""Bridge to the trained models in ml/ (ML_README.md, step U6).

- Duration model (Georgia Power start->need dates): fills a MISSING start date. Never replaces a date from a document.
- Cost model (Dominion filed budgets): fills a MISSING budget. Never replaces a budget from a filing or a contract.
Every prediction carries label "predicted" and a low/high range.

Model inputs are computed with the same rules the training data used (ml/build_datasets.py), so the models see the
kind of features they were trained on. If the models cannot load, callers fall back (MISO per-mile, spend years)."""
import json
import logging
import re
import sys
import warnings
from datetime import date
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("gridlock.ml")
ML_DIR = Path(__file__).resolve().parents[1] / "ml"
FILING_YEAR = 2024
BUDGET_SOURCE = "predicted (ridge, Dominion budgets)"


@lru_cache(maxsize=1)
def _predict():
    """ml/predict.py, loaded once. None if the models or libraries are unavailable."""
    try:
        if str(ML_DIR) not in sys.path:
            sys.path.insert(0, str(ML_DIR))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            import predict  # noqa: E402  (ml/predict.py)
        return predict
    except Exception as e:  # missing scikit-learn, bad pickle, missing files
        log.warning("ML models unavailable (%s: %s): using non-ML fallbacks", type(e).__name__, e)
        return None


def available():
    return _predict() is not None


def metrics():
    return json.loads((ML_DIR / "metrics.json").read_text(encoding="utf-8"))


# ---- feature rules mirrored from ml/build_datasets.py (the training data) ----
def ml_voltage(text):
    text = re.sub(r"(\d{2})O(\s*kv)", r"\g<1>0\2", text or "", flags=re.I)
    v = []
    for a, b in re.findall(r"(\d{2,3})(?:\s*[-/]\s*(\d{2,3}))?\s*kv", text, re.I):
        v += [int(x) for x in (a, b) if x and 34 <= int(x) <= 765]
    return max(v) if v else None


def ml_miles(text):
    vals = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*(?:miles|mile|mi\b)", text or "", re.I) if 0 < float(x) < 300]
    return round(sum(vals), 2) if vals else None


def ml_project_type(title):
    core = re.split(r"\d{2,3}\s*-?\s*kv", re.sub(r"^[A-Z]{2,5}:\s*", "", title or ""), flags=re.I)[0]
    return "line" if re.search(r"\s[-–]\s|[a-z]-[a-z]", core, re.I) else "substation"


def features(project):
    """Model inputs for a project dict (name, description, voltage_kv, line_miles, project_type)."""
    P = _predict()
    title, desc = project.get("name") or "", project.get("description") or ""
    stated_miles = project.get("line_miles")
    return {"project_type": ml_project_type(title) if P else project.get("project_type"),
            "work_type_": P.work_type(title, desc) if P else "other",
            "voltage_kv": project.get("voltage_kv") or ml_voltage(title) or ml_voltage(desc),
            "line_miles": float(stated_miles) if stated_miles else ml_miles(desc)}


# ---- predictions ----
def predicted_window(project, reference_year=FILING_YEAR, not_before=None):
    """{"start", "prediction": {...}, "flags": [...]} for a project whose start date is missing; None if not possible."""
    P, need = _predict(), project.get("in_service_date")
    if P is None or not need:
        return None
    try:
        r = P.predict_start_date(need_date=need, not_before=not_before, reference_year=reference_year, **features(project))
    except Exception as e:
        log.warning("duration prediction failed for %s: %s", project.get("id"), e)
        return None
    return {"start": r["start_date"], "flags": r["flags"],
            "prediction": {"months": r["months"], "low": r["low"], "high": r["high"],
                           "typical_error_months": r["typical_error_months"], "method": r["method"],
                           "trained_on": r["trained_on"], "label": "predicted"}}


def predicted_budget(project):
    """{"budget_usd", "budget_range_usd", "budget_source", "budget_note", "budget_prediction"} or None."""
    P = _predict()
    if P is None:
        return None
    try:
        f = features(project)
        r = P.predict_cost(f["project_type"], f["work_type_"], f["voltage_kv"], f["line_miles"])
    except Exception as e:
        log.warning("cost prediction failed for %s: %s", project.get("id"), e)
        return None
    return {"budget_usd": r["usd"], "budget_range_usd": [r["low"], r["high"]], "budget_source": BUDGET_SOURCE,
            "budget_note": f"Predicted from {r['trained_on']}; typical error {r['typical_error_pct']}%. "
                           f"Work type: {f['work_type_'].replace('_', ' ')}.",
            "budget_prediction": {"low": r["low"], "high": r["high"], "method": r["method"], "label": "predicted",
                                  "typical_error_pct": r["typical_error_pct"], "trained_on": r["trained_on"]}}


def this_year():
    return date.today().year
