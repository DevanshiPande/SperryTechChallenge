# Gridlock backend

Backend for **Gridlock** (Sperry Tech "Gridlock" challenge, ShellHacks 2026). It reads the public construction plans of **Dominion Energy South Carolina (DESC)** and **Georgia Power (GPC)**, places their projects on the map, and flags where they overlap: any DESC–GPC pair whose center points are under 25 miles apart (Sperry's rule), with the gap between in-service dates.

On top of that it ranks the coordination opportunities, estimates illustrative savings, lets companies add their own projects, share equipment and crews, post jobs and message each other, and has a Gemini assistant that can answer questions and propose changes that the user confirms.

The API contract the frontend uses is `contract/API_README.md`. It is not changed by this backend, only extended (see "New endpoints" at the end of that file).

## The rule that shapes everything

**Numbers come from code, words come from Gemini.** Coordinates, distances, dates, windows, scores, ranks and dollar amounts are computed by deterministic code. Gemini reads messy text, writes explanations and understands requests. Everything Gemini returns is checked: numbers in its text must appear in the facts it was given, IDs must come from tool results, and any write it proposes waits for the user to confirm.

## Quick start

Requires Python 3.11+.

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env            # optional: add GEMINI_API_KEY and MONGO_URI
uvicorn api.main:app --reload --port 8000
```

Then point the frontend at `http://localhost:8000` (`window.GRIDLOCK_API_URL`).

- **No `MONGO_URI`:** read-only mode. The map, overlaps, quality, what-if, briefs and the Excel export work from `data/*.json`. Marketplace, messaging and assistant writes return `503 DB_UNAVAILABLE`.
- **No `GEMINI_API_KEY`:** briefs use a template (`source: "fallback"`); `/draft`, `/scenario/assist`, `/ask` and `/agent/chat` return `503 GEMINI_UNAVAILABLE`. Set `FAKE_GEMINI=1` for deterministic stand-in responses in offline demos.

## Environment variables

| Var | Default | Use |
|---|---|---|
| `MONGO_URI` | none | MongoDB Atlas connection string. Missing = read-only mode |
| `MONGO_DB` | `gridlock` | Database name |
| `GEMINI_API_KEY` | none | Gemini API key |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Model for every Gemini call |
| `GEMINI_TIMEOUT_S` | `20` | Per call; one retry on timeout/5xx |
| `CORS_ORIGINS` | `*` | Comma-separated |
| `NOMINATIM_EMAIL` | none | Contact email in the Nominatim User-Agent |
| `DATA_DIR` | `backend/data` | Where `projects.json` / `overlaps.json` live |
| `FAKE_GEMINI` | `0` | `1` = deterministic stubs (tests, offline demos) |
| `FAKE_GEOCODER` | `0` | `1` = small built-in town list instead of Nominatim (tests) |

## Layout

```
api/        FastAPI app, routers, identity from headers, error handling
engine/     pure functions: geo (haversine, closest distance, tiers), windows, overlaps (pairs, score, rank),
            cost (scenario, estimate, right-of-way acres), whatif, closures, quality flags
pipeline/   offline: parse_desc, parse_gpc, endpoints (name splitting), fetch_substations (OSM matcher, provided),
            locate (matching + checks + review sheet), counties (FCC API), build (writes data/*.json)
ai/         gemini client, prompts, guards (validate), brief/draft/scenario features, agent + tools, fakes
services/   business logic shared by REST and the agent: projects, resources + reservations, jobs, messages,
            events, geocode, identity
db/         Mongo connection, indexes, counters, idempotent seed
data/       raw PDFs + answer key, OSM cache, overrides.csv, projects.json, overlaps.json, county_cache.json,
            review/ (parsed CSVs and the location review sheet)
tests/      pytest suite (runs offline, no Mongo or Gemini needed)
scripts/    capture_examples.py: records real responses of the new endpoints into contract/examples/
```

## The data pipeline (offline)

The API never parses PDFs. The pipeline writes JSON files that are committed.

```bash
python -m pipeline.build            # parse, locate, look up counties (FCC), run the engine, write data/*.json
python -m pipeline.build --offline  # same, counties only from data/county_cache.json
```

It needs poppler's `pdftotext` (see `OPEN_QUESTIONS.md` #19) and the cached OSM extracts in `data/osm_cache/` (`python pipeline/fetch_substations.py` refreshes them from Overpass).

Steps:
1. **Parse.** `parse_desc.py` splits the DESC PDF on `Project N of 44` (44 projects, costs by year). `parse_gpc.py` reads Table 2 of the GA ITS Ten-Year Plan (208 rows) and the 208 project detail pages, joined on TEAMS number. Only `GPC` and `SAV` sponsors are Georgia Power (138 projects).
2. **Split names.** `endpoints.py` turns `SAV: GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD` into `GOSHEN (SAV)`, `MCINTOSH`, 115 kV. Names it can't split go to a Gemini fallback whose answer is accepted only if each name appears in the title.
3. **Locate.** The provided OSM matcher (overrides, fuzzy names, Savannah/Augusta region anchors, sibling anchor, ambiguity checks), then two extra checks: the matched name must agree with the endpoint name, and an endpoint in the other state must be a cross-river tie in the border band.
4. **Review.** `data/review/locations_to_review.csv` lists every non-high-confidence endpoint near the Savannah River. Fill `override_lat`/`override_lon`, copy the rows into `data/overrides.csv` and rebuild.
5. **Build.** Counties from the FCC Area API, construction windows (GPC start dates, DESC spend years), quality flags, then the engine: every DESC × GPC pair under 25 mi, ranked.

Current output: 182 projects (44 DESC, 138 GPC), 53 cross-utility overlaps. #1 is Jasper–Okatie ↔ McIntosh–Purrysburg (5.66 mi, 24 months of overlapping construction).

## Overlaps, score and cost

- **Overlap:** center-point haversine < 25 mi (Sperry). Public pairs are always DESC × GPC. A user project is compared with every project that has a different owner.
- **Closest distance** in UTM 17N and **tier:** crossing (≤ 0.05 km), shared_land (< 1.6), shared_site (< 8), shared_crews (< 40).
- **Score** = tier base × (1 − min(closest km, 40)/80) + min(window overlap months, 24)/24 × 40. Potential: high ≥ 60, moderate ≥ 35. Ranked within each kind.
- **Cost scenario:** illustrative placeholder unit rates (mobilization $3,000, bucket truck $1,500/day, laydown $5,000). The frontend recomputes it live with the same formula.

## Identity (no real login)

Send `X-Company-Id: CMP_A` (or `CMP_B`, `CMP_C`) to act as a demo company, `X-Worker-Id: WRK_1` to act as the demo worker. `GET /companies` lists them. Without a header you are a read-only guest.

## Tests

```bash
python -m pytest tests -q
```

Offline and self-contained: Mongo is replaced by mongomock, Gemini by scripted fakes, Nominatim by a small gazetteer. The most important test is `tests/test_answer_key.py`: Sperry's 10 starter projects must give exactly Sperry's 6 overlaps with the right distances and time gaps. `tests/test_contract.py` checks every response in `contract/examples/` against the real API.

## Deploy (Render + MongoDB Atlas)

1. Create a free Atlas cluster, a database user, and allow access from anywhere. Copy the `mongodb+srv://...` URI.
2. On Render, create a Blueprint from this repo (`backend/render.yaml`) or a web service with root `backend`, build `pip install -r requirements.txt`, start `uvicorn api.main:app --host 0.0.0.0 --port $PORT`, health check `/health`.
3. Set `MONGO_URI`, `GEMINI_API_KEY` and `NOMINATIM_EMAIL` in Render's environment.
4. On first start the app loads `data/*.json`, connects to Mongo (5 s timeout, read-only mode if it fails) and seeds the demo data if the database is empty.

## Spec update 2: sourced savings, traffic, contracts

- **Score v2:** proximity 40 + savings 40 + timing 20 (`overlap.score_breakdown`).
- **Sourced savings (`cost_estimate` v2):** shared mobilization, hauling, shared right-of-way and traffic delay. Each is a low/point/high range with named sources. Budgets come from Dominion's filings, uploaded contracts, or MISO per-mile estimates for Georgia Power's redacted lines. Every constant lives in `config/cost_sources.json`, with its source and a verified flag.
- **Traffic management (`/traffic/*`):** OSM roads plus SCDOT 2025 / GDOT 2017 traffic counts in `data/traffic/` (refresh with `python -m pipeline.fetch_traffic`). It finds where lines cross roads, picks the best closure window with a work-zone queue model, and flags closures on the same road worth merging.
- **Contract upload (`/contracts/*`):** upload a PDF, get fields with evidence quotes, and see ranked coordination partners with savings ranges and traffic impact. A fictional sample is in `data/samples/` (`python scripts/make_sample_contract.py`).
- `python scripts/capture_examples.py` re-captures every new endpoint into `contract/examples/` and `contract/API_README.md`.
