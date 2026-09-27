# ContractMap

**Every utility project. One shared map.**

ContractMap puts the planned transmission work of **Dominion Energy South Carolina** and **Georgia Power** on one map, finds the projects that are close enough to coordinate, and shows contractors what working together would save, when to do road work, and who has the equipment and crews they need.

Built for the **Sperry Tech "Gridlock" challenge** at ShellHacks 2026.

**Live demo:** https://contractmap.onrender.com

---

## What it does

| | |
|---|---|
| **Upload a contract** | Drop in a contract PDF. Gemini reads it and fills in the project details (name, location, dates, voltage, budget, equipment, roads affected). You review every field before saving. Missing start/end dates and budgets are predicted by our ML models and clearly labeled *predicted*. |
| **Explore the map** | All 182 public projects on Google Maps, and the **55 Dominion ↔ Georgia Power pairs** that are within 25 miles of each other, ranked by a coordination score. Click any pin to see that project's ranked partners and details. |
| **Traffic & timing** | For any project: the roads its line crosses, predicted congestion if a lane is closed (heavy / moderate / light), the crossroads that absorb the backup, and a plain-English **best time to do the work**, from real traffic counts and other construction nearby. |
| **Cost comparison** | Estimated savings from coordinating a pair (shared mobilization, logistics, shared right-of-way, one road closure instead of two), with a low–likely–high range and the sources behind every number. |
| **Inventory** | Contractors list equipment and crews. For the selected project, ContractMap works out **what it needs**, uses your own equipment first, then suggests other companies' listings that fill the gaps, and shows what is still missing. |
| **Staffing & jobs** | Contractors post jobs; workers search, save and apply, and get a confirmation. |
| **Assistant** | Ask questions in plain English ("What could these projects share?"). Any change it proposes waits for your confirmation. |

## How it works

### The rule that shapes everything
**Numbers come from code, words come from Gemini.** Distances, dates, scores, savings and congestion levels are computed by deterministic code. Gemini reads messy PDFs, writes summaries and understands requests, and everything it returns is checked: a number it writes must appear in the facts it was given, a road or record it names must exist, and anything it wants to change needs the user's OK. If Gemini is unavailable, template text is used instead.

### Data
- **Dominion Energy SC** 10-year transmission plan and **Georgia Power** IRP Technical Appendix, Volume 3 (both PDFs), parsed into 182 projects (44 Dominion, 138 Georgia Power). Substations are located with OpenStreetMap.
- The **starter workbook** from the challenge (`Projects_Overlaps.xlsx`): our results include all of its overlaps (checked by the tests), and the Excel export keeps its template columns.
- **Roads** from OpenStreetMap; **traffic counts** from SCDOT (2025) and GDOT.
- **Cost inputs** with sources: MoDOT (mobilization, work-zone capacity), ATRI (trucking cost per mile), BLS (wages), USDA (land values), USDOT (value of time). All listed in `backend/config/cost_sources.json`.

### Matching and ranking
- Two projects **match** when their closest points (edge to edge) are under **25 miles**, the distance crews and equipment actually travel. Sperry's original center-to-center rule is kept alongside: every pair under Sperry's rule is included, and the export marks which pairs meet it.
- **Coordination score (0–100)** = proximity (40, what they can share at that distance) + savings (40, relative to the smaller budget) + timing (20, months of overlapping construction).

### Traffic
For each road a project's line crosses, a work-zone **queue model** (MoDOT lane capacities, a typical hourly traffic profile) predicts the backups from a daytime lane closure and finds the window with the least delay. Results are stored in the database, so the map loads them instantly; a newly uploaded project is computed right after it is saved.

### Machine learning
- **Construction duration** (random forest, trained on 205 Georgia Power projects with filed start and in-service dates): fills in a missing start or end date. Typical error about 8.5 months.
- **Project cost** (ridge regression on log cost, trained on Dominion's 44 filed budgets): fills in Georgia Power's redacted budgets and missing contract budgets. Typical error about 47%.
- Both are cross-validated (5-fold, repeated 10 times) and beat simple baselines. Every prediction is shown with its range and labeled *predicted*. Details in `backend/ml/ML_README.md`; live metrics at `GET /ml/status`.

---

## Run it locally

**Requirements:** Python 3.11+. Optional: a MongoDB Atlas database, a Gemini API key, a Google Maps JavaScript API key.

### 1. Backend (port 8000)
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env, then fill in the keys
uvicorn api.main:app --port 8000
```

`backend/.env`:

| Variable | What it is |
|---|---|
| `MONGO_URI` | MongoDB Atlas connection string. Without it the app runs read-only (the map, pairs, cost and traffic still work). |
| `MONGO_DB` | Database name (default `gridlock`). On first start the challenge data and a demo setup (3 companies, a worker, listings, jobs) are created automatically. |
| `GEMINI_API_KEY` | Enables contract reading, summaries and the assistant. Without it, template text is used. |
| `NOMINATIM_EMAIL` | Contact email for OpenStreetMap address lookup. |

Check it: http://localhost:8000/health should return `{"status":"ok","db":"connected"}`.

### 2. Frontend (port 5500)
```bash
cd frontend
copy config.example.js config.js   # macOS/Linux: cp; then paste your Google Maps key
python -m http.server 5500
```
Open **http://localhost:5500** for the landing page, or **http://localhost:5500/app.html** to go straight to the app. The app talks to `http://localhost:8000` by default (set `apiUrl` in `config.js` to change it). Without a Maps key the app shows a schematic map instead.

`backend/.env` and `frontend/config.js` hold keys and are **git-ignored**. Never commit them.

### 3. Tests
```bash
cd backend
python -m pytest -q
```
171 tests covering the challenge's answer key, the PDF parsers, matching, the score, the cost model, traffic and congestion, ML predictions, contract upload, inventory suggestions and the API contract.

---

## Project layout

```
frontend/
  index.html          landing page (3D map of the matches)
  app.html            the app
  app.js              pages and interactions
  backend.js          connects the pages to the API
  gmap.js             Google Maps layer (pins, project lines, congestion roads)
  styles.css
backend/
  api/                FastAPI app and routes
  services/           projects, contracts, congestion, suggestions, needs, jobs, ...
  engine/             pure logic: geometry, matching and score, cost model, traffic queue model, timing
  ai/                 Gemini calls, prompts and output checks
  ml/                 trained models, training scripts, metrics
  pipeline/           offline: PDFs -> projects.json and overlaps.json
  data/               parsed projects and pairs, road network, traffic counts, raw filings
  config/             sourced cost inputs, typical equipment needs
  contract/           API reference (API_README.md) and example responses
  tests/
```

More on the backend, the API and each design decision: `backend/README.md`, `backend/contract/API_README.md`, `backend/OPEN_QUESTIONS.md`.

## Limitations

- Transmission lines are drawn as straight lines between their substations, so road crossings are approximate.
- Dominion's filings have no construction start dates and Georgia Power redacts its budgets, so those values are predictions, shown with ranges.
- Congestion levels are predictions from traffic counts and a queue model, not live traffic.
- There is no real login: you act as a demo contractor or a demo worker.

## Team

Built at ShellHacks 2026 by **@DevanshiPande**, **@jasminek12**, **@Lavanya275** and **@aadraxe**.

Landing-page map: [USGS The National Map](https://www.usgs.gov/programs/national-geospatial-program/national-map). Map data © Google and OpenStreetMap contributors.
