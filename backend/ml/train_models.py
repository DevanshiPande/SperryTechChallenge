"""
Train and evaluate the two Gridlock models, honestly.
  1) Construction duration (months) from Georgia Power's filed Start/Need dates.
  2) Project cost (USD) from Dominion's filed budgets.
Every model is compared with simple baselines using repeated k-fold cross-validation.
The model is only used if it beats the best baseline. Outputs: metrics.json, *.joblib, predictions.
"""
import json, numpy as np, pandas as pd, joblib
from sklearn.model_selection import RepeatedKFold
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor

SEED = 7
CAT = ["project_type", "work_type"]
NUM = ["voltage_kv", "log_miles", "miles_missing"]
NUM_DUR = NUM + ["years_ahead"]
FILING_YEAR = 2024   # both filings are 2024 plans; for an uploaded contract use the current year

def features(df, with_horizon=False):
    X = df.copy()
    X["log_miles"] = np.log1p(X["line_miles"])
    X["miles_missing"] = X["line_miles"].isna().astype(int)
    if with_horizon:
        X["years_ahead"] = pd.to_datetime(X["need_date"]).dt.year - FILING_YEAR
        return X[CAT + NUM_DUR]
    return X[CAT + NUM]

def make(model, num=None):
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT),
        ("num", SimpleImputer(strategy="median"), num or NUM)])
    return Pipeline([("pre", pre), ("m", model)])

def cv_eval(X, y, build, folds=5, repeats=10, transform=None, inverse=None):
    """Returns out-of-fold predictions averaged over repeats."""
    oof = np.zeros((repeats, len(y)))
    rkf = RepeatedKFold(n_splits=folds, n_repeats=repeats, random_state=SEED)
    for k, (tr, te) in enumerate(rkf.split(X)):
        r = k // folds
        pred = build(X.iloc[tr], y.iloc[tr], X.iloc[te])
        oof[r, te] = pred
    return oof.mean(axis=0)

def fit_predict_pipeline(model, transform=None, inverse=None, num=None):
    def f(Xtr, ytr, Xte):
        m = make(model, num); yt = transform(ytr) if transform else ytr
        m.fit(Xtr, yt); p = m.predict(Xte)
        return inverse(p) if inverse else p
    return f

def median_baseline(Xtr, ytr, Xte): return np.full(len(Xte), np.median(ytr))
def group_median_baseline(Xtr, ytr, Xte):
    med = pd.Series(ytr.values, index=Xtr.index).groupby(Xtr["work_type"]).median()
    return Xte["work_type"].map(med).fillna(np.median(ytr)).values

report = {}

# ================= 1) Duration =================
g = pd.read_csv("gpc_duration.csv")
bad = g[g.duration_months <= 0]
g = g[g.duration_months > 0].reset_index(drop=True)
Xg, yg = features(g, with_horizon=True), g["duration_months"]
cands = {
    "baseline_median": median_baseline,
    "baseline_median_by_work_type": group_median_baseline,
    "ridge": fit_predict_pipeline(Ridge(alpha=3.0), num=NUM_DUR),
    "random_forest": fit_predict_pipeline(RandomForestRegressor(n_estimators=300, max_depth=4, min_samples_leaf=5, random_state=SEED), num=NUM_DUR),
}
res, dur_oof = {}, {}
for name, fn in cands.items():
    p = cv_eval(Xg, yg, fn); dur_oof[name] = p
    res[name] = {"mae_months": round(float(np.mean(np.abs(p - yg))), 2),
                 "median_abs_error_months": round(float(np.median(np.abs(p - yg))), 2)}
best_base = min((k for k in res if k.startswith("baseline")), key=lambda k: res[k]["mae_months"])
best_model = min((k for k in res if not k.startswith("baseline")), key=lambda k: res[k]["mae_months"])
use = best_model if res[best_model]["mae_months"] < res[best_base]["mae_months"] else best_base
improvement = round(100 * (1 - res[best_model]["mae_months"] / res[best_base]["mae_months"]), 1)
final = make(Ridge(alpha=3.0) if best_model == "ridge" else RandomForestRegressor(n_estimators=300, max_depth=4, min_samples_leaf=5, random_state=SEED), NUM_DUR)
final.fit(Xg, yg); joblib.dump(final, "duration_model.joblib")
dur_err = np.abs(dur_oof[use] - yg)
report["duration"] = {
    "target": "months from filed Start Date to Need Date (Georgia Power 10-year plan detail pages)",
    "rows_used": int(len(g)), "rows_excluded_bad_dates": bad[["teams", "title", "start_date", "need_date"]].to_dict("records"),
    "features": CAT + ["voltage_kv", "line_miles (log, with missing flag)", "years_ahead = need year - filing year"],
    "cv": "5-fold, repeated 10 times", "results": res,
    "prediction_interval_months": {"p25_abs_error": round(float(np.percentile(dur_err, 25)), 1), "p50_abs_error": round(float(np.percentile(dur_err, 50)), 1), "p75_abs_error": round(float(np.percentile(dur_err, 75)), 1)},
    "note": "Start Date in the filing is the project start (engineering + construction), so this predicts the planned project window, not field-construction days only.",
    "best_baseline": best_base, "best_model": best_model, "used": use,
    "improvement_over_best_baseline_pct": improvement,
    "target_stats_months": {k: round(float(v), 1) for k, v in yg.describe().items() if k in ("mean", "50%", "std", "min", "max")},
}

# ================= 2) Cost =================
d = pd.read_csv("desc_cost.csv").reset_index(drop=True)
Xd, yd = features(d), d["total_cost_usd"].astype(float)
logf, expf = np.log, np.exp
cands = {
    "baseline_median": median_baseline,
    "baseline_median_by_work_type": group_median_baseline,
    "ridge_log": fit_predict_pipeline(Ridge(alpha=3.0), logf, expf),
    "random_forest_log": fit_predict_pipeline(RandomForestRegressor(n_estimators=300, max_depth=3, min_samples_leaf=4, random_state=SEED), logf, expf),
}
res, oof = {}, {}
for name, fn in cands.items():
    p = cv_eval(Xd, yd, fn); oof[name] = p
    ape = np.abs(p - yd) / yd
    res[name] = {"median_abs_pct_error": round(float(np.median(ape)) * 100, 1),
                 "mae_usd": int(np.mean(np.abs(p - yd))),
                 "within_50pct_share": round(float(np.mean(ape <= 0.5)) * 100, 1)}
# MISO per-mile baseline, only where miles are known (line projects)
MISO = {138: 2_000_000, 230: 2_200_000}
mask = d["line_miles"].notna() & (d["project_type"] == "line")
miso_pred = d.loc[mask].apply(lambda r: r["line_miles"] * MISO[230 if (r["voltage_kv"] or 0) >= 200 else 138], axis=1)
sub = {}
if mask.sum() >= 3:
    ytrue = yd[mask]
    for name in ["baseline_median", "ridge_log", "random_forest_log"]:
        sub[name] = round(float(np.median(np.abs(oof[name][mask] - ytrue) / ytrue)) * 100, 1)
    sub["miso_per_mile"] = round(float(np.median(np.abs(miso_pred - ytrue) / ytrue)) * 100, 1)
best_base = min((k for k in res if k.startswith("baseline")), key=lambda k: res[k]["median_abs_pct_error"])
best_model = min((k for k in res if not k.startswith("baseline")), key=lambda k: res[k]["median_abs_pct_error"])
use = best_model if res[best_model]["median_abs_pct_error"] < res[best_base]["median_abs_pct_error"] else best_base
mdl = Ridge(alpha=3.0) if best_model == "ridge_log" else RandomForestRegressor(n_estimators=300, max_depth=3, min_samples_leaf=4, random_state=SEED)
final = make(mdl); final.fit(Xd, np.log(yd)); joblib.dump(final, "cost_model_log.joblib")
cost_ape = np.abs(oof[use] - yd) / yd
report["cost"] = {
    "target": "total estimated project cost, Dominion Energy SC filing (44 projects)",
    "rows_used": int(len(d)), "features": CAT + ["voltage_kv", "line_miles (log, with missing flag)"],
    "cv": "5-fold, repeated 10 times; model trained on log(cost)", "results": res,
    "subset_with_known_miles": {"rows": int(mask.sum()), "median_abs_pct_error": sub},
    "best_baseline": best_base, "best_model": best_model, "used": use,
    "prediction_interval_pct": {"p50_abs_pct_error": round(float(np.percentile(cost_ape, 50)) * 100, 1), "p75_abs_pct_error": round(float(np.percentile(cost_ape, 75)) * 100, 1)},
    "caveat": "44 projects is very small; Dominion (SC) costs are used to estimate Georgia Power (GA) projects, a different utility.",
}
json.dump(report, open("metrics.json", "w"), indent=2)
print(json.dumps({k: {kk: v[kk] for kk in ("results", "best_baseline", "best_model", "used")} for k, v in report.items()}, indent=1))
print("cost subset with miles:", report["cost"]["subset_with_known_miles"])
print("duration improvement %:", report["duration"]["improvement_over_best_baseline_pct"])
