"""Learning curves: does error keep dropping as we add projects? Evidence for 'more data -> better model'."""
import json, numpy as np, pandas as pd
from sklearn.model_selection import KFold
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
import train_models as T   # reuses features/make (runs training once on import; that's fine)

rng = np.random.default_rng(7)
def curve(X, y, build_model, sizes, metric, transform=None, inverse=None, reps=30):
    out = []
    for n in sizes:
        errs, base_errs = [], []
        for r in range(reps):
            idx = rng.permutation(len(y)); test = idx[:max(10, len(y)//5)]; pool = idx[len(test):]
            tr = rng.choice(pool, size=min(n, len(pool)), replace=False)
            m = build_model(); yt = transform(y.iloc[tr]) if transform else y.iloc[tr]
            m.fit(X.iloc[tr], yt); p = m.predict(X.iloc[test]); p = inverse(p) if inverse else p
            errs.append(metric(p, y.iloc[test].values))
            base_errs.append(metric(np.full(len(test), np.median(y.iloc[tr])), y.iloc[test].values))
        out.append({"train_size": int(n), "model_error": round(float(np.mean(errs)), 2), "baseline_error": round(float(np.mean(base_errs)), 2)})
    return out

g = pd.read_csv("gpc_duration.csv"); g = g[g.duration_months > 0].reset_index(drop=True)
Xg, yg = T.features(g, with_horizon=True), g["duration_months"]
dur = curve(Xg, yg, lambda: T.make(RandomForestRegressor(n_estimators=200, max_depth=4, min_samples_leaf=5, random_state=7), T.NUM_DUR),
            [20, 40, 60, 80, 100, 130, 160], lambda p, y: np.mean(np.abs(p - y)))
d = pd.read_csv("desc_cost.csv")
Xd, yd = T.features(d), d["total_cost_usd"].astype(float)
cost = curve(Xd, yd, lambda: T.make(Ridge(alpha=3.0)), [10, 15, 20, 25, 30, 34],
             lambda p, y: np.median(np.abs(p - y) / y) * 100, transform=np.log, inverse=np.exp)
json.dump({"duration_mae_months": dur, "cost_median_abs_pct_error": cost}, open("learning_curves.json", "w"), indent=2)
print("DURATION"); [print(r) for r in dur]; print("COST"); [print(r) for r in cost]
