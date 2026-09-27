# Gridlock ML: What We Trained, Why, and How Well It Works

## The one-sentence version
We use machine learning only where the public filings give us **real answers to learn from**: how long Georgia Power projects take (205 projects with filed start and need dates) and what Dominion projects cost (44 filed budgets). The models fill gaps in the data. Every prediction is labeled "predicted," shows a range, and is only used if the model beats a simple guess on held-out data.

## Why not use ML to rank the opportunities?
A ranking model needs examples of coordinations that actually happened (or didn't). That data doesn't exist yet. Training on labels we generate ourselves would just teach the model to copy our own formula, a circular setup that looks like ML but adds nothing. So the ranking stays an explainable expected-value calculation, and the app **collects planner feedback** (👍/👎, "we contacted them") so a ranking model can be trained once real outcomes exist.

## Model 1: Construction duration
- **Question:** when a project's start date is missing, how long before its in-service date does it start?
- **Data:** Georgia Power 2024 ten-year plan, detail pages. 208 projects with a Start Date and a Need Date. **3 were excluded** because their start was on or after their need date (data errors, listed in `metrics.json`). 205 used.
- **Target:** months from start to need date. Median 36, spread 18.
- **Features:** project type (line or substation), work type (rebuild, new line, reconductor, relay, breaker/switch, transformer, reactive equipment, tap, upgrade, other), voltage, line miles (when stated), and **years ahead** (need year minus the year the plan was made).
- **Model:** random forest, kept small (300 trees, max depth 4, at least 5 projects per leaf).
- **Validation:** 5-fold cross-validation, repeated 10 times.
- **Result:** average error **11.2 months vs 13.0 for the median guess, 14% better.** Typical (median) error 8.5 months.
- **Used for:** Dominion projects (their filing has no start dates) and uploaded contracts without a start date. **Never overrides a date that's in a document.** Predicted starts for new projects are never set before today.
- **Honest limits:**
  - The filed "Start Date" is the project start, which includes engineering. So this predicts the planned project window, not only field-construction time.
  - It's trained on Georgia Power and applied to Dominion, a different utility.
  - The learning curve is flat: more rows of the same kind of data help little. **What would help is better information**, like actual construction start and finish dates, which the app would collect from contractors over time.

## Model 2: Project cost
- **Question:** what does a project probably cost when its budget is hidden (Georgia Power's costs are redacted)?
- **Data:** Dominion Energy SC's "$2M and above" project descriptions, 44 projects with filed total costs ($1.1M to $93.5M, median $10.0M).
- **Features:** the same as above, minus years ahead.
- **Model:** ridge regression on log(cost), a deliberately simple choice for 44 examples.
- **Validation:** 5-fold cross-validation, repeated 10 times.
- **Result:** typical error **47% vs 65% for the best simple guess**. On the 14 line projects whose length is stated, **27% vs 74% for the MISO per-mile estimate**, so the model beats a published industry cost guide on local projects.
- **Used for:** Georgia Power budgets (redacted), and uploaded contracts with no budget. **Never overrides a real budget.**
- **Honest limits:**
  - 44 projects is very small, and the typical error is still large. That's why we always show a range.
  - It's trained on Dominion (SC) and applied to Georgia Power (GA).
  - The learning curve is **still improving** (69% error with 10 projects → about 50% with 25–34), so more projects would help this model directly.

## "Will it get smarter with more data?" What we can actually show
See `learning_curves.png`:
- **Cost model: yes.** Error keeps falling as it sees more projects. More filings (other utilities, other years) or contractors' real contract values would improve it.
- **Duration model: only with better data, not just more of the same.** Its curve has leveled off. The next step is actual construction dates, which the app collects as contractors upload contracts and report progress.
- **Ranking: yes, once outcomes exist.** The feedback buttons create the labels a ranking model needs.

## What to say to the judges (30 seconds)
> "We only used ML where the filings contain real answers. Georgia Power published start and need dates for 205 projects, so we trained a duration model. It's 14% more accurate than a simple guess, and we use it to fill in Dominion's missing start dates. Dominion published 44 budgets, so we trained a cost model to estimate Georgia Power's redacted budgets. On local projects it beats MISO's published per-mile guide, 27% error vs 74%. Every prediction is labeled and shows its range. We didn't train a ranking model, because nobody has data on which coordinations actually happened, and training on our own formula would be circular. Instead we collect planner feedback, so that model can be learned from real outcomes."

**Questions they might ask:**
- *"Why not deep learning?"* 205 and 44 rows. Anything bigger would memorize the data. We picked the simplest model that beat the baseline.
- *"How do you know it works?"* Repeated cross-validation against baselines. The numbers are in `metrics.json`, and the pipeline automatically falls back to the baseline if the model doesn't win.
- *"What would make it better?"* Actual construction dates and actual costs from completed projects, and coordination outcomes for the ranking.

## Files
| File | What |
|---|---|
| `build_datasets.py` | Builds the training data from the two filings (`pdftotext -layout` output) |
| `gpc_duration.csv` | 208 Georgia Power projects: features + start/need dates + duration |
| `desc_cost.csv` | 44 Dominion projects: features + total cost |
| `train_models.py` | Trains, cross-validates against baselines, saves models + `metrics.json` |
| `learning_curve.py`, `learning_curves.json`, `learning_curves.png` | Evidence for "more data helps" |
| `duration_model.joblib`, `cost_model_log.joblib` | Trained models |
| `predict.py` | Backend helpers: `predict_duration`, `predict_start_date`, `predict_cost` (each returns value, range, method, label) |
| `metrics.json` | Every result, the excluded rows, prediction intervals |

Rebuild everything:
```bash
pdftotext -layout data/raw/gpc_irp_vol3.pdf gpc.txt
pdftotext -layout data/raw/desc_projects.pdf desc.txt
python build_datasets.py gpc.txt desc.txt
python train_models.py
python learning_curve.py
```

---

## For Claude Code: integration (step U6)
Add this after U1–U5 in `SPEC_UPDATE_2.md`.

1. Copy this folder to `backend/ml/`. Add `scikit-learn`, `joblib`, `pandas` to requirements. Load `predict.py` once at startup.
2. **Duration:**
   - For every DESC project, set `construction_window.start` from `predict_start_date(need_date=in_service_date, project_type, work_type, voltage_kv, line_miles, reference_year=2024)`. Set `construction_window.source = "predicted"` and add `construction_window.prediction = {low, high, typical_error_months, method, trained_on}`.
   - This replaces the "DESC spend years" rule (main spec §6.4) for the **start** date. Keep the spend-years start as a sanity check: if the two differ by more than 24 months, add quality flag `WINDOW_DISAGREEMENT`.
   - For uploaded contracts or user projects without a start date: `predict_start_date(..., reference_year=<current year>, not_before=<today>)`.
   - **Never** replace a start date that appears in a document.
3. **Cost:**
   - For GPC projects (redacted) with `project_type == "line"`: `budget_usd = predict_cost(...)`, `budget_source = "predicted (ridge, Dominion budgets)"`, and keep `budget_range_usd = [low, high]`. This replaces the MISO per-mile estimate in U2.2, because the model beat it in validation (27% vs 74% median error).
   - Keep MISO per-mile as a fallback only if the model file fails to load.
   - For uploaded contracts without a budget: the same.
   - **Never** replace a budget from a filing or a contract.
4. **Propagate uncertainty:** the savings range (U2) uses the budget low/high when the budget is predicted. The timing factor uses the predicted window, with `timing_confidence: "predicted"`. Frontend labels: "predicted" next to any predicted date or budget.
5. **Feedback (for a future ranking model):**
   - Add `POST /overlaps/{id}/feedback` with body `{useful: true|false, contacted?: bool, note?}` → store in a `feedback` collection `{overlap_id, company_id, useful, contacted, note, ts}` and emit an event.
   - Add `GET /ml/status` → `{duration: metrics.duration summary, cost: metrics.cost summary, feedback_count, ranking_model: "not trained: needs outcome data", learning_curves: <json>}` for an "About the models" panel.
6. **Tests:** predictions are labeled and have `low <= value <= high`; a document-provided date or budget is never replaced; the start clamp works; `/ml/status` returns the metrics.
