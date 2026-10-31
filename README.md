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

## Security

Every push and pull request runs the **Security Scan** workflow (`.github/workflows/security.yml`). Any finding fails the check.

| Scan | What it checks | Why it matters here |
|---|---|---|
| **Gitleaks** (secrets) | Every commit in the full git history for API keys, passwords, tokens and connection strings. | ContractMap holds a Gemini key, a MongoDB Atlas login and a Google Maps key. A leaked Gemini key can run up the bill; a leaked Atlas login exposes every company's listings, jobs and messages. A key deleted in a later commit is still in history, so the whole history is scanned. |
| **Semgrep** (SAST) | The Python, JavaScript, HTML and workflow code against Semgrep's community rules (`--config auto`): injection, unsafe deserialization, insecure transport, missing integrity checks, CI supply-chain mistakes. | Catches insecure patterns before they ship, including in the frontend that opens uploaded PDFs. |
| **pip-audit** (dependencies) | `backend/requirements.txt` against the PyPI/OSV vulnerability databases. | Most of the code that runs is third-party (FastAPI, pymongo, pdfplumber, google-genai...). Pinned versions stay pinned even after a CVE is published. |
| **Trivy** (container image) | Not run: there is no Dockerfile. Render builds ContractMap as a native Python service, so there is no image to scan. Add the job if the app moves to a container. | – |

**Dependabot** (`.github/dependabot.yml`) opens weekly update PRs for the Python packages and the workflow's actions, after a 7-day cooldown on new releases. Actions are pinned to commit SHAs.

### Before and after

The first scan found **2 vulnerable dependencies, 4 code issues and 1 real secret** (plus 23 false-positive secret matches and 8 issues in the new CI config). A manual review found **1 more**, in the PDF library the frontend loads from a CDN. All were fixed or documented; every scan now passes. Full details: [`SECURITY_FINDINGS.md`](SECURITY_FINDINGS.md).

| | Before | After | What was done |
|---|---|---|---|
| Secrets (Gitleaks) | 1 real (Gemini key + MongoDB URI in a never-pushed local stash), 23 false positives | 0 | Both credentials rotated, stash dropped, `.gitignore` hardened at the repo root |
| Vulnerable dependencies (pip-audit) | 2 High: pymongo 4.18.2, dnspython 2.8.0 | 0 | Upgraded to 4.18.3 and 2.9.0; 171 tests pass |
| Code issues (Semgrep) | 4 (1 real, 3 false positives) + 8 in the new CI config | 0 | Subresource Integrity on pdf.js; false positives annotated inline; actions pinned to SHAs; Dependabot cooldown |
| Manual review | 1 High: pdf.js CVE-2024-4367 | 0 | `isEvalSupported: false` when opening uploaded PDFs |

### Threat model

STRIDE categories: **S**poofing, **T**ampering, **R**epudiation, **I**nformation disclosure, **D**enial of service, **E**levation of privilege.

| Threat | STRIDE | Risk | Current mitigation | Recommended next step |
|---|---|---|---|---|
| **Malicious file upload.** A crafted PDF sent to `POST /contracts/analyze` or opened in the browser. | T, D, E | Parser bugs, script running in the page (pdf.js CVE-2024-4367), or a huge PDF tying up the server. | Server: 10 MB cap, `%PDF` magic-byte check, text-only extraction with pdfplumber, the file is never stored (only a hash and the extracted fields). Browser: pdf.js loaded with an SRI hash and `isEvalSupported: false`. pip-audit tracks pdfplumber/pdfminer CVEs. | Cap the page count and the parse time (run extraction in a worker with a timeout); upgrade pdf.js to 4.x or newer. |
| **Prompt injection through contract text.** The uploaded text is pasted into the Gemini extraction prompt, so a contract can say "ignore previous instructions...". | T, I | Wrong or planted field values saved as a project. | The extraction call has no tools, so injected text cannot act. Its output must match a JSON schema. Each field must quote an evidence snippet that code finds in the document, and every number must appear in that snippet; anything else is dropped. A person reviews every field before saving. | Wrap the contract in clear delimiters and tell the model it is untrusted data. Flag text that looks like instructions to the model. Keep the review step required. |
| **Abuse of the function-calling assistant.** A user (or injected text the assistant reads) tries to get it to change data or reach other companies' data. | T, E, I | Unwanted creates/updates/deletes, or reading another company's records. | **Approval gate:** write tools never run from chat; they create a pending action with a summary and preview. The change only happens after `POST /agent/actions/{id}/confirm`, which checks the action belongs to the caller's company, is still pending (single use) and under 30 minutes old, and re-validates the arguments. Threads and actions are scoped per company; at most 5 model turns per message; replies are checked so cited numbers and IDs must exist. | The gate stops the *model* from changing data, but it relies on knowing who the caller is (see next row). Add rate limits per caller on `/agent/chat` and the Gemini routes to protect the Gemini quota. |
| **Spoofed identity.** Callers pick a demo company with the `X-Company-Id` header; there is no real login. | S, E, R | Anyone can act as any company: see its inventory, threads and messages, make changes as it, and confirm its pending actions if they know the action ID (6 random characters). | It is a demo with seeded demo companies; the README states there is no real login. | Add real authentication (e.g. OAuth or signed sessions) and take the company from the session, not a header. Log who confirmed each action. |
| **Exposed secrets.** Gemini key, MongoDB URI, Maps key. | I | Bill abuse on the Gemini key; full read/write of the database with the Atlas login. | Secrets live only in environment variables (Render `sync: false`, local `backend/.env`, git-ignored at every level). Gitleaks scans full history on every push. The one leak found was in a never-pushed local stash and has been rotated. The Maps key is served to the browser on purpose (`/config.js`). | Restrict the Maps key to the site's HTTP referrer and the Maps JavaScript API. Restrict the Gemini key to the Generative Language API. Use a least-privilege Atlas user. Add a pre-commit Gitleaks hook so secrets are caught before they are committed. |
| **Dependency and supply-chain risk.** A vulnerable or malicious package, CDN script or CI action. | T, E | Known CVEs in pinned packages; a hijacked release or action running in CI or production. | Exact version pins; pip-audit in CI; Dependabot with a 7-day cooldown; actions pinned to commit SHAs; gitleaks binary verified by checksum; SRI on the CDN script. | Pin transitive dependencies with hashes (`pip-compile --generate-hashes`, then `pip install --require-hashes`). Treat the committed `.joblib` model files as code: they are loaded with joblib (pickle), so only load files this repo produced. |

## Team

Built at ShellHacks 2026 by **@DevanshiPande**, **@jasminek12**, **@Lavanya275** and **@aadraxe**.

Landing-page map: [USGS The National Map](https://www.usgs.gov/programs/national-geospatial-program/national-map). Map data © Google and OpenStreetMap contributors.
