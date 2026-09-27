# Open questions

Each item lists the conservative default we built. Questions 1–4 are for Sperry; the rest are decisions made during the build that the team should know about.

## For Sperry

1. **Official distance rule.** Center-point haversine under 25 mi (the Finding Real Locations guide), or closest-point 40 km with tiers (another version of the brief)?
   **Default:** center-point < 25 mi decides what counts as an overlap and is the ranked list. Closest-point distance and tiers are shown as extra information.
2. **Do GTC / MEAG / DU rows in Georgia Power's Table 2 count as Georgia Power projects?**
   **Default:** no. Only `GPC` and `SAV` sponsors (`GPC_SPONSORS_INCLUDED` in `pipeline/parse_gpc.py`). The other 70 rows stay in `data/review/parsed_gpc.csv` with `included: false`.
3. **Projects whose in-service date has passed.**
   **Default:** included, flagged `POSSIBLY_COMPLETE`.
4. **Is there a newer DESC project list (SERTP) than the 2024–2028 PDF?**
   **Default:** we use the provided PDF.

## Build decisions

5. **`source` field conflict.** The spec asks for `"source": "public_filing"` on every project, but the contract already defines `source` as `{document, page}`. The contract wins: origin is stored as `source.type` (`public_filing` | `user`). `GET /projects?source=` filters on it.
6. **Phased in-service date.** DESC project 34 (Dawson 230kV) lists `10/1/2025 (phase 1) and 10/1/2026 (phase 2)`. We use the final phase date (it is in the filing) and add the flag `MULTI_PHASE_DATE`, instead of dropping the date to `null`.
7. **Wrong OSM matches rejected after matching.** The provided matcher (`fetch_substations.py`, logic unchanged) uses `token_set_ratio`, which scores a subset as 100 (`NORTH SPA` → "North Substation") and accepts weak fuzzy hits (`Riverport` → "Airport Substation"). Those produced false overlaps. `pipeline/locate.py` now also requires the whole normalized names to agree (`token_sort_ratio ≥ 80`); otherwise the endpoint is `not_found` and the rejected candidate goes to the review sheet. This is why 77 of 182 projects have no located endpoint.
8. **Endpoints in the wrong state.** The GA OSM extract extends into SC, so Atlanta-area names matched SC substations (e.g. `BUZZARD ROOST` → Buzzard Roost Dam, Greenwood SC). An endpoint in the other state is rejected unless it is in the 60 km border band **and** (for GPC) the project has a Savannah/Augusta region hint (SAV prefix, zone 219 or 215). Cross-river tie lines like McIntosh–Purrysburg still work.
9. **Endpoint splitter additions.** Besides the spec's work words we also cut at: a colon, `Relay`, `Modernization`, `Installation`, `Statcom`, `Capacitor`, `Equipment`, `Improvements`, `Replacement`, `Removal`, `Protective`, `Bank`, `Transformer`, `Strategic`, `Area`, and the GPC prefixes `CC - ` / `GRID - `. Separators after the first colon (e.g. `Edenwood Sub: #1 & #2 Autobanks`) do not trigger `MULTI_SEGMENT`. All 9 spec test cases still pass.
10. **Answer-key data vs real data.** Sperry's starter IDs (`DESC_1..5`, `GPC_1..5`) are not the real IDs (`DESC_<page>`, `GPC_<TEAMS>`). The answer-key test runs on the starter workbook; the real build reproduces the same pairs (e.g. Jasper–Okatie ↔ McIntosh–Purrysburg is `OVL_DESC_23__GPC_20277`, rank 1). Jasper's OSM point is 0.18 km from Sperry's, so that pair is 5.66 mi instead of 5.65.
11. **Overlap IDs** are `OVL_<a>__<b>` (stable across rebuilds), not the mock's `OVL_1..6`. The frontend must not hard-code overlap IDs.
12. **Duplicate-looking projects.** `DESC_14`/`DESC_15` (both "Stevens Creek – Hooks") and `GPC_20793`/`GPC_20794` (Evans–Thurmond #5 and #6) are separate filing entries, so both are kept. Their labels look identical.
13. **Tier beyond 40 km.** A pair can be under 25 mi center to center (40.23 km) while the closest points are just over 40 km. The tier is then `null`. With line centers on the lines this is a 0.23 km window and does not occur in the current data.
14. **User overlaps on public projects.** Public projects keep `overlap_ids` = Sperry's cross-utility overlaps only, so the official list and `has_overlap` filter do not change when users add projects. User-project overlaps involving a public project are listed in the additive `user_overlap_ids`.
15. **`GET /overlaps` default.** Returns both kinds (spec). The ranked list for Sperry should call `GET /overlaps?kind=cross_utility`.
16. **`/ask` intent pages.** The agent's pages include `projects` and `messages`, which are not in the contract's page list. `/ask` maps `projects` → `map` and returns `{action: "none"}` for `messages`. `/agent/chat` (new endpoint) returns the agent's page names unchanged.
17. **Demo seed data.** The frontend's `data/challenge.js` / `app.js` are not in this repo, so the demo resources, jobs and conversation in `db/seed.py` were written to match the spec's list (bucket trucks, 60-ton crane, lineworkers; transmission lineworker, substation electrician, bucket truck operator). Sync names and dates with the frontend's demo data if they differ. Phone numbers use the fictional 555-01xx range.
18. **Job pay unit.** `pay_min`/`pay_max` are treated as hourly (`$38–$46/hr`).
19. **pdftotext.** The parsing rules need poppler's `pdftotext`. The xpdf 4.x build that ships with Git for Windows scrambles the DESC cost rows. `pipeline/pdftext.py` looks for `PDFTOTEXT`, then `backend/.tools/poppler`, then `PATH`.

## Spec update 2 (sourced costs, traffic, contracts)

20. **Source values that differ from the spec draft.** Checked against the documents on 2026-09-26 (`config/cost_sources.json`):
    - USDA NASS 2026 farm real estate: South Carolina is **$4,900/acre**, not $3,950 (Georgia $4,950 matches).
    - MISO per-mile costs are by state and have no Georgia or South Carolina row. We use the **Mississippi** row (nearest Southeast state): 115 kV $2.2M, 138 kV $2.3M, 230 kV $2.6M, 500 kV $5.0M per mile. These are new single-circuit costs, so they likely overstate rebuilds and reconductors. Always labeled "estimated (MISO per-mile)".
    - USDOT value of time: the 2026 BCA PDF blocks automated downloads, so the federal values come from the Caltrans Cal-B/C 2026 federal comparison: **$29.15 per vehicle-hour** all-purpose (2024 dollars), applied per vehicle (occupancy 1.0).
    - BLS OEWS 2025 lineworker mean wage: GA $39.37/h, SC $36.25/h (BLS API).
    - USACE EP 1110-1-8 lists rates by make and model; no generic bucket truck value was pinned down, so `verified: false` and the sandbox keeps its default truck rate.
21. **Traffic counts.** South Carolina uses SCDOT's own 2025 statewide stations (route-matched). The newest public GDOT station layer we could reach is 2017 AADT with no route field; a GDOT station is used only when the crossed road is the road the station sits on. Otherwise the road-class estimate is used and labeled. Interstate stations are sparse, so on motorways a same-route station up to 8 km away is accepted (2 km elsewhere).
22. **Logistics sign.** With the spec's assumptions (contractor base 25–100 mi from site, road miles = 1.2 × straight line), the site-to-site haul beats the base haul only beyond about 42 mi at the point estimate. Within the 25-mile overlap threshold only the low end of the range goes negative. Kept as is (honest).
23. **Logistics and mobilization need timing.** Both are counted only when windows overlap or a ±12-month shift makes them overlap (halved for mobilization when only a shift works). Sharing equipment is impossible otherwise.
24. **Traffic delay component.** Merging two closures often changes delay very little (each closure's best window is overnight), so this component is mostly the avoided traffic-control setup (2 flaggers × closure hours × BLS wage). Shown as 50–150% of the point estimate.
25. **Typed roads vs line crossings.** A road a user or contract lists that its line already crosses counts once (the line crossing), not twice.
26. **Contracts without a database** are kept in memory (lost on restart) so the upload demo works in read-only mode.
27. **Sample contract.** `data/samples/sample_contract_hardeeville.pdf` was not provided, so `scripts/make_sample_contract.py` generates a clearly fictional one (Jasper–Bluffton 115 kV rebuild through Hardeeville).
28. **Site focus.** `GET /overlaps?project_id=` returns every opportunity a site is part of. The frontend's map uses it when a site is selected: the list re-ranks to that site's partners and opens the best one.

## ML integration (ml/ML_README.md step U6)

29. **Where predictions are used.** Dominion start dates (filing has none) and redacted Georgia Power line budgets in the pipeline; missing start dates and missing budgets on `POST /projects` and contract upload. Dates and budgets from a filing, contract or user are never replaced. The spending-years start is kept only as a sanity check (`WINDOW_DISAGREEMENT` when more than 24 months apart; 3 projects).
30. **Budgets predicted only for transmission work.** On `POST /projects` a missing budget is predicted only when `voltage_kv` is given; on contracts, when a voltage is stated or the work runs between two substations. Road work gets no predicted transmission budget.
31. **Equipment work on lines.** ML_README says to predict every GPC *line* project, so equipment work on a line (e.g. McIntosh–Purrysburg reactors) now gets a predicted budget; the old MISO rule skipped it. MISO per-mile stays as the fallback if the models can't load.
32. **`start_date` is now optional** on `POST /projects` (predicted when missing, never before today). `end_date` is still required. This relaxes validation; no existing request breaks.
33. **Model features** are computed with the same rules as `ml/build_datasets.py` (verified identical on all 252 training rows).
34. **scikit-learn is pinned to 1.8.0**, the version the models were saved with; newer versions warn the pickles may give invalid results.
