# Gridlock Backend API

This is everything the backend will provide, matched to the screens in the design handoff. You don't have to wait for the backend: a **mock server** in this folder answers every endpoint below with the exact same routes, shapes, filters and errors. Build against it now, and switch to the real backend later by changing the base URL.

## Run the mock (1 minute)

Requires Node 18+. No `npm install`.

```bash
node mock-server.js
# Gridlock mock API on http://localhost:8000
```

Options:
- `PORT=9000 node mock-server.js` to use another port
- `GEMINI_LATENCY_MS=3000 node mock-server.js` to test loading states (default 1500 ms on the Gemini endpoints)
- `MOCK_GEMINI_FAIL=1 node mock-server.js` to test failure handling: briefs come back with `source: "fallback"`, and `/ask`, `/draft` and `/scenario/assist` return a 503

## Connect the existing prototype (5 minutes)

`api-adapter.js` lets the current `app.js` run on the API **without rewriting it**. It fetches projects and overlaps, converts them into the starter-workbook shape `app.js` already reads (`window.GRIDLOCK_CHALLENGE`), keeps every new API field on each record, then loads `app.js`. If the API is down, the app falls back to the bundled `data/challenge.js`.

In `index.html`, replace the `app.js` script tag with:

```html
<script src="data/challenge.js"></script>
<script>window.GRIDLOCK_API_URL = "http://localhost:8000";</script>
<script src="api-adapter.js"></script>
```

It also exposes `window.GridlockAPI` for the new features: `GridlockAPI.draft(kind, text)`, `GridlockAPI.whatif({...})`, `GridlockAPI.brief(id, "plan")`, `GridlockAPI.scenarioAssist(id, message)`, `GridlockAPI.ask(question)`, and the plain getters. Every method returns a promise and throws an `Error` with `.code` and `.status` on API errors.

Tested: the prototype renders with the API's ranked list through the adapter.

## Files

- `mock-server.js`: the mock API
- `mock_api.json`: the data the mock serves
- `api-adapter.js`: connects the design prototype to the API
- `overlaps.xlsx`: served by the export endpoint
- `examples/`: the real response from every endpoint and error case

General: JSON everywhere except the Excel export. CORS is open for local development. Reads are instant; Gemini endpoints take a few seconds.

---

## Screen to endpoint map

| Screen in the prototype | Backend | Endpoint |
|---|---|---|
| Explore map (pins, hover card, ranked list, pair panel) | Real | `GET /projects`, `GET /overlaps?sort=distance` |
| Pair panel: Summarize, Draft coordination plan, Identify risks | Real (Gemini) | `POST /overlaps/{id}/brief` with `mode` |
| Export (opportunities list) | Real | `GET /export/overlaps.xlsx` |
| Project detail (quality flags, road crossings, nearby matches, delete own project) | Real | `GET /projects/{id}`, `GET /overlaps?project_id=`, `DELETE /projects/{id}` |
| My projects, contract upload | Real | `POST /contracts/analyze` → `/match` → `/save`; `POST /projects` when parsed in the browser |
| Cost comparison (inputs, totals) | Real defaults, computed live in the browser | `cost_scenario` on each overlap |
| Cost page assistant ("Try sharing 2 bucket trucks for 5 days", Apply to scenario) | Real (Gemini) | `POST /scenario/assist` |
| Feasibility (nearby projects, schedule suggestion, road crossings, closure conflicts, Save as my project) | Real | `POST /whatif`, `POST /projects` |
| Describe resource / Describe job requirement (chat to draft) | Real (Gemini), local parsing as fallback | `POST /draft` with `kind: "resource"` or `"job"` |
| Inventory: listings, orders, requests (accept, decline, cancel), remove listing | Real | `GET/POST/DELETE /resources`, `POST /resources/{id}/reservations`, `GET/PATCH /reservations` |
| Staffing: postings, applicants (review, accept, reject), close posting | Real | `GET/POST/PATCH /jobs`, `GET/PATCH /applications` |
| Messages: conversations, threads, new conversation with cost-scenario attachment | Real | `GET/POST /conversations`, `GET/POST /conversations/{id}/messages` |
| Worker: find jobs, search, saved jobs, apply, applications, profile | Real | `GET /jobs?q=`, `GET /saved-jobs`, `POST/DELETE /jobs/{id}/save`, `POST /jobs/{id}/applications`, `GET /applications`, `GET/PATCH /me` |
| Acting-as company picker | Real | `GET /companies`; requests send `X-Company-Id` (contractor) or `X-Worker-Id` (worker), never both |
| Live updates from other companies | Real | `GET /events?since=` polled every 15 s |
| Global "Ask Gridlock" bar | Real (Gemini) | `POST /ask` (returns an `intent` to navigate) |
| Data quality | Real | Each project's `quality_flags`, shown on the project detail page (`GET /quality` lists all of them) |

The frontend adapter is `frontend/api-adapter.js`; `contract/api-adapter.js` is the original read-only reference. Every screen falls back to the bundled demo data when `apiUrl` is not set or the API is unreachable.

---

## Endpoints

| Method | Endpoint | Purpose | Example file |
|---|---|---|---|
| GET | `/health` | Server is up | `GET_health.json` |
| GET | `/meta` | Utilities, threshold, tiers, potential levels, year range | `GET_meta.json` |
| GET | `/projects` | All projects | `GET_projects.json` |
| GET | `/projects/{id}` | One project | `GET_project_DESC_3.json` |
| GET | `/overlaps` | Ranked overlaps | `GET_overlaps.json` |
| GET | `/overlaps/{id}` | One overlap, including `cost_scenario` | `GET_overlap_OVL_3.json` |
| GET | `/quality` | All data quality flags | `GET_quality.json` |
| POST | `/whatif` | Nearby projects and schedule suggestion for a proposed project | `POST_whatif.json`, `POST_whatif_location.json` |
| POST | `/overlaps/{id}/brief` | Gemini summary, plan or risks for one overlap | `POST_brief.json`, `POST_brief_plan.json`, `POST_brief_risks.json` |
| POST | `/draft` | Gemini turns free text into a reviewable draft | `POST_draft_project.json`, `POST_draft_resource.json`, `POST_draft_job.json` |
| POST | `/scenario/assist` | Gemini proposes changes to a cost scenario | `POST_scenario_assist.json` |
| POST | `/ask` | Gemini answer plus a navigation intent | `POST_ask.json` |
| GET | `/export/overlaps.xlsx` | Excel in Sperry's template format | `overlaps.xlsx` |

### Query parameters

`GET /projects`
- `utility`: `DESC` or `GPC`
- `confidence`: `high`, `medium`, `low` or `not_found`
- `has_overlap`: `true` or `false`
- `year_from`, `year_to`: in-service year range, e.g. `2025` and `2033`
- `q`: search text, matched against name, short name, utility, counties and endpoint names

`GET /overlaps`
- `max_mi`: number, default `25`
- `tier`: `crossing`, `shared_land`, `shared_site` or `shared_crews`
- `potential`: `high`, `moderate` or `lower`
- `min_window_overlap_months`: number, default `0`
- `year_from`, `year_to`: keeps an overlap if either project's in-service year is in range
- `q`: search text, matched against either project
- `sort`: `score` (default), `distance` or `timeline`

All parameters are optional.

---

## Response examples

These are the **exact** responses the API returns, captured from the mock server. The real backend returns the same shapes; only the values change once the PDFs are parsed. Every file here is also in `examples/`.

### `GET /health`

Response `200`:

```json
{
  "status": "ok"
}
```

---

### `GET /meta`

Load once at startup. Use it for the utility legend, tier labels, potential badges and the year filter range.

Response `200`:

```json
{
  "utilities": [
    {
      "code": "DESC",
      "name": "Dominion Energy South Carolina",
      "color": "#1F6FB2"
    },
    {
      "code": "GPC",
      "name": "Georgia Power",
      "color": "#D9822B"
    }
  ],
  "threshold_mi": 25,
  "generated_at": "2026-09-26",
  "tiers": [
    {
      "code": "crossing",
      "label": "Touching / crossing",
      "max_km": 0.05
    },
    {
      "code": "shared_land",
      "label": "Under 1.6 km",
      "max_km": 1.6
    },
    {
      "code": "shared_site",
      "label": "Under 8 km",
      "max_km": 8
    },
    {
      "code": "shared_crews",
      "label": "Under 40 km",
      "max_km": 40
    }
  ],
  "potential_levels": [
    {
      "code": "high",
      "label": "High potential",
      "min_score": 60
    },
    {
      "code": "moderate",
      "label": "Moderate potential",
      "min_score": 35
    },
    {
      "code": "lower",
      "label": "Lower potential",
      "min_score": 0
    }
  ],
  "in_service_years": [
    2023,
    2033
  ]
}
```

---

### `GET /projects`

Map pins, hover cards, My projects list, project detail. Filters: see Query parameters.

Response `200`:

An **array** (10 items in the mock). First item shown; every item has the same shape.

```json
[
  {
    "id": "DESC_1",
    "utility": "DESC",
    "utility_name": "Dominion Energy South Carolina",
    "state": "SC",
    "name": "Stevens Creek - Hooks 115 kV / LR Plumb Branch 46 kV Rebuilds",
    "voltage_kv": 115,
    "project_type": "line",
    "status": "Planned",
    "in_service_date": "2024-12-31",
    "construction_window": {
      "start": "2023-01-01",
      "end": "2024-12-31",
      "source": "estimated"
    },
    "endpoints": [
      {
        "name": "Stevens Creek Sub",
        "lat": 33.562599,
        "lon": -82.051362,
        "confidence": "high",
        "source": "Sperry starter file",
        "county": "Edgefield County, SC"
      },
      {
        "name": "Hooks Sub",
        "lat": null,
        "lon": null,
        "confidence": "not_found",
        "source": null,
        "county": null
      }
    ],
    "center": {
      "lat": 33.562599,
      "lon": -82.051362
    },
    "geometry": {
      "type": "Point",
      "coordinates": [
        -82.051362,
        33.562599
      ]
    },
    "location_confidence": "medium",
    "description": "(mock) Full description parsed from the utility PDF goes here.",
    "cost": {
      "currency": "USD",
      "by_year": {
        "2024": 800000,
        "2025": 2500000,
        "2026": 0,
        "2027": 0,
        "2028": 0,
        "previous": 1200000
      },
      "total": 4500000,
      "note": "(mock values) Dominion only; Georgia Power costs are redacted"
    },
    "source": {
      "document": "DESC 2024-2028 project descriptions",
      "page": null
    },
    "quality_flags": [
      {
        "code": "ENDPOINT_NOT_FOUND",
        "message": "One endpoint could not be located; center uses the located endpoint only."
      }
    ],
    "overlap_ids": [
      "OVL_1"
    ],
    "short_name": "Stevens Creek–Hooks",
    "work_type_label": "Line rebuild",
    "counties": [
      "Edgefield County, SC"
    ],
    "county_source": "mock (real backend: Census county boundaries)"
  }
]
```

---

### `GET /projects/DESC_3`

Same object as one item of `/projects`.

Response `200`:

```json
{
  "id": "DESC_3",
  "utility": "DESC",
  "utility_name": "Dominion Energy South Carolina",
  "state": "SC",
  "name": "Jasper - Okatie 230 kV #2: Construct",
  "voltage_kv": 230,
  "project_type": "line",
  "status": "Planned",
  "in_service_date": "2025-12-31",
  "construction_window": {
    "start": "2024-01-01",
    "end": "2025-12-31",
    "source": "estimated"
  },
  "endpoints": [
    {
      "name": "Jasper Sub",
      "lat": 32.35912,
      "lon": -81.1246,
      "confidence": "high",
      "source": "Sperry starter file",
      "county": "Jasper County, SC"
    },
    {
      "name": "Okatie Sub",
      "lat": 32.333758,
      "lon": -81.032495,
      "confidence": "high",
      "source": "Sperry starter file",
      "county": "Jasper County, SC"
    }
  ],
  "center": {
    "lat": 32.346439,
    "lon": -81.078547
  },
  "geometry": {
    "type": "LineString",
    "coordinates": [
      [
        -81.1246,
        32.35912
      ],
      [
        -81.032495,
        32.333758
      ]
    ]
  },
  "location_confidence": "high",
  "description": "(mock) Full description parsed from the utility PDF goes here.",
  "cost": {
    "currency": "USD",
    "by_year": {
      "2024": 800000,
      "2025": 2500000,
      "2026": 0,
      "2027": 0,
      "2028": 0,
      "previous": 1200000
    },
    "total": 4500000,
    "note": "(mock values) Dominion only; Georgia Power costs are redacted"
  },
  "source": {
    "document": "DESC 2024-2028 project descriptions",
    "page": null
  },
  "quality_flags": [],
  "overlap_ids": [
    "OVL_3",
    "OVL_4"
  ],
  "short_name": "Jasper–Okatie",
  "work_type_label": "New transmission line",
  "counties": [
    "Jasper County, SC"
  ],
  "county_source": "mock (real backend: Census county boundaries)"
}
```

---

### `GET /overlaps`

Ranked list on the map page (already sorted by `rank`), pair panel, opportunity page, cost page. The first item is the #1 opportunity.

Response `200`:

An **array** (6 items in the mock). First item shown; every item has the same shape.

```json
[
  {
    "id": "OVL_3",
    "project_a": "DESC_3",
    "project_b": "GPC_2",
    "center_distance_mi": 5.65,
    "closest_distance_km": 4.82,
    "closest_points": {
      "a": {
        "lat": 32.35912,
        "lon": -81.1246
      },
      "b": {
        "lat": 32.352116,
        "lon": -81.175112
      }
    },
    "tier": "shared_site",
    "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
    "shared_endpoint": false,
    "time_gap_days": 152,
    "window_overlap_months": 24,
    "score": 77.6,
    "rank": 1,
    "cost_estimate": {
      "shared_row_acres": null,
      "mobilization_savings_usd": null,
      "total_estimated_savings_usd": 17000,
      "assumptions": [
        "Unit rates are placeholders; replace with real bids.",
        "Trucks are shared only when construction windows overlap (yes for this pair).",
        "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
      ]
    },
    "brief": null,
    "label": "Jasper–Okatie ↔ McIntosh–Purrysburg",
    "potential": "high",
    "cost_scenario": {
      "illustrative": true,
      "unit_rates": {
        "mobilization_per_event": 3000,
        "bucket_truck_per_day": 1500,
        "laydown_per_site": 5000
      },
      "separate": {
        "a": {
          "mobilization_events": 1,
          "truck_days": 10,
          "laydown_sites": 1,
          "start_date": "2024-01-01"
        },
        "b": {
          "mobilization_events": 1,
          "truck_days": 10,
          "laydown_sites": 1,
          "start_date": "2024-01-01"
        }
      },
      "coordinated": {
        "mobilization_events_a": 1,
        "mobilization_events_b": 1,
        "shared_truck_days": 12,
        "laydown_sites": 1,
        "start_date_a": "2024-01-01",
        "start_date_b": "2024-01-01"
      },
      "totals": {
        "separate": 46000,
        "coordinated": 29000,
        "savings": 17000,
        "savings_pct": 37,
        "separate_by_project": {
          "a": 23000,
          "b": 23000
        },
        "coordinated_by_project": {
          "a": 14500,
          "b": 14500
        }
      },
      "range": {
        "separate": [
          39100,
          52899
        ],
        "coordinated": [
          24650,
          33350
        ],
        "savings": [
          12750,
          21250
        ]
      },
      "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
      "assumptions": [
        "Unit rates are placeholders; replace with real bids.",
        "Trucks are shared only when construction windows overlap (yes for this pair).",
        "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
      ]
    }
  }
]
```

---

### `GET /overlaps/OVL_3`

Same object as one item of `/overlaps`.

Response `200`:

```json
{
  "id": "OVL_3",
  "project_a": "DESC_3",
  "project_b": "GPC_2",
  "center_distance_mi": 5.65,
  "closest_distance_km": 4.82,
  "closest_points": {
    "a": {
      "lat": 32.35912,
      "lon": -81.1246
    },
    "b": {
      "lat": 32.352116,
      "lon": -81.175112
    }
  },
  "tier": "shared_site",
  "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
  "shared_endpoint": false,
  "time_gap_days": 152,
  "window_overlap_months": 24,
  "score": 77.6,
  "rank": 1,
  "cost_estimate": {
    "shared_row_acres": null,
    "mobilization_savings_usd": null,
    "total_estimated_savings_usd": 17000,
    "assumptions": [
      "Unit rates are placeholders; replace with real bids.",
      "Trucks are shared only when construction windows overlap (yes for this pair).",
      "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
    ]
  },
  "brief": null,
  "label": "Jasper–Okatie ↔ McIntosh–Purrysburg",
  "potential": "high",
  "cost_scenario": {
    "illustrative": true,
    "unit_rates": {
      "mobilization_per_event": 3000,
      "bucket_truck_per_day": 1500,
      "laydown_per_site": 5000
    },
    "separate": {
      "a": {
        "mobilization_events": 1,
        "truck_days": 10,
        "laydown_sites": 1,
        "start_date": "2024-01-01"
      },
      "b": {
        "mobilization_events": 1,
        "truck_days": 10,
        "laydown_sites": 1,
        "start_date": "2024-01-01"
      }
    },
    "coordinated": {
      "mobilization_events_a": 1,
      "mobilization_events_b": 1,
      "shared_truck_days": 12,
      "laydown_sites": 1,
      "start_date_a": "2024-01-01",
      "start_date_b": "2024-01-01"
    },
    "totals": {
      "separate": 46000,
      "coordinated": 29000,
      "savings": 17000,
      "savings_pct": 37,
      "separate_by_project": {
        "a": 23000,
        "b": 23000
      },
      "coordinated_by_project": {
        "a": 14500,
        "b": 14500
      }
    },
    "range": {
      "separate": [
        39100,
        52899
      ],
      "coordinated": [
        24650,
        33350
      ],
      "savings": [
        12750,
        21250
      ]
    },
    "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
    "assumptions": [
      "Unit rates are placeholders; replace with real bids.",
      "Trucks are shared only when construction windows overlap (yes for this pair).",
      "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
    ]
  }
}
```

---

### `GET /quality`

Data quality page and badge count.

Response `200`:

```json
[
  {
    "project_id": "DESC_1",
    "code": "ENDPOINT_NOT_FOUND",
    "message": "One endpoint could not be located; center uses the located endpoint only."
  },
  {
    "project_id": "DESC_2",
    "code": "ENDPOINT_NOT_FOUND",
    "message": "One endpoint could not be located; center uses the located endpoint only."
  },
  {
    "project_id": "DESC_4",
    "code": "ENDPOINT_NOT_FOUND",
    "message": "One endpoint could not be located; center uses the located endpoint only."
  },
  {
    "project_id": "DESC_4",
    "code": "POSSIBLY_COMPLETE",
    "message": "In-service date is in the past; project may already be complete."
  },
  {
    "project_id": "GPC_2",
    "code": "ENDPOINT_NOT_FOUND",
    "message": "One endpoint could not be located; center uses the located endpoint only."
  },
  {
    "project_id": "GPC_2",
    "code": "COORD_CONFLICT",
    "message": "McIntosh substation appears with two different longitudes (-81.175112 vs -81.182105) across projects."
  },
  {
    "project_id": "GPC_3",
    "code": "COORD_CONFLICT",
    "message": "McIntosh substation appears with two different longitudes (-81.175112 vs -81.182105) across projects."
  }
]
```

---

### `POST /whatif`

Feasibility page and the Nearby projects panel after a draft. Using map pins instead: send `endpoints` (see POST bodies).

Request body:
```json
{
  "name": "Corridor upgrade",
  "location_text": "Near Hardeeville, SC",
  "construction_window": {
    "start": "2027-06-01",
    "end": "2027-12-15"
  }
}
```

Response `200`:

```json
{
  "proposed": {
    "name": "Corridor upgrade",
    "utility": null,
    "voltage_kv": null,
    "endpoints": [
      {
        "name": "Hardeeville, SC",
        "lat": 32.2871,
        "lon": -81.079
      }
    ],
    "construction_window": {
      "start": "2027-06-01",
      "end": "2027-12-15"
    },
    "center": {
      "lat": 32.2871,
      "lon": -81.079
    },
    "geocoded": {
      "lat": 32.2871,
      "lon": -81.079,
      "label": "Hardeeville, SC",
      "query": "Near Hardeeville, SC",
      "source": "mock gazetteer"
    }
  },
  "overlaps": [
    {
      "project_id": "DESC_3",
      "short_name": "Jasper–Okatie",
      "name": "Jasper - Okatie 230 kV #2: Construct",
      "utility": "DESC",
      "utility_name": "Dominion Energy South Carolina",
      "construction_window": {
        "start": "2024-01-01",
        "end": "2025-12-31",
        "source": "estimated"
      },
      "center_distance_mi": 4.1,
      "closest_distance_km": 6.26,
      "tier": "shared_site",
      "window_overlap_months": 0
    },
    {
      "project_id": "GPC_3",
      "short_name": "Goshen–McIntosh",
      "name": "SAV: GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "construction_window": {
        "start": "2025-06-01",
        "end": "2027-06-01",
        "source": "estimated"
      },
      "center_distance_mi": 6.88,
      "closest_distance_km": 11.05,
      "tier": "shared_crews",
      "window_overlap_months": 0
    },
    {
      "project_id": "GPC_2",
      "short_name": "McIntosh–Purrysburg",
      "name": "SAV: MCINTOSH - PURRYSBURG 230KV REACTORS",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "construction_window": {
        "start": "2024-01-01",
        "end": "2026-06-01",
        "source": "estimated"
      },
      "center_distance_mi": 7.19,
      "closest_distance_km": 11.55,
      "tier": "shared_crews",
      "window_overlap_months": 0
    },
    {
      "project_id": "DESC_5",
      "short_name": "Okatie–Bluffton",
      "name": "Okatie-Bluffton 115 kV: Rebuild",
      "utility": "DESC",
      "utility_name": "Dominion Energy South Carolina",
      "construction_window": {
        "start": "2024-01-01",
        "end": "2025-06-01",
        "source": "estimated"
      },
      "center_distance_mi": 7.95,
      "closest_distance_km": 6.77,
      "tier": "shared_site",
      "window_overlap_months": 0
    }
  ],
  "closure_conflicts": [],
  "closure_data_available": false,
  "closure_note": "No public road-closure data is connected. Closure conflicts are not evaluated.",
  "suggestion": {
    "shift_months": -6,
    "suggested_window": {
      "start": "2026-12-01",
      "end": "2027-06-15"
    },
    "window_overlap_months_before": 0,
    "window_overlap_months_after": 6,
    "explanation": "Moving the window 6 months earlier increases shared construction time with nearby projects from 0 to 6 months, so crews and equipment can be shared."
  }
}
```

---

### `POST /overlaps/OVL_3/brief`

"Draft coordination plan" chip. `mode` can be `summary`, `plan` or `risks`.

Request body:
```json
{
  "mode": "plan"
}
```

Response `200`:

```json
{
  "overlap_id": "OVL_3",
  "mode": "plan",
  "brief": "(mock Gemini) Coordination plan for Jasper–Okatie ↔ McIntosh–Purrysburg: 1) Planners from Dominion Energy South Carolina and Georgia Power confirm construction windows (2024-01-01 to 2025-12-31 and 2024-01-01 to 2026-06-01). 2) Schedule shared crews and equipment during the 24 overlapping months. 3) Share one laydown yard and delivery route. 4) Exchange contacts and review permits for common roads.",
  "source": "gemini",
  "cached": false
}
```

---

### `POST /draft`

Chat-to-draft on + Describe project. Render `fields` in the draft panel with a badge per `confidence`, `follow_up_questions` as the assistant's next bubble, and `location_point` as the proposed pin.

Request body:
```json
{
  "kind": "project",
  "text": "We're planning a corridor upgrade near Hardeeville from June to December 2027 with a nightly lane closure on US-17 northbound, 9 PM to 5 AM",
  "draft": {}
}
```

Response `200`:

```json
{
  "kind": "project",
  "fields": {
    "name": {
      "value": "Corridor upgrade",
      "confidence": "high"
    },
    "description": {
      "value": "We're planning a corridor upgrade near Hardeeville from June to December 2027 with a nightly lane closure on US-17 northbound, 9 PM to 5 AM",
      "confidence": "medium"
    },
    "location": {
      "value": "Near Hardeeville, SC",
      "confidence": "high"
    },
    "start_date": {
      "value": "2027-06-01",
      "confidence": "high"
    },
    "end_date": {
      "value": "2027-12-31",
      "confidence": "high"
    },
    "work_type": {
      "value": "Roadway improvement",
      "confidence": "medium"
    },
    "lane_closures": {
      "value": "Lane closure (northbound)",
      "confidence": "high"
    },
    "work_hours": {
      "value": "9 PM – 5 AM",
      "confidence": "high"
    },
    "roads_affected": {
      "value": "US-17",
      "confidence": "high"
    }
  },
  "missing": [],
  "ready": true,
  "follow_up_questions": [],
  "location_point": {
    "lat": 32.2871,
    "lon": -81.079,
    "label": "Hardeeville, SC"
  },
  "source": "gemini",
  "note": "(mock Gemini) Draft only. Nothing is saved until the user reviews it."
}
```

---

### `POST /draft`

Same endpoint for resources (and `kind: "job"` for job postings).

Request body:
```json
{
  "kind": "resource",
  "text": "Two bucket trucks near Savannah June 3-10 2027 at $1,250 each",
  "draft": {}
}
```

Response `200`:

```json
{
  "kind": "resource",
  "fields": {
    "name": {
      "value": "Bucket trucks with operators",
      "confidence": "high"
    },
    "quantity": {
      "value": 2,
      "confidence": "high"
    },
    "location": {
      "value": "Savannah, GA",
      "confidence": "high"
    },
    "dates": {
      "value": "2027-06-03 to 2027-06-10",
      "confidence": "medium"
    },
    "rate": {
      "value": "$1,250",
      "confidence": "high"
    }
  },
  "missing": [],
  "ready": true,
  "follow_up_questions": [],
  "location_point": {
    "lat": 32.0809,
    "lon": -81.0912,
    "label": "Savannah, GA"
  },
  "source": "gemini",
  "note": "(mock Gemini) Draft only. Nothing is saved until the user reviews it."
}
```

---

### `POST /scenario/assist`

Cost page assistant. Show `reply` as a bubble, `suggested_changes` as the checklist, and apply them on "Apply to scenario".

Request body:
```json
{
  "overlap_id": "OVL_3",
  "message": "Try sharing 2 bucket trucks for 5 days and a single laydown yard"
}
```

Response `200`:

```json
{
  "overlap_id": "OVL_3",
  "reply": "(mock Gemini) Applying these changes gives separate work at $46,000 and coordinated work at $26,000, about $20,000 (43%) lower. ",
  "suggested_changes": [
    {
      "path": "coordinated.shared_truck_days",
      "value": 10,
      "label": "Use 2 shared bucket trucks for 5 days (10 truck-days)"
    },
    {
      "path": "coordinated.laydown_sites",
      "value": 1,
      "label": "Share a single laydown yard"
    }
  ],
  "preview_totals": {
    "separate": 46000,
    "coordinated": 26000,
    "savings": 20000,
    "savings_pct": 43.5
  }
}
```

---

### `POST /ask`

Global Ask Gridlock bar. Show `answer`; if `intent.action` is `navigate`, select `intent.overlap_id` (if any) and go to `intent.page`.

Request body:
```json
{
  "question": "How much could Jasper and McIntosh save by sharing costs?"
}
```

Response `200`:

```json
{
  "intent": {
    "action": "navigate",
    "page": "cost",
    "overlap_id": "OVL_3"
  },
  "answer": "(mock Gemini) Based on the planned projects: OVL_3: Jasper - Okatie 230 kV #2: Construct (Dominion) and SAV: MCINTOSH - PURRYSBURG 230KV REACTORS (Georgia Power), 5.65 mi apart, 24 months of overlapping construction.",
  "cited_project_ids": [
    "DESC_3",
    "GPC_2"
  ],
  "cited_overlap_ids": [
    "OVL_3"
  ]
}
```

---

### `GET /projects/GPC_99`

Every error has this shape.

Response `404`:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Project GPC_99 does not exist"
  }
}
```

---

### `POST /draft`

Request body:
```json
{
  "kind": "car",
  "text": "x"
}
```

Response `400`:

```json
{
  "error": {
    "code": "BAD_REQUEST",
    "message": "kind must be project, resource or job"
  }
}
```

---

### When Gemini is down

Start the mock with `MOCK_GEMINI_FAIL=1` to see these.

- `POST /overlaps/{id}/brief` still returns `200` with `"source": "fallback"` and a template text. Render it normally.
- `POST /ask`, `POST /draft` and `POST /scenario/assist` return `503`:
```json
{
  "error": {
    "code": "GEMINI_UNAVAILABLE",
    "message": "Gemini is not responding. Use the manual form."
  }
}
```
Show the message and keep the manual path available (manual form, editable cost inputs).

---

## Objects

### Project

| Field | Type | Notes |
|---|---|---|
| `id` | string | e.g. `DESC_3`, `GPC_2` |
| `utility` | string | `DESC` or `GPC` |
| `utility_name` | string | Full name |
| `state` | string | `SC` or `GA` |
| `name` | string | As written in the filing |
| `short_name` | string | For cards and labels, e.g. `Jasper–Okatie` |
| `work_type_label` | string | e.g. `Line rebuild`, `New transmission line` |
| `voltage_kv` | number or null | |
| `project_type` | string | `line` or `substation` |
| `status` | string | From the filing, e.g. `Planned`, `In Progress` |
| `in_service_date` | string | `YYYY-MM-DD` |
| `construction_window` | object | `{start, end, source}`, dates `YYYY-MM-DD`. `source`: `gpc_start_date`, `desc_spend_years` or `estimated` |
| `endpoints` | array | `{name, lat, lon, confidence, source, county}`. `lat`, `lon` and `county` are null if not found |
| `counties` | array | e.g. `["Jasper County, SC"]` |
| `center` | object | `{lat, lon}`, midpoint of located endpoints |
| `geometry` | GeoJSON | `Point` or `LineString`, coordinates `[lon, lat]` |
| `location_confidence` | string | Weakest of the located endpoints |
| `description` | string | From the filing |
| `cost` | object or null | DESC only: `{currency, by_year {previous, 2024..2028}, total, note}`. GPC costs are redacted, so null |
| `source` | object | `{document, page}` |
| `quality_flags` | array | `{code, message}` |
| `overlap_ids` | array | IDs of overlaps this project is part of |

### Overlap

| Field | Type | Notes |
|---|---|---|
| `id` | string | e.g. `OVL_1` |
| `label` | string | e.g. `Jasper–Okatie ↔ McIntosh–Purrysburg` |
| `project_a` | string | Always the DESC project ID |
| `project_b` | string | Always the GPC project ID |
| `potential` | string | `high`, `moderate` or `lower` (from `score`; thresholds in `/meta`) |
| `center_distance_mi` | number | Sperry's official metric (haversine between centers) |
| `closest_distance_km` | number | Closest point to closest point |
| `closest_points` | object | `{a: {lat, lon}, b: {lat, lon}}` for drawing a connector |
| `tier` | string | `crossing`, `shared_land` (under 1.6 km), `shared_site` (under 8 km), `shared_crews` (under 40 km) |
| `tier_explanation` | string | Plain English |
| `shared_endpoint` | boolean | Both projects end at the same substation |
| `time_gap_days` | number | Gap between in-service dates (Sperry's column) |
| `window_overlap_months` | number | Months both are under construction at once |
| `score` | number | 0 to 100, higher is better |
| `rank` | number | 1 is the best opportunity |
| `cost_estimate` | object | Summary: `{shared_row_acres, mobilization_savings_usd, total_estimated_savings_usd, assumptions[]}`. Values can be null |
| `cost_scenario` | object | Full editable scenario for the cost page. See below |
| `brief` | string or null | Cached Gemini brief if one was already generated |

### Cost scenario (`overlap.cost_scenario`)

These are the default inputs for the cost comparison page. The browser recomputes totals live as the user edits, using `formula`.

```json
{
  "illustrative": true,
  "unit_rates": { "mobilization_per_event": 3000, "bucket_truck_per_day": 1500, "laydown_per_site": 5000 },
  "separate": {
    "a": { "mobilization_events": 1, "truck_days": 10, "laydown_sites": 1, "start_date": "2024-01-01" },
    "b": { "mobilization_events": 1, "truck_days": 10, "laydown_sites": 1, "start_date": "2024-01-01" }
  },
  "coordinated": { "mobilization_events_a": 1, "mobilization_events_b": 1, "shared_truck_days": 12, "laydown_sites": 1, "start_date_a": "...", "start_date_b": "..." },
  "totals": { "separate": 46000, "coordinated": 29000, "savings": 17000, "savings_pct": 37.0,
              "separate_by_project": { "a": 23000, "b": 23000 }, "coordinated_by_project": { "a": 14500, "b": 14500 } },
  "range": { "separate": [39100, 52900], "coordinated": [24650, 33350], "savings": [12750, 21250] },
  "formula": "...",
  "assumptions": ["..."]
}
```

- **Separate** = for each project: `mobilization_events × mobilization rate + truck_days × truck rate + laydown_sites × laydown rate`, then add the two.
- **Coordinated** = `(mobilization_events_a + mobilization_events_b) × mobilization rate + shared_truck_days × truck rate + laydown_sites × laydown rate`. Shared costs are split 50/50 for the per-project bars.
- The defaults depend on the data: trucks are shared only when construction windows overlap, and one laydown yard is shared only when the projects are under 8 km apart. So some pairs show $0 savings by default. That's accurate, not a bug.

### Quality flag

`{project_id, code, message}`. Codes: `ENDPOINT_NOT_FOUND`, `COORD_CONFLICT`, `POSSIBLY_COMPLETE`, `LOW_CONFIDENCE_MATCH`, `DATE_PARSE_FAILED`.

---

## POST bodies

### `POST /whatif`

Give either `endpoints` (map pins) or `location_text` (free text, geocoded by the backend).

```json
{
  "name": "Corridor upgrade",
  "location_text": "Near Hardeeville, SC",
  "construction_window": { "start": "2027-06-01", "end": "2027-12-15" }
}
```
or
```json
{
  "name": "Proposed: Hardeeville 230 kV Tap",
  "utility": "DESC",
  "voltage_kv": 230,
  "endpoints": [{ "name": "Hardeeville", "lat": 32.2866, "lon": -81.0801 }],
  "construction_window": { "start": "2029-01-01", "end": "2030-06-01" },
  "max_shift_months": 24
}
```
- `name` and `construction_window` are required. `utility`, `voltage_kv` and `max_shift_months` are optional.
- If `utility` is set, only the **other** utility's projects are compared. If it's omitted (e.g. road work), all projects are compared.
- Nothing is saved.

Response:
- `proposed`: echo, plus `center` and `geocoded` (`{lat, lon, label, query, source}` when `location_text` was used)
- `overlaps[]`: `{project_id, short_name, name, utility, utility_name, construction_window, center_distance_mi, closest_distance_km, tier, window_overlap_months}`
- `suggestion`: `{shift_months, suggested_window, window_overlap_months_before, window_overlap_months_after, explanation}`. Negative shift means earlier. Never suggests a start date in the past.
- `closure_conflicts: []`, `closure_data_available: false`, `closure_note`. There is no public road-closure data, so keep closure and traffic panels illustrative.

If `location_text` can't be located: 400 with a message asking for a town name or a map pin.

### `POST /overlaps/{id}/brief`

```json
{ "mode": "summary", "refresh": false }
```
- `mode`: `summary` (default), `plan` (for "Draft coordination plan") or `risks` (for "Identify risks")
- Response: `{overlap_id, mode, brief, source, cached}`. `source` is `gemini` or `fallback`. If Gemini fails, you still get a template-based brief with `source: "fallback"`.

### `POST /draft`

Turns a chat message into a structured draft for the review panel. Send the user's latest message plus the current draft, so values the user already typed are kept.

```json
{ "kind": "project", "text": "Corridor upgrade near Hardeeville from June to December 2027, nightly lane closure on US-17 northbound, 9 PM to 5 AM", "draft": {} }
```
- `kind`: `project`, `resource` or `job`

Response:
```json
{
  "kind": "project",
  "fields": {
    "name": { "value": "Corridor upgrade", "confidence": "high" },
    "start_date": { "value": "2027-06-01", "confidence": "high" },
    "work_hours": { "value": "9 PM – 5 AM", "confidence": "high" }
  },
  "missing": [],
  "ready": true,
  "follow_up_questions": [],
  "location_point": { "lat": 32.2871, "lon": -81.079, "label": "Hardeeville, SC" },
  "source": "gemini"
}
```
- Field keys per kind:
  - `project`: `name`, `description`, `location`, `start_date`, `end_date`, `work_type`, `lane_closures`, `work_hours`, `roads_affected`
  - `resource`: `name`, `quantity`, `location`, `dates`, `rate`
  - `job`: `role`, `openings`, `project`, `dates`, `requirements`
- Every key is always present. `confidence` is `high`, `medium`, `user` (kept from `draft`) or `null` when the value is missing. These map to the High/Medium badges in the design.
- `follow_up_questions`: up to 3, for the assistant's next chat bubble.
- `location_point`: drop the "Proposed project" pin, then call `/whatif` for nearby projects.
- Nothing is saved. Publishing stays a frontend action.

### `POST /scenario/assist`

For the assistant on the cost page.

```json
{ "overlap_id": "OVL_3", "message": "Try sharing 2 bucket trucks for 5 days", "scenario": { "...current cost_scenario, optional..." } }
```

Response:
```json
{
  "overlap_id": "OVL_3",
  "reply": "Applying these changes gives ...",
  "suggested_changes": [
    { "path": "coordinated.shared_truck_days", "value": 10, "label": "Use 2 shared bucket trucks for 5 days (10 truck-days)" }
  ],
  "preview_totals": { "separate": 46000, "coordinated": 26000, "savings": 20000, "savings_pct": 43.5 }
}
```
- `suggested_changes` powers the "Suggested changes" checklist. "Apply to scenario" sets each `path` to `value` in the local scenario.
- If `scenario` is omitted, the overlap's default scenario is used.

### `POST /ask`

```json
{ "question": "How much could Jasper and McIntosh save by sharing costs?" }
```

Response:
```json
{
  "intent": { "action": "navigate", "page": "cost", "overlap_id": "OVL_3" },
  "answer": "...",
  "cited_project_ids": ["DESC_3", "GPC_2"],
  "cited_overlap_ids": ["OVL_3"]
}
```
- `intent.action` is `navigate` or `none`. `page` uses the prototype's page names: `map`, `opportunities`, `feasibility`, `cost`, `inventory`, `jobs`, `addProject`. If `overlap_id` is present, select that overlap before navigating.

---

## Errors

All errors use this shape with a normal HTTP status (400, 404, 500, 503):
```json
{ "error": { "code": "NOT_FOUND", "message": "Project GPC_99 does not exist" } }
```
Codes: `NOT_FOUND`, `BAD_REQUEST`, `GEMINI_UNAVAILABLE`, `INTERNAL`. On `GEMINI_UNAVAILABLE` from `/draft`, offer the manual form.

---

## Things to know

- **GeoJSON coordinates are `[lon, lat]`.** Every other location is a `{lat, lon}` object.
- Projects with `not_found` endpoints still appear in `/projects`. Their `geometry` uses only the located endpoints. A project with no located endpoints has `geometry: null`.
- `/overlaps` only pairs a DESC project with a GPC project.
- Overlap IDs are not in rank order. Display by `rank` (`/overlaps` already returns them sorted).
- **In the mock, coordinates and in-service dates are real** (from Sperry's starter file). Construction windows, costs, counties, descriptions and Gemini text are placeholders, so the mock ranking is not final. Mock Gemini text starts with "(mock Gemini)".
- The mock geocoder only knows a few towns (Hardeeville, Savannah, Okatie, Bluffton, Ridgeland, Pooler, Rincon, Augusta, North Augusta, Evans, Charleston). The real backend geocodes any address.

---

<!-- NEW_ENDPOINTS_START -->

## New endpoints (real backend)

Added by the real backend; the mock does not serve these. Identity is by header: `X-Company-Id` (e.g. `CMP_A`) for companies, `X-Worker-Id` (e.g. `WRK_1`) for workers. Without a database these return `503 DB_UNAVAILABLE`; the endpoints above keep working. Additive fields on existing objects: `overlap.kind` (`cross_utility` | `user_project`), `project.source.type` (`public_filing` | `user`), `project.user_overlap_ids` on public projects, `project.budget_usd`/`budget_source`/`budget_note`, `project.traffic` on `GET /projects/{id}`, `traffic` on `/whatif`, `overlap.score_breakdown`, `overlap.cost_estimate` v2, and new query params `GET /projects?source=`, `GET /overlaps?kind=` and `GET /overlaps?project_id=`.

Errors also use `UNAUTHORIZED` (401), `FORBIDDEN` (403), `CONFLICT` / `INSUFFICIENT_QUANTITY` (409), `GONE` (410, expired assistant action), `NO_TEXT_LAYER` (422), `UNSUPPORTED_FILE` (415), `TRAFFIC_UNAVAILABLE` (503) and `DB_UNAVAILABLE` (503).

## Identity

### `GET /companies`

Demo companies for the company switcher. Send the chosen id as `X-Company-Id` on every request.

Response `200`:

An **array** (3 items here). First item shown; every item has the same shape.

```json
[
  {
    "id": "CMP_A",
    "name": "Demo Contractor A",
    "yard": {
      "label": "Savannah, GA",
      "lat": 32.0809,
      "lon": -81.0912
    },
    "phone": "(555) 010-0101"
  }
]
```

Example file: `examples/GET_companies.json`

---

### `GET /me`

Who the headers say you are: `company`, `worker` or `guest`. Guests can read everything but every write returns `401 UNAUTHORIZED`.

Headers: `X-Company-Id: CMP_A`

Response `200`:

```json
{
  "kind": "company",
  "company": {
    "id": "CMP_A",
    "name": "Demo Contractor A",
    "type": "contractor",
    "yard": {
      "label": "Savannah, GA",
      "lat": 32.0809,
      "lon": -81.0912
    },
    "phone": "(555) 010-0101",
    "created_at": "2026-09-27T00:11:01.665158+00:00",
    "updated_at": "2026-09-27T00:11:01.665158+00:00"
  }
}
```

Example file: `examples/GET_me.json`

---

## User projects

### `POST /projects`

Adds a user project. It joins the overlap analysis at once: it is compared with every project that has a different owner (both utilities' filings and other companies' projects). Location comes from `location_text` (geocoded) or 1-2 `endpoints` pins. Returns the project, its overlaps (`kind: "user_project"`) and lane-closure conflicts with other user projects.

Headers: `X-Company-Id: CMP_B`

Request body:
```json
{
  "name": "Corridor upgrade",
  "location_text": "Near Hardeeville, SC",
  "start_date": "2027-06-01",
  "end_date": "2027-12-15",
  "work_type": "Roadway improvement",
  "roads_affected": "US-17",
  "lane_closures": "Northbound lane, nightly",
  "work_hours": "21:00-05:00"
}
```

Response `201`:

```json
{
  "project": {
    "id": "USR_H010FE",
    "utility": "USER",
    "utility_name": "Demo Contractor B",
    "state": "SC",
    "name": "Corridor upgrade",
    "voltage_kv": null,
    "project_type": "substation",
    "status": "Planned",
    "in_service_date": "2027-12-15",
    "construction_window": {
      "start": "2027-06-01",
      "end": "2027-12-15",
      "source": "user"
    },
    "endpoints": [
      {
        "name": "Hardeeville, SC",
        "lat": 32.2871,
        "lon": -81.079,
        "confidence": "medium",
        "source": "gazetteer (test)",
        "county": null
      }
    ],
    "center": {
      "lat": 32.2871,
      "lon": -81.079
    },
    "geometry": {
      "type": "Point",
      "coordinates": [
        -81.079,
        32.2871
      ]
    },
    "location_confidence": "medium",
    "description": null,
    "cost": null,
    "source": {
      "document": null,
      "page": null,
      "type": "user"
    },
    "quality_flags": [],
    "overlap_ids": [
      "OVL_USR_H010FE__DESC_3",
      "OVL_USR_H010FE__DESC_5",
      "OVL_USR_H010FE__GPC_2",
      "OVL_USR_H010FE__GPC_3"
    ],
    "short_name": "Corridor upgrade",
    "work_type_label": "Roadway improvement",
    "counties": [],
    "county_source": null,
    "company_id": "CMP_B",
    "work_type": "Roadway improvement",
    "roads_affected": [
      "US-17"
    ],
    "lane_closures": "Northbound lane, nightly",
    "work_hours": "21:00-05:00",
    "planning_authority": null,
    "location_text": "Near Hardeeville, SC",
    "geocoded": {
      "lat": 32.2871,
      "lon": -81.079,
      "label": "Hardeeville, SC",
      "query": "Near Hardeeville, SC",
      "source": "gazetteer (test)"
    },
    "contract_text_hash": null,
    "line_miles": null,
    "budget_usd": null,
    "budget_source": null,
    "budget_note": "No budget available",
    "created_at": "2026-09-27T00:11:01.751145+00:00",
    "updated_at": "2026-09-27T00:11:01.751145+00:00"
  },
  "overlaps": [
    {
      "id": "OVL_USR_H010FE__DESC_3",
      "project_a": "USR_H010FE",
      "project_b": "DESC_3",
      "center_distance_mi": 4.1,
      "closest_distance_km": 6.27,
      "closest_points": {
        "a": {
          "lat": 32.2871,
          "lon": -81.079
        },
        "b": {
          "lat": 32.34091,
          "lon": -81.058439
        }
      },
      "tier": "shared_site",
      "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
      "shared_endpoint": false,
      "time_gap_days": 714,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 24.0,
      "score_breakdown": {
        "proximity": 24.0,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 1,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "no budget available"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": null,
        "reference_budget_source": null,
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [
          "No budget available for either project: mobilization savings not estimated"
        ],
        "sources": []
      },
      "brief": null,
      "label": "Corridor upgrade ↔ Jasper–Okatie",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 3000,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2023-12-31"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 1,
          "start_date_a": "2027-06-01",
          "start_date_b": "2023-12-31"
        },
        "totals": {
          "separate": 46000,
          "coordinated": 41000,
          "savings": 5000,
          "savings_pct": 10.9,
          "separate_by_project": {
            "a": 23000,
            "b": 23000
          },
          "coordinated_by_project": {
            "a": 20500,
            "b": 20500
          }
        },
        "range": {
          "separate": [
            39100,
            52900
          ],
          "coordinated": [
            34850,
            47150
          ],
          "savings": [
            3750,
            6250
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_H010FE__DESC_5",
      "project_a": "USR_H010FE",
      "project_b": "DESC_5",
      "center_distance_mi": 7.95,
      "closest_distance_km": 6.78,
      "closest_points": {
        "a": {
          "lat": 32.2871,
          "lon": -81.079
        },
        "b": {
          "lat": 32.333758,
          "lon": -81.032495
        }
      },
      "tier": "shared_site",
      "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
      "shared_endpoint": false,
      "time_gap_days": 927,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 23.8,
      "score_breakdown": {
        "proximity": 23.8,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 2,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "no budget available"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": null,
        "reference_budget_source": null,
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [
          "No budget available for either project: mobilization savings not estimated"
        ],
        "sources": []
      },
      "brief": null,
      "label": "Corridor upgrade ↔ Okatie–Bluffton",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 3000,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2023-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 1,
          "start_date_a": "2027-06-01",
          "start_date_b": "2023-06-01"
        },
        "totals": {
          "separate": 46000,
          "coordinated": 41000,
          "savings": 5000,
          "savings_pct": 10.9,
          "separate_by_project": {
            "a": 23000,
            "b": 23000
          },
          "coordinated_by_project": {
            "a": 20500,
            "b": 20500
          }
        },
        "range": {
          "separate": [
            39100,
            52900
          ],
          "coordinated": [
            34850,
            47150
          ],
          "savings": [
            3750,
            6250
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_H010FE__GPC_2",
      "project_a": "USR_H010FE",
      "project_b": "GPC_2",
      "center_distance_mi": 7.19,
      "closest_distance_km": 11.57,
      "closest_points": {
        "a": {
          "lat": 32.2871,
          "lon": -81.079
        },
        "b": {
          "lat": 32.352116,
          "lon": -81.175112
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 562,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 12.0,
      "score_breakdown": {
        "proximity": 12.0,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 4,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "no budget available"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": null,
        "reference_budget_source": null,
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [
          "No budget available for either project: mobilization savings not estimated"
        ],
        "sources": []
      },
      "brief": null,
      "label": "Corridor upgrade ↔ McIntosh–Purrysburg",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 3000,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2024-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2024-06-01"
        },
        "totals": {
          "separate": 46000,
          "coordinated": 46000,
          "savings": 0,
          "savings_pct": 0.0,
          "separate_by_project": {
            "a": 23000,
            "b": 23000
          },
          "coordinated_by_project": {
            "a": 23000,
            "b": 23000
          }
        },
        "range": {
          "separate": [
            39100,
            52900
          ],
          "coordinated": [
            39100,
            52900
          ],
          "savings": [
            0,
            0
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_H010FE__GPC_3",
      "project_a": "USR_H010FE",
      "project_b": "GPC_3",
      "center_distance_mi": 6.88,
      "closest_distance_km": 11.05,
      "closest_points": {
        "a": {
          "lat": 32.2871,
          "lon": -81.079
        },
        "b": {
          "lat": 32.309018,
          "lon": -81.193518
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 197,
      "window_overlap_months": 0,
      "schedule_shift_possible": true,
      "timing_confidence": "filed",
      "score": 18.1,
      "score_breakdown": {
        "proximity": 12.1,
        "savings": 0.0,
        "timing": 6.0
      },
      "rank": 3,
      "cost_estimate": {
        "total_estimated_savings_usd": 1170,
        "range_usd": [
          313,
          4286
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "no budget available"
          },
          "logistics": {
            "low": 313,
            "point": 1170,
            "high": 4286,
            "applies": true,
            "site_to_site_road_miles": 8.3
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": null,
        "reference_budget_source": null,
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [
          "No budget available for either project: mobilization savings not estimated",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "brief": null,
      "label": "Corridor upgrade ↔ Goshen–McIntosh",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 3000,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2025-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2025-06-01"
        },
        "totals": {
          "separate": 46000,
          "coordinated": 46000,
          "savings": 0,
          "savings_pct": 0.0,
          "separate_by_project": {
            "a": 23000,
            "b": 23000
          },
          "coordinated_by_project": {
            "a": 23000,
            "b": 23000
          }
        },
        "range": {
          "separate": [
            39100,
            52900
          ],
          "coordinated": [
            39100,
            52900
          ],
          "savings": [
            0,
            0
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    }
  ],
  "closure_conflicts": []
}
```

Example file: `examples/POST_projects.json`

---

### `PATCH /projects/{id}`

Own user projects only (`403` for other companies and for public filings). Overlaps are recomputed. Same response shape as `POST /projects`.

Headers: `X-Company-Id: CMP_B`

Request body:
```json
{
  "end_date": "2028-02-01"
}
```

Response `200`:

```json
{
  "project": {
    "id": "USR_H010FE",
    "utility": "USER",
    "utility_name": "Demo Contractor B",
    "state": "SC",
    "name": "Corridor upgrade",
    "voltage_kv": null,
    "project_type": "substation",
    "status": "Planned",
    "in_service_date": "2028-02-01",
    "construction_window": {
      "start": "2027-06-01",
      "end": "2028-02-01",
      "source": "user"
    },
    "endpoints": [
      {
        "name": "Hardeeville, SC",
        "lat": 32.2871,
        "lon": -81.079,
        "confidence": "medium",
        "source": "gazetteer (test)",
        "county": null
      }
    ],
    "center": {
      "lat": 32.2871,
      "lon": -81.079
    },
    "geometry": {
      "type": "Point",
      "coordinates": [
        -81.079,
        32.2871
      ]
    },
    "location_confidence": "medium",
    "description": null,
    "cost": null,
    "source": {
      "document": null,
      "page": null,
      "type": "user"
    },
    "quality_flags": [],
    "overlap_ids": [
      "OVL_USR_H010FE__DESC_3",
      "OVL_USR_H010FE__DESC_5",
      "OVL_USR_H010FE__GPC_2",
      "OVL_USR_H010FE__GPC_3"
    ],
    "short_name": "Corridor upgrade",
    "work_type_label": "Roadway improvement",
    "counties": [],
    "county_source": null,
    "company_id": "CMP_B",
    "work_type": "Roadway improvement",
    "roads_affected": [
      "US-17"
    ],
    "lane_closures": "Northbound lane, nightly",
    "work_hours": "21:00-05:00",
    "planning_authority": null,
    "location_text": "Near Hardeeville, SC",
    "geocoded": {
      "lat": 32.2871,
      "lon": -81.079,
      "label": "Hardeeville, SC",
      "query": "Near Hardeeville, SC",
      "source": "gazetteer (test)"
    },
    "contract_text_hash": null,
    "line_miles": null,
    "budget_usd": null,
    "budget_source": null,
    "budget_note": "No budget available",
    "created_at": "2026-09-27T00:11:01.751145+00:00",
    "updated_at": "2026-09-27T00:11:01.793588+00:00"
  },
  "overlaps": [
    {
      "id": "OVL_USR_H010FE__DESC_3",
      "project_a": "USR_H010FE",
      "project_b": "DESC_3",
      "center_distance_mi": 4.1,
      "closest_distance_km": 6.27,
      "closest_points": {
        "a": {
          "lat": 32.2871,
          "lon": -81.079
        },
        "b": {
          "lat": 32.34091,
          "lon": -81.058439
        }
      },
      "tier": "shared_site",
      "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
      "shared_endpoint": false,
      "time_gap_days": 762,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 24.0,
      "score_breakdown": {
        "proximity": 24.0,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 1,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "no budget available"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": null,
        "reference_budget_source": null,
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [
          "No budget available for either project: mobilization savings not estimated"
        ],
        "sources": []
      },
      "brief": null,
      "label": "Corridor upgrade ↔ Jasper–Okatie",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 3000,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2023-12-31"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 1,
          "start_date_a": "2027-06-01",
          "start_date_b": "2023-12-31"
        },
        "totals": {
          "separate": 46000,
          "coordinated": 41000,
          "savings": 5000,
          "savings_pct": 10.9,
          "separate_by_project": {
            "a": 23000,
            "b": 23000
          },
          "coordinated_by_project": {
            "a": 20500,
            "b": 20500
          }
        },
        "range": {
          "separate": [
            39100,
            52900
          ],
          "coordinated": [
            34850,
            47150
          ],
          "savings": [
            3750,
            6250
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_H010FE__DESC_5",
      "project_a": "USR_H010FE",
      "project_b": "DESC_5",
      "center_distance_mi": 7.95,
      "closest_distance_km": 6.78,
      "closest_points": {
        "a": {
          "lat": 32.2871,
          "lon": -81.079
        },
        "b": {
          "lat": 32.333758,
          "lon": -81.032495
        }
      },
      "tier": "shared_site",
      "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
      "shared_endpoint": false,
      "time_gap_days": 975,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 23.8,
      "score_breakdown": {
        "proximity": 23.8,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 2,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "no budget available"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": null,
        "reference_budget_source": null,
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [
          "No budget available for either project: mobilization savings not estimated"
        ],
        "sources": []
      },
      "brief": null,
      "label": "Corridor upgrade ↔ Okatie–Bluffton",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 3000,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2023-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 1,
          "start_date_a": "2027-06-01",
          "start_date_b": "2023-06-01"
        },
        "totals": {
          "separate": 46000,
          "coordinated": 41000,
          "savings": 5000,
          "savings_pct": 10.9,
          "separate_by_project": {
            "a": 23000,
            "b": 23000
          },
          "coordinated_by_project": {
            "a": 20500,
            "b": 20500
          }
        },
        "range": {
          "separate": [
            39100,
            52900
          ],
          "coordinated": [
            34850,
            47150
          ],
          "savings": [
            3750,
            6250
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_H010FE__GPC_2",
      "project_a": "USR_H010FE",
      "project_b": "GPC_2",
      "center_distance_mi": 7.19,
      "closest_distance_km": 11.57,
      "closest_points": {
        "a": {
          "lat": 32.2871,
          "lon": -81.079
        },
        "b": {
          "lat": 32.352116,
          "lon": -81.175112
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 610,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 12.0,
      "score_breakdown": {
        "proximity": 12.0,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 4,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "no budget available"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": null,
        "reference_budget_source": null,
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [
          "No budget available for either project: mobilization savings not estimated"
        ],
        "sources": []
      },
      "brief": null,
      "label": "Corridor upgrade ↔ McIntosh–Purrysburg",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 3000,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2024-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2024-06-01"
        },
        "totals": {
          "separate": 46000,
          "coordinated": 46000,
          "savings": 0,
          "savings_pct": 0.0,
          "separate_by_project": {
            "a": 23000,
            "b": 23000
          },
          "coordinated_by_project": {
            "a": 23000,
            "b": 23000
          }
        },
        "range": {
          "separate": [
            39100,
            52900
          ],
          "coordinated": [
            39100,
            52900
          ],
          "savings": [
            0,
            0
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_H010FE__GPC_3",
      "project_a": "USR_H010FE",
      "project_b": "GPC_3",
      "center_distance_mi": 6.88,
      "closest_distance_km": 11.05,
      "closest_points": {
        "a": {
          "lat": 32.2871,
          "lon": -81.079
        },
        "b": {
          "lat": 32.309018,
          "lon": -81.193518
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 245,
      "window_overlap_months": 0,
      "schedule_shift_possible": true,
      "timing_confidence": "filed",
      "score": 18.1,
      "score_breakdown": {
        "proximity": 12.1,
        "savings": 0.0,
        "timing": 6.0
      },
      "rank": 3,
      "cost_estimate": {
        "total_estimated_savings_usd": 1170,
        "range_usd": [
          313,
          4286
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "no budget available"
          },
          "logistics": {
            "low": 313,
            "point": 1170,
            "high": 4286,
            "applies": true,
            "site_to_site_road_miles": 8.3
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": null,
        "reference_budget_source": null,
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [
          "No budget available for either project: mobilization savings not estimated",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "brief": null,
      "label": "Corridor upgrade ↔ Goshen–McIntosh",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 3000,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2025-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2025-06-01"
        },
        "totals": {
          "separate": 46000,
          "coordinated": 46000,
          "savings": 0,
          "savings_pct": 0.0,
          "separate_by_project": {
            "a": 23000,
            "b": 23000
          },
          "coordinated_by_project": {
            "a": 23000,
            "b": 23000
          }
        },
        "range": {
          "separate": [
            39100,
            52900
          ],
          "coordinated": [
            39100,
            52900
          ],
          "savings": [
            0,
            0
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    }
  ],
  "closure_conflicts": []
}
```

Example file: `examples/PATCH_project.json`

---

### `GET /overlaps?kind=user_project`

Additive filter: `kind=cross_utility` is Sperry's ranked DESC x GPC list, `kind=user_project` the user-project overlaps (ranked among themselves). Default: both.

Response `200`:

An **array** (4 items here). First item shown; every item has the same shape.

```json
[
  {
    "id": "OVL_USR_H010FE__DESC_3",
    "project_a": "USR_H010FE",
    "project_b": "DESC_3",
    "center_distance_mi": 4.1,
    "closest_distance_km": 6.27,
    "closest_points": {
      "a": {
        "lat": 32.2871,
        "lon": -81.079
      },
      "b": {
        "lat": 32.34091,
        "lon": -81.058439
      }
    },
    "tier": "shared_site",
    "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
    "shared_endpoint": false,
    "time_gap_days": 762,
    "window_overlap_months": 0,
    "schedule_shift_possible": false,
    "timing_confidence": "filed",
    "score": 24.0,
    "score_breakdown": {
      "proximity": 24.0,
      "savings": 0.0,
      "timing": 0.0
    },
    "rank": 1,
    "cost_estimate": {
      "total_estimated_savings_usd": 0,
      "range_usd": [
        0,
        0
      ],
      "components": {
        "mobilization": {
          "low": 0,
          "point": 0,
          "high": 0,
          "applies": false,
          "reason": "no budget available"
        },
        "logistics": {
          "low": 0,
          "point": 0,
          "high": 0,
          "applies": false,
          "reason": "construction windows cannot overlap"
        },
        "shared_land": {
          "low": 0,
          "point": 0,
          "high": 0,
          "applies": false
        },
        "traffic_delay": {
          "low": 0,
          "point": 0,
          "high": 0,
          "applies": false
        }
      },
      "reference_budget_usd": null,
      "reference_budget_source": null,
      "shared_row_acres": null,
      "mobilization_savings_usd": null,
      "assumptions": [
        "No budget available for either project: mobilization savings not estimated"
      ],
      "sources": []
    },
    "brief": null,
    "label": "Corridor upgrade ↔ Jasper–Okatie",
    "potential": "lower",
    "cost_scenario": {
      "illustrative": true,
      "defaults_source": "cost_sources.json",
      "unit_rates": {
        "mobilization_per_event": 3000,
        "bucket_truck_per_day": 1500,
        "laydown_per_site": 5000,
        "crew_size": 4,
        "crew_cost_per_day": 1160
      },
      "separate": {
        "a": {
          "mobilization_events": 1,
          "truck_days": 10,
          "laydown_sites": 1,
          "start_date": "2027-06-01"
        },
        "b": {
          "mobilization_events": 1,
          "truck_days": 10,
          "laydown_sites": 1,
          "start_date": "2023-12-31"
        }
      },
      "coordinated": {
        "mobilization_events_a": 1,
        "mobilization_events_b": 1,
        "shared_truck_days": 20,
        "laydown_sites": 1,
        "start_date_a": "2027-06-01",
        "start_date_b": "2023-12-31"
      },
      "totals": {
        "separate": 46000,
        "coordinated": 41000,
        "savings": 5000,
        "savings_pct": 10.9,
        "separate_by_project": {
          "a": 23000,
          "b": 23000
        },
        "coordinated_by_project": {
          "a": 20500,
          "b": 20500
        }
      },
      "range": {
        "separate": [
          39100,
          52900
        ],
        "coordinated": [
          34850,
          47150
        ],
        "savings": [
          3750,
          6250
        ]
      },
      "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
      "assumptions": [
        "Unit rates are placeholders; replace with real bids.",
        "Trucks are shared only when construction windows overlap (no for this pair).",
        "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
      ]
    },
    "kind": "user_project",
    "created_at": "2026-09-27T00:11:01.810047+00:00",
    "updated_at": "2026-09-27T00:11:01.810047+00:00"
  }
]
```

Example file: `examples/GET_overlaps_user.json`

---

## Resources

### `POST /resources`

List equipment or a crew. `type`: `equipment` or `crew`. Location from `location_text`, `location {lat, lon, label}`, or the company yard when omitted. `nearby_project_ids` are projects within 40 km.

Headers: `X-Company-Id: CMP_C`

Request body:
```json
{
  "name": "60-ton crane",
  "type": "equipment",
  "quantity": 2,
  "location_text": "Pooler, GA",
  "available_from": "2027-06-01",
  "available_to": "2027-06-30",
  "daily_rate": 1250,
  "notes": "Operator included"
}
```

Response `201`:

```json
{
  "id": "RES_VN17K4",
  "company_id": "CMP_C",
  "company_name": "Coastal Crane (demo)",
  "name": "60-ton crane",
  "type": "equipment",
  "quantity": 2,
  "location": {
    "label": "Pooler, GA",
    "lat": 32.1155,
    "lon": -81.247
  },
  "available_from": "2027-06-01",
  "available_to": "2027-06-30",
  "date_label": "Jun 1–30, 2027",
  "daily_rate": 1250,
  "rate_label": "$1,250/day per unit",
  "notes": "Operator included",
  "nearby_project_ids": [
    "GPC_3",
    "USR_H010FE",
    "GPC_2",
    "DESC_3",
    "DESC_5"
  ],
  "created_at": "2026-09-27T00:11:01.870472+00:00",
  "updated_at": "2026-09-27T00:11:01.870472+00:00"
}
```

Example file: `examples/POST_resources.json`

---

### `GET /resources?near=32.1155,-81.247&radius_km=40`

Filters: `type`, `near=<lat,lon>` + `radius_km` (default 40; adds `distance_km` and sorts by it), `q`, `company_id`, `available_on=<date>`.

Response `200`:

An **array** (4 items here). First item shown; every item has the same shape.

```json
[
  {
    "id": "RES_DEMO2",
    "company_id": "CMP_C",
    "company_name": "Coastal Crane (demo)",
    "name": "60-ton crane",
    "type": "equipment",
    "quantity": 1,
    "location": {
      "label": "Pooler, GA",
      "lat": 32.1155,
      "lon": -81.247
    },
    "available_from": "2027-05-01",
    "available_to": "2027-08-31",
    "date_label": "May 1 – Aug 31, 2027",
    "daily_rate": null,
    "rate_label": "Rate on request",
    "notes": "Demo listing. Operator and rigger available.",
    "nearby_project_ids": [
      "GPC_3",
      "GPC_2",
      "DESC_3",
      "DESC_5"
    ],
    "demo": true,
    "created_at": "2026-09-27T00:11:01.670063+00:00",
    "updated_at": "2026-09-27T00:11:01.670063+00:00",
    "distance_km": 0.0
  }
]
```

Example file: `examples/GET_resources.json`

---

### `PATCH /resources/{id}`

Owner only. Any subset of the POST fields.

Headers: `X-Company-Id: CMP_C`

Request body:
```json
{
  "quantity": 3
}
```

Response `200`:

```json
{
  "id": "RES_VN17K4",
  "company_id": "CMP_C",
  "company_name": "Coastal Crane (demo)",
  "name": "60-ton crane",
  "type": "equipment",
  "quantity": 3,
  "location": {
    "label": "Pooler, GA",
    "lat": 32.1155,
    "lon": -81.247
  },
  "available_from": "2027-06-01",
  "available_to": "2027-06-30",
  "date_label": "Jun 1–30, 2027",
  "daily_rate": 1250,
  "rate_label": "$1,250/day per unit",
  "notes": "Operator included",
  "nearby_project_ids": [
    "GPC_3",
    "USR_H010FE",
    "GPC_2",
    "DESC_3",
    "DESC_5"
  ],
  "created_at": "2026-09-27T00:11:01.870472+00:00",
  "updated_at": "2026-09-27T00:11:01.896931+00:00"
}
```

Example file: `examples/PATCH_resource.json`

---

## Reservations

### `POST /resources/{id}/reservations`

Request another company's resource. Rules: not your own (`400`), dates inside the availability window (`400`), and `quantity + accepted overlapping reservations <= resource.quantity` (`409 INSUFFICIENT_QUANTITY`). Starts `pending`.

Headers: `X-Company-Id: CMP_A`

Request body:
```json
{
  "quantity": 2,
  "from": "2027-06-05",
  "to": "2027-06-10",
  "note": "For the Hardeeville corridor work"
}
```

Response `201`:

```json
{
  "id": "RSV_EBCH8Q",
  "resource_id": "RES_VN17K4",
  "resource_name": "60-ton crane",
  "owner_company_id": "CMP_C",
  "requester_company_id": "CMP_A",
  "requester_company_name": "Demo Contractor A",
  "quantity": 2,
  "from": "2027-06-05",
  "to": "2027-06-10",
  "project_id": null,
  "note": "For the Hardeeville corridor work",
  "status": "pending",
  "created_at": "2026-09-27T00:11:01.918460+00:00",
  "updated_at": "2026-09-27T00:11:01.918460+00:00"
}
```

Example file: `examples/POST_reservation.json`

---

### `GET /reservations?role=incoming`

`role=incoming` (requests for my resources) or `outgoing` (my requests). Default: both.

Headers: `X-Company-Id: CMP_C`

Response `200`:

An **array** (1 items here). First item shown; every item has the same shape.

```json
[
  {
    "id": "RSV_EBCH8Q",
    "resource_id": "RES_VN17K4",
    "resource_name": "60-ton crane",
    "owner_company_id": "CMP_C",
    "requester_company_id": "CMP_A",
    "requester_company_name": "Demo Contractor A",
    "quantity": 2,
    "from": "2027-06-05",
    "to": "2027-06-10",
    "project_id": null,
    "note": "For the Hardeeville corridor work",
    "status": "pending",
    "created_at": "2026-09-27T00:11:01.918460+00:00",
    "updated_at": "2026-09-27T00:11:01.918460+00:00"
  }
]
```

Example file: `examples/GET_reservations.json`

---

### `PATCH /reservations/{id}`

The owner sets `accepted`/`declined`; the requester sets `cancelled`. Quantity is re-checked on accept.

Headers: `X-Company-Id: CMP_C`

Request body:
```json
{
  "status": "accepted"
}
```

Response `200`:

```json
{
  "id": "RSV_EBCH8Q",
  "resource_id": "RES_VN17K4",
  "resource_name": "60-ton crane",
  "owner_company_id": "CMP_C",
  "requester_company_id": "CMP_A",
  "requester_company_name": "Demo Contractor A",
  "quantity": 2,
  "from": "2027-06-05",
  "to": "2027-06-10",
  "project_id": null,
  "note": "For the Hardeeville corridor work",
  "status": "accepted",
  "created_at": "2026-09-27T00:11:01.918460+00:00",
  "updated_at": "2026-09-27T00:11:01.941228+00:00"
}
```

Example file: `examples/PATCH_reservation.json`

---

### `POST /resources/{id}/reservations`

Over-booking.

Headers: `X-Company-Id: CMP_B`

Request body:
```json
{
  "quantity": 2,
  "from": "2027-06-08",
  "to": "2027-06-09"
}
```

Response `409`:

```json
{
  "error": {
    "code": "INSUFFICIENT_QUANTITY",
    "message": "Only 1 of 3 available for those dates"
  }
}
```

Example file: `examples/ERROR_409_quantity.json`

---

## Jobs

### `POST /jobs`

Post a job. Pay is per hour.

Headers: `X-Company-Id: CMP_B`

Request body:
```json
{
  "title": "Transmission lineworker",
  "openings": 3,
  "location_text": "Hardeeville, SC",
  "pay_min": 38,
  "pay_max": 46,
  "start_date": "2027-06-01",
  "end_date": "2027-12-15",
  "qualifications": [
    "Journeyman Lineworker",
    "CDL Class A"
  ]
}
```

Response `201`:

```json
{
  "id": "JOB_TMHGR1",
  "company_id": "CMP_B",
  "company_name": "Demo Contractor B",
  "title": "Transmission lineworker",
  "openings": 3,
  "location": {
    "label": "Hardeeville, SC",
    "lat": 32.2871,
    "lon": -81.079
  },
  "pay_min": 38,
  "pay_max": 46,
  "pay_label": "$38–$46/hr",
  "start_date": "2027-06-01",
  "end_date": "2027-12-15",
  "date_label": "Jun 1 – Dec 15, 2027",
  "qualifications": [
    "Journeyman Lineworker",
    "CDL Class A"
  ],
  "project_id": null,
  "status": "open",
  "created_at": "2026-09-27T00:11:01.977719+00:00",
  "updated_at": "2026-09-27T00:11:01.977719+00:00"
}
```

Example file: `examples/POST_jobs.json`

---

### `GET /jobs?qualification=CDL`

Open jobs. Filters: `q`, `near` + `radius_km`, `qualification`.

Response `200`:

An **array** (3 items here). First item shown; every item has the same shape.

```json
[
  {
    "id": "JOB_TMHGR1",
    "company_id": "CMP_B",
    "company_name": "Demo Contractor B",
    "title": "Transmission lineworker",
    "openings": 3,
    "location": {
      "label": "Hardeeville, SC",
      "lat": 32.2871,
      "lon": -81.079
    },
    "pay_min": 38,
    "pay_max": 46,
    "pay_label": "$38–$46/hr",
    "start_date": "2027-06-01",
    "end_date": "2027-12-15",
    "date_label": "Jun 1 – Dec 15, 2027",
    "qualifications": [
      "Journeyman Lineworker",
      "CDL Class A"
    ],
    "project_id": null,
    "status": "open",
    "created_at": "2026-09-27T00:11:01.977719+00:00",
    "updated_at": "2026-09-27T00:11:01.977719+00:00"
  }
]
```

Example file: `examples/GET_jobs.json`

---

### `POST /jobs/{id}/applications`

A worker applies (`X-Worker-Id`). Fields default to the worker profile.

Headers: `X-Worker-Id: WRK_1`

Request body:
```json
{
  "availability": "Available from June 2027"
}
```

Response `201`:

```json
{
  "id": "APP_2ZPGWZ",
  "job_id": "JOB_TMHGR1",
  "job_title": "Transmission lineworker",
  "company_id": "CMP_B",
  "worker_id": "WRK_1",
  "applicant": {
    "name": "Jordan Davis (demo)",
    "qualifications": [
      "OSHA 10",
      "CDL Class A",
      "Journeyman Lineworker"
    ],
    "availability": "Available from June 2027"
  },
  "status": "submitted",
  "created_at": "2026-09-27T00:11:01.997615+00:00",
  "updated_at": "2026-09-27T00:11:01.997615+00:00"
}
```

Example file: `examples/POST_application.json`

---

### `GET /applications`

Workers see their applications; companies see applications to their jobs.

Headers: `X-Company-Id: CMP_B`

Response `200`:

An **array** (1 items here). First item shown; every item has the same shape.

```json
[
  {
    "id": "APP_2ZPGWZ",
    "job_id": "JOB_TMHGR1",
    "job_title": "Transmission lineworker",
    "company_id": "CMP_B",
    "worker_id": "WRK_1",
    "applicant": {
      "name": "Jordan Davis (demo)",
      "qualifications": [
        "OSHA 10",
        "CDL Class A",
        "Journeyman Lineworker"
      ],
      "availability": "Available from June 2027"
    },
    "status": "submitted",
    "created_at": "2026-09-27T00:11:01.997615+00:00",
    "updated_at": "2026-09-27T00:11:01.997615+00:00"
  }
]
```

Example file: `examples/GET_applications.json`

---

### `PATCH /applications/{id}`

Job owner only. `status`: submitted, reviewed, accepted, rejected.

Headers: `X-Company-Id: CMP_B`

Request body:
```json
{
  "status": "reviewed"
}
```

Response `200`:

```json
{
  "id": "APP_2ZPGWZ",
  "job_id": "JOB_TMHGR1",
  "job_title": "Transmission lineworker",
  "company_id": "CMP_B",
  "worker_id": "WRK_1",
  "applicant": {
    "name": "Jordan Davis (demo)",
    "qualifications": [
      "OSHA 10",
      "CDL Class A",
      "Journeyman Lineworker"
    ],
    "availability": "Available from June 2027"
  },
  "status": "reviewed",
  "created_at": "2026-09-27T00:11:01.997615+00:00",
  "updated_at": "2026-09-27T00:11:02.014605+00:00"
}
```

Example file: `examples/PATCH_application.json`

---

## Messages

### `POST /conversations`

Start a conversation with another company. Optional `overlap_id` and `attachment: {type: "cost_scenario", overlap_id}` (totals are filled in by the backend).

Headers: `X-Company-Id: CMP_A`

Request body:
```json
{
  "to_company_id": "CMP_C",
  "topic": "Crane for the corridor work",
  "overlap_id": "OVL_DESC_3__GPC_2",
  "text": "Could we share your crane in June 2027?",
  "attachment": {
    "type": "cost_scenario",
    "overlap_id": "OVL_DESC_3__GPC_2"
  }
}
```

Response `201`:

```json
{
  "conversation": {
    "id": "CNV_JAZOWS",
    "participant_company_ids": [
      "CMP_A",
      "CMP_C"
    ],
    "topic": "Crane for the corridor work",
    "overlap_id": "OVL_DESC_3__GPC_2",
    "last_message_at": "2026-09-27T00:11:02.036047+00:00",
    "last_message_preview": "Could we share your crane in June 2027?",
    "created_at": "2026-09-27T00:11:02.035048+00:00",
    "updated_at": "2026-09-27T00:11:02.036047+00:00"
  },
  "message": {
    "id": "MSG_MYVJQG",
    "conversation_id": "CNV_JAZOWS",
    "sender_company_id": "CMP_A",
    "sender_name": "Demo Contractor A",
    "text": "Could we share your crane in June 2027?",
    "attachment": {
      "type": "cost_scenario",
      "overlap_id": "OVL_DESC_3__GPC_2",
      "totals": {
        "separate": 46000,
        "coordinated": 29000,
        "savings": 17000,
        "savings_pct": 37.0,
        "separate_by_project": {
          "a": 23000,
          "b": 23000
        },
        "coordinated_by_project": {
          "a": 14500,
          "b": 14500
        }
      }
    },
    "created_at": "2026-09-27T00:11:02.036047+00:00",
    "updated_at": "2026-09-27T00:11:02.036047+00:00"
  }
}
```

Example file: `examples/POST_conversations.json`

---

### `POST /conversations/{id}/messages`

Participants only.

Headers: `X-Company-Id: CMP_C`

Request body:
```json
{
  "text": "Yes, both units are free June 5-10."
}
```

Response `201`:

```json
{
  "id": "MSG_0AUZW3",
  "conversation_id": "CNV_JAZOWS",
  "sender_company_id": "CMP_C",
  "sender_name": "Coastal Crane (demo)",
  "text": "Yes, both units are free June 5-10.",
  "attachment": null,
  "created_at": "2026-09-27T00:11:02.045701+00:00",
  "updated_at": "2026-09-27T00:11:02.045701+00:00"
}
```

Example file: `examples/POST_message.json`

---

### `GET /conversations`

The caller's conversations, newest first.

Headers: `X-Company-Id: CMP_A`

Response `200`:

An **array** (2 items here). First item shown; every item has the same shape.

```json
[
  {
    "id": "CNV_JAZOWS",
    "participant_company_ids": [
      "CMP_A",
      "CMP_C"
    ],
    "topic": "Crane for the corridor work",
    "overlap_id": "OVL_DESC_3__GPC_2",
    "last_message_at": "2026-09-27T00:11:02.045701+00:00",
    "last_message_preview": "Yes, both units are free June 5-10.",
    "created_at": "2026-09-27T00:11:02.035048+00:00",
    "updated_at": "2026-09-27T00:11:02.045701+00:00",
    "participants": [
      {
        "id": "CMP_A",
        "name": "Demo Contractor A"
      },
      {
        "id": "CMP_C",
        "name": "Coastal Crane (demo)"
      }
    ]
  }
]
```

Example file: `examples/GET_conversations.json`

---

### `GET /conversations/{id}/messages`

Participants only (`403` otherwise).

Headers: `X-Company-Id: CMP_A`

Response `200`:

An **array** (2 items here). First item shown; every item has the same shape.

```json
[
  {
    "id": "MSG_MYVJQG",
    "conversation_id": "CNV_JAZOWS",
    "sender_company_id": "CMP_A",
    "sender_name": "Demo Contractor A",
    "text": "Could we share your crane in June 2027?",
    "attachment": {
      "type": "cost_scenario",
      "overlap_id": "OVL_DESC_3__GPC_2",
      "totals": {
        "separate": 46000,
        "coordinated": 29000,
        "savings": 17000,
        "savings_pct": 37.0,
        "separate_by_project": {
          "a": 23000,
          "b": 23000
        },
        "coordinated_by_project": {
          "a": 14500,
          "b": 14500
        }
      }
    },
    "created_at": "2026-09-27T00:11:02.036047+00:00",
    "updated_at": "2026-09-27T00:11:02.036047+00:00"
  }
]
```

Example file: `examples/GET_messages.json`

---

## Assistant (agent)

### `POST /agent/chat`

Gemini with tools. Read tools run at once; write tools only create `pending_actions` the user must confirm. `changes` is always `[]` here. `intent` tells the UI where to navigate; `cited_ids` come from tool results, not model text. Every number in `reply` is checked against tool results (`source: "template"` when the check replaced the model text). `503 GEMINI_UNAVAILABLE` without a key.

Headers: `X-Company-Id: CMP_A`

Request body:
```json
{
  "message": "I have 2 cranes",
  "context": {
    "page": "inventory"
  }
}
```

Response `200`:

```json
{
  "thread_id": "THR_BG8MGV",
  "reply": "I can add 2 cranes to your inventory at your Savannah yard. Confirm below.",
  "pending_actions": [
    {
      "id": "ACT_LNND6Y",
      "tool": "add_resource",
      "summary": "Add 2 cranes to Demo Contractor A's inventory at Savannah, GA, available Sep 26, 2026 to Oct 26, 2026, rate on request. (location defaulted to the company yard (Savannah, GA); dates defaulted to today for 30 days; edit if needed.)",
      "preview": {
        "collection": "resources",
        "fields": {
          "name": "Crane",
          "type": "equipment",
          "quantity": 2,
          "location": {
            "label": "Savannah, GA",
            "lat": 32.0809,
            "lon": -81.0912
          },
          "available_from": "2026-09-26",
          "available_to": "2026-10-26",
          "date_label": "Sep 26 – Oct 26, 2026",
          "daily_rate": null,
          "rate_label": "Rate on request",
          "notes": null
        },
        "location_point": {
          "lat": 32.0809,
          "lon": -81.0912
        }
      },
      "expires_at": "2026-09-27T00:41:02+00:00"
    }
  ],
  "changes": [],
  "intent": {
    "action": "navigate",
    "page": "inventory"
  },
  "cited_ids": {
    "projects": [],
    "overlaps": [],
    "resources": [],
    "jobs": []
  },
  "source": "gemini"
}
```

Example file: `examples/POST_agent_chat.json`

---

### `POST /agent/actions/{id}/confirm`

Runs the pending action (same company, while pending, within 30 minutes: `409`/`410` otherwise). Optional `args` override fields and are re-validated. `changes` lists what was written.

Headers: `X-Company-Id: CMP_A`

Request body:
```json
{}
```

Response `200`:

```json
{
  "action": {
    "id": "ACT_LNND6Y",
    "thread_id": "THR_BG8MGV",
    "company_id": "CMP_A",
    "tool": "add_resource",
    "args": {
      "name": "Crane",
      "type": "equipment",
      "quantity": 2
    },
    "summary": "Add 2 cranes to Demo Contractor A's inventory at Savannah, GA, available Sep 26, 2026 to Oct 26, 2026, rate on request. (location defaulted to the company yard (Savannah, GA); dates defaulted to today for 30 days; edit if needed.)",
    "preview": {
      "collection": "resources",
      "fields": {
        "name": "Crane",
        "type": "equipment",
        "quantity": 2,
        "location": {
          "label": "Savannah, GA",
          "lat": 32.0809,
          "lon": -81.0912
        },
        "available_from": "2026-09-26",
        "available_to": "2026-10-26",
        "date_label": "Sep 26 – Oct 26, 2026",
        "daily_rate": null,
        "rate_label": "Rate on request",
        "notes": null
      },
      "location_point": {
        "lat": 32.0809,
        "lon": -81.0912
      }
    },
    "status": "confirmed",
    "created_at": "2026-09-27T00:11:02.098284+00:00",
    "expires_at": "2026-09-27T00:41:02+00:00",
    "result": {
      "id": "RES_AB4MPO",
      "company_id": "CMP_A",
      "company_name": "Demo Contractor A",
      "name": "Crane",
      "type": "equipment",
      "quantity": 2,
      "location": {
        "label": "Savannah, GA",
        "lat": 32.0809,
        "lon": -81.0912
      },
      "available_from": "2026-09-26",
      "available_to": "2026-10-26",
      "date_label": "Sep 26 – Oct 26, 2026",
      "daily_rate": null,
      "rate_label": "Rate on request",
      "notes": null,
      "nearby_project_ids": [
        "GPC_3",
        "USR_H010FE",
        "DESC_5",
        "DESC_3",
        "GPC_2"
      ],
      "created_at": "2026-09-27T00:11:02.112146+00:00",
      "updated_at": "2026-09-27T00:11:02.112146+00:00"
    },
    "error": null,
    "updated_at": "2026-09-27T00:11:02.112146+00:00"
  },
  "result": {
    "id": "RES_AB4MPO",
    "company_id": "CMP_A",
    "company_name": "Demo Contractor A",
    "name": "Crane",
    "type": "equipment",
    "quantity": 2,
    "location": {
      "label": "Savannah, GA",
      "lat": 32.0809,
      "lon": -81.0912
    },
    "available_from": "2026-09-26",
    "available_to": "2026-10-26",
    "date_label": "Sep 26 – Oct 26, 2026",
    "daily_rate": null,
    "rate_label": "Rate on request",
    "notes": null,
    "nearby_project_ids": [
      "GPC_3",
      "USR_H010FE",
      "DESC_5",
      "DESC_3",
      "GPC_2"
    ],
    "created_at": "2026-09-27T00:11:02.112146+00:00",
    "updated_at": "2026-09-27T00:11:02.112146+00:00"
  },
  "changes": [
    {
      "collection": "resources",
      "op": "insert",
      "id": "RES_AB4MPO"
    }
  ],
  "reply": "Added 2 cranes to your inventory. They're now visible to other companies."
}
```

Example file: `examples/POST_agent_confirm.json`

---

### `POST /agent/actions/{id}/cancel`

Cancel a pending action.

Headers: `X-Company-Id: CMP_A`

Response `200`:

```json
{
  "action": {
    "id": "ACT_EBAMVD",
    "thread_id": "THR_BG8MGV",
    "company_id": "CMP_A",
    "tool": "add_resource",
    "args": {
      "name": "Bucket truck",
      "type": "equipment",
      "quantity": 1
    },
    "summary": "Add 1 bucket truck to Demo Contractor A's inventory at Savannah, GA, available Sep 26, 2026 to Oct 26, 2026, rate on request. (location defaulted to the company yard (Savannah, GA); dates defaulted to today for 30 days; edit if needed.)",
    "preview": {
      "collection": "resources",
      "fields": {
        "name": "Bucket truck",
        "type": "equipment",
        "quantity": 1,
        "location": {
          "label": "Savannah, GA",
          "lat": 32.0809,
          "lon": -81.0912
        },
        "available_from": "2026-09-26",
        "available_to": "2026-10-26",
        "date_label": "Sep 26 – Oct 26, 2026",
        "daily_rate": null,
        "rate_label": "Rate on request",
        "notes": null
      },
      "location_point": {
        "lat": 32.0809,
        "lon": -81.0912
      }
    },
    "status": "cancelled",
    "created_at": "2026-09-27T00:11:02.120147+00:00",
    "expires_at": "2026-09-27T00:41:02+00:00",
    "result": null,
    "error": null,
    "updated_at": "2026-09-27T00:11:02.126662+00:00"
  }
}
```

Example file: `examples/POST_agent_cancel.json`

---

### `GET /agent/threads/{id}`

Thread history (last 30 messages) and its actions.

Headers: `X-Company-Id: CMP_A`

Response `200`:

```json
{
  "id": "THR_BG8MGV",
  "company_id": "CMP_A",
  "messages": [
    {
      "role": "user",
      "text": "I have 2 cranes",
      "ts": "2026-09-27T00:11:02.097285+00:00"
    },
    {
      "role": "model",
      "text": null,
      "calls": [
        {
          "name": "add_resource",
          "args": {
            "name": "Crane",
            "type": "equipment",
            "quantity": 2
          }
        }
      ],
      "ts": "2026-09-27T00:11:02.097285+00:00"
    },
    {
      "role": "tool",
      "results": [
        {
          "name": "add_resource",
          "response": {
            "pending_action_id": "ACT_LNND6Y",
            "summary": "Add 2 cranes to Demo Contractor A's inventory at Savannah, GA, available Sep 26, 2026 to Oct 26, 2026, rate on request. (location defaulted to the company yard (Savannah, GA); dates defaulted to today for 30 days; edit if needed.)",
            "note": "Not executed yet. The user must confirm this action in the app."
          }
        }
      ],
      "ts": "2026-09-27T00:11:02.098284+00:00"
    },
    {
      "role": "model",
      "text": "I can add 2 cranes to your inventory at your Savannah yard. Confirm below.",
      "ts": "2026-09-27T00:11:02.098284+00:00"
    },
    {
      "role": "note",
      "text": "Action ACT_LNND6Y confirmed: insert RES_AB4MPO",
      "ts": "2026-09-27T00:11:02.112146+00:00"
    },
    {
      "role": "user",
      "text": "add a bucket truck",
      "ts": "2026-09-27T00:11:02.120147+00:00"
    },
    {
      "role": "model",
      "text": null,
      "calls": [
        {
          "name": "add_resource",
          "args": {
            "name": "Bucket truck",
            "type": "equipment",
            "quantity": 1
          }
        }
      ],
      "ts": "2026-09-27T00:11:02.120147+00:00"
    },
    {
      "role": "tool",
      "results": [
        {
          "name": "add_resource",
          "response": {
            "pending_action_id": "ACT_EBAMVD",
            "summary": "Add 1 bucket truck to Demo Contractor A's inventory at Savannah, GA, available Sep 26, 2026 to Oct 26, 2026, rate on request. (location defaulted to the company yard (Savannah, GA); dates defaulted to today for 30 days; edit if needed.)",
            "note": "Not executed yet. The user must confirm this action in the app."
          }
        }
      ],
      "ts": "2026-09-27T00:11:02.120655+00:00"
    },
    {
      "role": "model",
      "text": "I can add 1 bucket truck. Confirm below.",
      "ts": "2026-09-27T00:11:02.120655+00:00"
    },
    {
      "role": "note",
      "text": "Action ACT_EBAMVD cancelled by the user.",
      "ts": "2026-09-27T00:11:02.126662+00:00"
    }
  ],
  "created_at": "2026-09-27T00:11:02.097285+00:00",
  "updated_at": "2026-09-27T00:11:02.126662+00:00",
  "pending_actions": [
    {
      "id": "ACT_LNND6Y",
      "thread_id": "THR_BG8MGV",
      "company_id": "CMP_A",
      "tool": "add_resource",
      "args": {
        "name": "Crane",
        "type": "equipment",
        "quantity": 2
      },
      "summary": "Add 2 cranes to Demo Contractor A's inventory at Savannah, GA, available Sep 26, 2026 to Oct 26, 2026, rate on request. (location defaulted to the company yard (Savannah, GA); dates defaulted to today for 30 days; edit if needed.)",
      "preview": {
        "collection": "resources",
        "fields": {
          "name": "Crane",
          "type": "equipment",
          "quantity": 2,
          "location": {
            "label": "Savannah, GA",
            "lat": 32.0809,
            "lon": -81.0912
          },
          "available_from": "2026-09-26",
          "available_to": "2026-10-26",
          "date_label": "Sep 26 – Oct 26, 2026",
          "daily_rate": null,
          "rate_label": "Rate on request",
          "notes": null
        },
        "location_point": {
          "lat": 32.0809,
          "lon": -81.0912
        }
      },
      "status": "confirmed",
      "created_at": "2026-09-27T00:11:02.098284+00:00",
      "expires_at": "2026-09-27T00:41:02+00:00",
      "result": {
        "id": "RES_AB4MPO",
        "company_id": "CMP_A",
        "company_name": "Demo Contractor A",
        "name": "Crane",
        "type": "equipment",
        "quantity": 2,
        "location": {
          "label": "Savannah, GA",
          "lat": 32.0809,
          "lon": -81.0912
        },
        "available_from": "2026-09-26",
        "available_to": "2026-10-26",
        "date_label": "Sep 26 – Oct 26, 2026",
        "daily_rate": null,
        "rate_label": "Rate on request",
        "notes": null,
        "nearby_project_ids": [
          "GPC_3",
          "USR_H010FE",
          "DESC_5",
          "DESC_3",
          "GPC_2"
        ],
        "created_at": "2026-09-27T00:11:02.112146+00:00",
        "updated_at": "2026-09-27T00:11:02.112146+00:00"
      },
      "error": null,
      "updated_at": "2026-09-27T00:11:02.112146+00:00"
    },
    {
      "id": "ACT_EBAMVD",
      "thread_id": "THR_BG8MGV",
      "company_id": "CMP_A",
      "tool": "add_resource",
      "args": {
        "name": "Bucket truck",
        "type": "equipment",
        "quantity": 1
      },
      "summary": "Add 1 bucket truck to Demo Contractor A's inventory at Savannah, GA, available Sep 26, 2026 to Oct 26, 2026, rate on request. (location defaulted to the company yard (Savannah, GA); dates defaulted to today for 30 days; edit if needed.)",
      "preview": {
        "collection": "resources",
        "fields": {
          "name": "Bucket truck",
          "type": "equipment",
          "quantity": 1,
          "location": {
            "label": "Savannah, GA",
            "lat": 32.0809,
            "lon": -81.0912
          },
          "available_from": "2026-09-26",
          "available_to": "2026-10-26",
          "date_label": "Sep 26 – Oct 26, 2026",
          "daily_rate": null,
          "rate_label": "Rate on request",
          "notes": null
        },
        "location_point": {
          "lat": 32.0809,
          "lon": -81.0912
        }
      },
      "status": "cancelled",
      "created_at": "2026-09-27T00:11:02.120147+00:00",
      "expires_at": "2026-09-27T00:41:02+00:00",
      "result": null,
      "error": null,
      "updated_at": "2026-09-27T00:11:02.126662+00:00"
    }
  ]
}
```

Example file: `examples/GET_agent_thread.json`

---

## Score v2 and sourced savings

### `GET /overlaps/{id}`

Every overlap now carries `score_breakdown` (proximity 40 + savings 40 + timing 20), `schedule_shift_possible`, and `cost_estimate` v2: `total_estimated_savings_usd` (point), `range_usd`, `components` (mobilization, logistics, shared_land, traffic_delay; each low/point/high), the reference budget and its source, plus `sources[]` (named public sources and the values used) and `assumptions[]`. Old fields are kept. `cost_scenario` keeps its shape; defaults now come from `config/cost_sources.json` (`defaults_source`, `unit_rates.crew_size`, `unit_rates.crew_cost_per_day`).

Response `200`:

```json
{
  "id": "OVL_DESC_23__GPC_20277",
  "project_a": "DESC_23",
  "project_b": "GPC_20277",
  "center_distance_mi": 5.66,
  "closest_distance_km": 4.89,
  "closest_points": {
    "a": {
      "lat": 32.360699,
      "lon": -81.124152
    },
    "b": {
      "lat": 32.352116,
      "lon": -81.175112
    }
  },
  "tier": "shared_site",
  "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
  "shared_endpoint": false,
  "time_gap_days": 152,
  "window_overlap_months": 24,
  "schedule_shift_possible": false,
  "timing_confidence": "predicted",
  "score": 64.6,
  "score_breakdown": {
    "proximity": 24.4,
    "savings": 20.2,
    "timing": 20.0
  },
  "rank": 1,
  "cost_estimate": {
    "total_estimated_savings_usd": 127061,
    "range_usd": [
      34660,
      373655
    ],
    "components": {
      "mobilization": {
        "low": 34320,
        "point": 125850,
        "high": 369300,
        "applies": true,
        "requires_schedule_shift": false
      },
      "logistics": {
        "low": 340,
        "point": 1211,
        "high": 4355,
        "applies": true,
        "site_to_site_road_miles": 6.8
      },
      "shared_land": {
        "low": 0,
        "point": 0,
        "high": 0,
        "applies": false
      },
      "traffic_delay": {
        "low": 0,
        "point": 0,
        "high": 0,
        "applies": false
      }
    },
    "reference_budget_usd": 5034000,
    "reference_budget_source": "predicted (ridge, Dominion budgets)",
    "shared_row_acres": null,
    "mobilization_savings_usd": 125850,
    "assumptions": [
      "The reference budget is an ML prediction (likely $3,432,000–$7,386,000); the savings range uses that budget range",
      "Share of one mobilization that can be shared: 25%–50% (assumption)",
      "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
    ],
    "sources": [
      {
        "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): McIntosh–Purrysburg",
        "value_used": "$5,034,000"
      },
      {
        "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
        "value_used": "4%–10% of the budget",
        "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
      },
      {
        "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
        "value_used": "$2.336/mile",
        "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
      }
    ]
  },
  "brief": null,
  "label": "Jasper–Okatie ↔ McIntosh–Purrysburg",
  "potential": "high",
  "cost_scenario": {
    "illustrative": true,
    "defaults_source": "cost_sources.json",
    "unit_rates": {
      "mobilization_per_event": 125800,
      "bucket_truck_per_day": 1500,
      "laydown_per_site": 5000,
      "crew_size": 4,
      "crew_cost_per_day": 1160
    },
    "separate": {
      "a": {
        "mobilization_events": 1,
        "truck_days": 10,
        "laydown_sites": 1,
        "start_date": "2023-08-31"
      },
      "b": {
        "mobilization_events": 1,
        "truck_days": 10,
        "laydown_sites": 1,
        "start_date": "2024-01-01"
      }
    },
    "coordinated": {
      "mobilization_events_a": 1,
      "mobilization_events_b": 1,
      "shared_truck_days": 12,
      "laydown_sites": 1,
      "start_date_a": "2023-08-31",
      "start_date_b": "2024-01-01"
    },
    "totals": {
      "separate": 291600,
      "coordinated": 274600,
      "savings": 17000,
      "savings_pct": 5.8,
      "separate_by_project": {
        "a": 145800,
        "b": 145800
      },
      "coordinated_by_project": {
        "a": 137300,
        "b": 137300
      }
    },
    "range": {
      "separate": [
        247860,
        335340
      ],
      "coordinated": [
        233410,
        315790
      ],
      "savings": [
        12750,
        21250
      ]
    },
    "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
    "assumptions": [
      "Unit rates are placeholders; replace with real bids.",
      "Trucks are shared only when construction windows overlap (yes for this pair).",
      "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
    ]
  },
  "kind": "cross_utility"
}
```

Example file: `examples/GET_overlap_v2.json`

---

### `GET /overlaps?project_id={id}`

Additive filter `project_id`: every opportunity one work site is part of, best first. The frontend uses it when a site is selected on the map.

Response `200`:

An **array** (11 items here). First item shown; every item has the same shape.

```json
[
  {
    "id": "OVL_DESC_23__GPC_20277",
    "project_a": "DESC_23",
    "project_b": "GPC_20277",
    "center_distance_mi": 5.66,
    "closest_distance_km": 4.89,
    "closest_points": {
      "a": {
        "lat": 32.360699,
        "lon": -81.124152
      },
      "b": {
        "lat": 32.352116,
        "lon": -81.175112
      }
    },
    "tier": "shared_site",
    "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
    "shared_endpoint": false,
    "time_gap_days": 152,
    "window_overlap_months": 24,
    "schedule_shift_possible": false,
    "timing_confidence": "predicted",
    "score": 64.6,
    "score_breakdown": {
      "proximity": 24.4,
      "savings": 20.2,
      "timing": 20.0
    },
    "rank": 1,
    "cost_estimate": {
      "total_estimated_savings_usd": 127061,
      "range_usd": [
        34660,
        373655
      ],
      "components": {
        "mobilization": {
          "low": 34320,
          "point": 125850,
          "high": 369300,
          "applies": true,
          "requires_schedule_shift": false
        },
        "logistics": {
          "low": 340,
          "point": 1211,
          "high": 4355,
          "applies": true,
          "site_to_site_road_miles": 6.8
        },
        "shared_land": {
          "low": 0,
          "point": 0,
          "high": 0,
          "applies": false
        },
        "traffic_delay": {
          "low": 0,
          "point": 0,
          "high": 0,
          "applies": false
        }
      },
      "reference_budget_usd": 5034000,
      "reference_budget_source": "predicted (ridge, Dominion budgets)",
      "shared_row_acres": null,
      "mobilization_savings_usd": 125850,
      "assumptions": [
        "The reference budget is an ML prediction (likely $3,432,000–$7,386,000); the savings range uses that budget range",
        "Share of one mobilization that can be shared: 25%–50% (assumption)",
        "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
      ],
      "sources": [
        {
          "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): McIntosh–Purrysburg",
          "value_used": "$5,034,000"
        },
        {
          "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
          "value_used": "4%–10% of the budget",
          "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
        },
        {
          "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
          "value_used": "$2.336/mile",
          "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
        }
      ]
    },
    "brief": null,
    "label": "Jasper–Okatie ↔ McIntosh–Purrysburg",
    "potential": "high",
    "cost_scenario": {
      "illustrative": true,
      "defaults_source": "cost_sources.json",
      "unit_rates": {
        "mobilization_per_event": 125800,
        "bucket_truck_per_day": 1500,
        "laydown_per_site": 5000,
        "crew_size": 4,
        "crew_cost_per_day": 1160
      },
      "separate": {
        "a": {
          "mobilization_events": 1,
          "truck_days": 10,
          "laydown_sites": 1,
          "start_date": "2023-08-31"
        },
        "b": {
          "mobilization_events": 1,
          "truck_days": 10,
          "laydown_sites": 1,
          "start_date": "2024-01-01"
        }
      },
      "coordinated": {
        "mobilization_events_a": 1,
        "mobilization_events_b": 1,
        "shared_truck_days": 12,
        "laydown_sites": 1,
        "start_date_a": "2023-08-31",
        "start_date_b": "2024-01-01"
      },
      "totals": {
        "separate": 291600,
        "coordinated": 274600,
        "savings": 17000,
        "savings_pct": 5.8,
        "separate_by_project": {
          "a": 145800,
          "b": 145800
        },
        "coordinated_by_project": {
          "a": 137300,
          "b": 137300
        }
      },
      "range": {
        "separate": [
          247860,
          335340
        ],
        "coordinated": [
          233410,
          315790
        ],
        "savings": [
          12750,
          21250
        ]
      },
      "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
      "assumptions": [
        "Unit rates are placeholders; replace with real bids.",
        "Trucks are shared only when construction windows overlap (yes for this pair).",
        "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
      ]
    },
    "kind": "cross_utility"
  }
]
```

Example file: `examples/GET_overlaps_for_site.json`

---

### `GET /meta`

`/meta` adds `method_notes[]` (About/method text) and `traffic_data`.

Response `200`:

```json
{
  "utilities": [
    {
      "code": "DESC",
      "name": "Dominion Energy South Carolina",
      "color": "#1F6FB2"
    },
    {
      "code": "GPC",
      "name": "Georgia Power",
      "color": "#D9822B"
    }
  ],
  "threshold_mi": 25,
  "generated_at": "2026-09-26",
  "tiers": [
    {
      "code": "crossing",
      "label": "Touching / crossing",
      "max_km": 0.05
    },
    {
      "code": "shared_land",
      "label": "Under 1.6 km",
      "max_km": 1.6
    },
    {
      "code": "shared_site",
      "label": "Under 8 km",
      "max_km": 8
    },
    {
      "code": "shared_crews",
      "label": "Under 40 km",
      "max_km": 40
    }
  ],
  "potential_levels": [
    {
      "code": "high",
      "label": "High potential",
      "min_score": 60
    },
    {
      "code": "moderate",
      "label": "Moderate potential",
      "min_score": 35
    },
    {
      "code": "lower",
      "label": "Lower potential",
      "min_score": 0
    }
  ],
  "in_service_years": [
    2023,
    2034
  ],
  "method_notes": [
    "Overlaps follow Sperry's rule: center points under 25 miles.",
    "Score = proximity 40 + savings 40 + timing 20. Savings already shrink with distance and when timing does not line up, so distance and timing partly count twice: proximity measures how practical coordination is, savings how much it is worth.",
    "Savings use Dominion's filed budgets, MISO per-mile estimates for Georgia Power's redacted budgets, the MoDOT mobilization benchmark, ATRI trucking costs, BLS wages, and USDA land values. The shareable fraction is an assumption, shown as a range.",
    "Traffic uses OpenStreetMap roads, SCDOT (2025) and GDOT (2017) traffic counts where available, MoDOT work-zone capacity, and USDOT value of time. Hourly profiles and closure durations are assumptions.",
    "Lines are straight-line approximations between substations, so crossings are approximate."
  ],
  "traffic_data": true
}
```

Example file: `examples/GET_meta_v2.json`

---

## Traffic management

### `GET /traffic/crossings?min_aadt=40000`

Where planned lines cross major roads (OSM), with traffic volume (SCDOT 2025 / GDOT 2017 counts, else a labeled class estimate), closure type, the recommended closure window and its delay, and the worst window. Filters: `project_id`, `road_ref`, `min_aadt`. Crossing points are approximate (straight lines).

Response `200`:

An **array** (12 items here). First item shown; every item has the same shape.

```json
[
  {
    "id": "XING_DESC_23_3",
    "project_id": "DESC_23",
    "road_name": null,
    "road_ref": "I-95",
    "road_refs": [
      "I-95"
    ],
    "road_class": "motorway",
    "lanes": 2,
    "lanes_assumed": false,
    "oneway": true,
    "aadt": 55500,
    "aadt_source": "SCDOT 2025 statewide traffic counts (I-95, station 4.1 km away)",
    "osm_id": 156558742,
    "point": {
      "lat": 32.338528,
      "lon": -81.048702
    },
    "point_approximate": true,
    "est_closure_hours": 8,
    "work_window": {
      "start": "2023-08-31",
      "end": "2025-12-31",
      "source": "predicted",
      "prediction": {
        "months": 27.8,
        "low": 19.3,
        "high": 36.3,
        "typical_error_months": 8.5,
        "method": "random_forest",
        "trained_on": "205 Georgia Power projects (filed start and need dates)",
        "label": "predicted"
      }
    },
    "owner": "DESC",
    "closure_type": "lane_closure",
    "closure_hours": 8,
    "recommended_window": "19:00–03:00",
    "delay_veh_hours": 0.0,
    "vehicles_affected": 5128,
    "delay_cost_usd": 0,
    "worst_window": "14:00–22:00",
    "worst_delay_veh_hours": 11600.2
  }
]
```

Example file: `examples/GET_traffic_crossings.json`

---

### `GET /traffic/crossings/{id}`

One crossing with its full plan: `hourly` (24 x demand, capacity, queue) for a chart, sources and assumptions, and any closure conflicts on the same road.

Response `200`:

```json
{
  "id": "XING_DESC_23_3",
  "project_id": "DESC_23",
  "road_name": null,
  "road_ref": "I-95",
  "road_refs": [
    "I-95"
  ],
  "road_class": "motorway",
  "lanes": 2,
  "lanes_assumed": false,
  "oneway": true,
  "aadt": 55500,
  "aadt_source": "SCDOT 2025 statewide traffic counts (I-95, station 4.1 km away)",
  "osm_id": 156558742,
  "point": {
    "lat": 32.338528,
    "lon": -81.048702
  },
  "point_approximate": true,
  "est_closure_hours": 8,
  "work_window": {
    "start": "2023-08-31",
    "end": "2025-12-31",
    "source": "predicted",
    "prediction": {
      "months": 27.8,
      "low": 19.3,
      "high": 36.3,
      "typical_error_months": 8.5,
      "method": "random_forest",
      "trained_on": "205 Georgia Power projects (filed start and need dates)",
      "label": "predicted"
    }
  },
  "owner": "DESC",
  "closure_type": "lane_closure",
  "closure_hours": 8,
  "recommended_window": "19:00–03:00",
  "delay_veh_hours": 0.0,
  "vehicles_affected": 5128,
  "delay_cost_usd": 0,
  "worst_window": "14:00–22:00",
  "worst_delay_veh_hours": 11600.2,
  "plan": {
    "closure_type": "lane_closure",
    "closure_hours": 8,
    "recommended_window": "19:00–03:00",
    "recommended_start_hour": 19,
    "delay_veh_hours": 0.0,
    "vehicles_affected": 5128,
    "delay_cost_usd": 0,
    "worst_window": "14:00–22:00",
    "worst_delay_veh_hours": 11600.2,
    "worst_delay_cost_usd": 338146,
    "hourly": [
      {
        "hour": 0,
        "demand": 305,
        "capacity": 1600,
        "queue": 0
      },
      {
        "hour": 1,
        "demand": 244,
        "capacity": 1600,
        "queue": 0
      },
      {
        "hour": 2,
        "demand": 214,
        "capacity": 1600,
        "queue": 0
      },
      {
        "hour": 3,
        "demand": 214,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 4,
        "demand": 305,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 5,
        "demand": 672,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 6,
        "demand": 1526,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 7,
        "demand": 2289,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 8,
        "demand": 2137,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 9,
        "demand": 1587,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 10,
        "demand": 1435,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 11,
        "demand": 1526,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 12,
        "demand": 1618,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 13,
        "demand": 1648,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 14,
        "demand": 1770,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 15,
        "demand": 2015,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 16,
        "demand": 2320,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 17,
        "demand": 2381,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 18,
        "demand": 1954,
        "capacity": 3800,
        "queue": 0
      },
      {
        "hour": 19,
        "demand": 1404,
        "capacity": 1600,
        "queue": 0
      },
      {
        "hour": 20,
        "demand": 1099,
        "capacity": 1600,
        "queue": 0
      },
      {
        "hour": 21,
        "demand": 885,
        "capacity": 1600,
        "queue": 0
      },
      {
        "hour": 22,
        "demand": 641,
        "capacity": 1600,
        "queue": 0
      },
      {
        "hour": 23,
        "demand": 336,
        "capacity": 1600,
        "queue": 0
      }
    ],
    "sources": [
      {
        "name": "MoDOT EPG 616.13 Work Zone Capacity, Queue and Travel Delay (base work zone capacity 1600 pc/h/ln)",
        "value_used": "1600 veh/h/lane in a work zone",
        "url": "https://epg.modot.org/index.php/616.13_Work_Zone_Capacity,_Queue_and_Travel_Delay"
      },
      {
        "name": "USDOT Benefit-Cost Analysis Guidance, 2026 update (federal values as restated in Caltrans Cal-B/C federal comparison, 2026)",
        "value_used": "$29.15/vehicle-hour (2024$)",
        "url": "https://www.transportation.gov/sites/dot.gov/files/2025-12/Benefit%20Cost%20Analysis%20Guidance%202026%20Update%20(Final).pdf"
      }
    ],
    "assumptions": [
      "8-hour closure (assumption)",
      "Typical weekday hourly profile (assumption)",
      "Peak-direction split 55% (assumption)"
    ]
  },
  "conflicts": []
}
```

Example file: `examples/GET_traffic_crossing.json`

---

### `POST /traffic/plan`

Plan any proposed closure: nearest matching road to the point, optional overrides (`lanes`, `aadt`, `closure_hours`, `closure_type`).

Request body:
```json
{
  "point": {
    "lat": 32.2871,
    "lon": -81.079
  },
  "road_ref": "US-17",
  "closure_hours": 8
}
```

Response `200`:

```json
{
  "road": {
    "road_name": "Whyte Hardee Boulevard",
    "road_ref": "US-17",
    "road_refs": [
      "US-17"
    ],
    "road_class": "primary",
    "lanes": 4,
    "lanes_assumed": false,
    "oneway": false,
    "aadt": 11100,
    "aadt_source": "SCDOT 2025 statewide traffic counts (US-17, station 0.2 km away)",
    "osm_id": 138272923
  },
  "closure_type": "lane_closure",
  "closure_hours": 8,
  "recommended_window": "00:00–08:00",
  "recommended_start_hour": 0,
  "delay_veh_hours": 0.0,
  "vehicles_affected": 2098,
  "delay_cost_usd": 0,
  "worst_window": "00:00–08:00",
  "worst_delay_veh_hours": 0.0,
  "worst_delay_cost_usd": 0,
  "hourly": [
    {
      "hour": 0,
      "demand": 111,
      "capacity": 3200,
      "queue": 0
    },
    {
      "hour": 1,
      "demand": 89,
      "capacity": 3200,
      "queue": 0
    },
    {
      "hour": 2,
      "demand": 78,
      "capacity": 3200,
      "queue": 0
    },
    {
      "hour": 3,
      "demand": 78,
      "capacity": 3200,
      "queue": 0
    },
    {
      "hour": 4,
      "demand": 111,
      "capacity": 3200,
      "queue": 0
    },
    {
      "hour": 5,
      "demand": 244,
      "capacity": 3200,
      "queue": 0
    },
    {
      "hour": 6,
      "demand": 555,
      "capacity": 3200,
      "queue": 0
    },
    {
      "hour": 7,
      "demand": 832,
      "capacity": 3200,
      "queue": 0
    },
    {
      "hour": 8,
      "demand": 777,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 9,
      "demand": 577,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 10,
      "demand": 522,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 11,
      "demand": 555,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 12,
      "demand": 588,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 13,
      "demand": 599,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 14,
      "demand": 644,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 15,
      "demand": 733,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 16,
      "demand": 844,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 17,
      "demand": 866,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 18,
      "demand": 710,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 19,
      "demand": 511,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 20,
      "demand": 400,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 21,
      "demand": 322,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 22,
      "demand": 233,
      "capacity": 7600,
      "queue": 0
    },
    {
      "hour": 23,
      "demand": 122,
      "capacity": 7600,
      "queue": 0
    }
  ],
  "sources": [
    {
      "name": "MoDOT EPG 616.13 Work Zone Capacity, Queue and Travel Delay (base work zone capacity 1600 pc/h/ln)",
      "value_used": "1600 veh/h/lane in a work zone",
      "url": "https://epg.modot.org/index.php/616.13_Work_Zone_Capacity,_Queue_and_Travel_Delay"
    },
    {
      "name": "USDOT Benefit-Cost Analysis Guidance, 2026 update (federal values as restated in Caltrans Cal-B/C federal comparison, 2026)",
      "value_used": "$29.15/vehicle-hour (2024$)",
      "url": "https://www.transportation.gov/sites/dot.gov/files/2025-12/Benefit%20Cost%20Analysis%20Guidance%202026%20Update%20(Final).pdf"
    }
  ],
  "assumptions": [
    "8-hour closure (assumption)",
    "Typical weekday hourly profile (assumption)",
    "Peak-direction split 55% (assumption)"
  ]
}
```

Example file: `examples/POST_traffic_plan.json`

---

### `GET /traffic/conflicts`

Two owners closing the same road within 3 km while both are under construction: delay if merged into one closure (sign kept), closures and traffic-control setups avoided. Filters `kind`, `min_delay`.

Response `200`:

An **array** (0 items here). First item shown; every item has the same shape.

```json
[]
```

Example file: `examples/GET_traffic_conflicts.json`

---

### `GET /traffic/summary`

Dashboard tile.

Response `200`:

```json
{
  "crossings_count": 158,
  "projects_with_crossings": 19,
  "high_volume_crossings": 28,
  "conflicts_count": 0,
  "total_delay_avoidable_veh_hours": 0,
  "daytime_vs_night_delay_veh_hours": {
    "worst_windows": 33242.6,
    "recommended_windows": 0
  },
  "data_sources": [
    "OpenStreetMap roads (Overpass)",
    "SCDOT 2025 statewide traffic counts",
    "GDOT traffic counts (2017 AADT)"
  ]
}
```

Example file: `examples/GET_traffic_summary.json`

---

### `POST /traffic/crossings/{id}/brief`

Gemini traffic-management note for one crossing, from computed facts only (number guard + template fallback). `POST /overlaps/{id}/brief` also accepts `mode: "traffic"`.

Request body:
```json
{}
```

Response `200`:

```json
{
  "crossing_id": "XING_DESC_23_3",
  "mode": "traffic",
  "brief": "Jasper–Okatie crosses I-95 (55,500 vehicles/day). Close it 19:00–03:00: about 0.0 vehicle-hours of delay versus 11600.2 for a 14:00–22:00 closure.",
  "source": "fallback",
  "cached": false
}
```

Example file: `examples/POST_crossing_brief.json`

---

## Contract upload

### `POST /contracts/analyze`

Multipart upload, form field `file` (PDF, 10 MB max). Text is extracted with pdfplumber; Gemini returns each field with an exact `evidence` quote. Code drops a field when its quote is not in the document or its numbers are not in the quote. Scanned PDFs: `422 NO_TEXT_LAYER`; non-PDF: `415 UNSUPPORTED_FILE`. The PDF is not stored, only its text hash and the fields.

Response `201`:

```json
{
  "contract_id": "CTR_TJYZLK",
  "filename": "sample_contract_hardeeville.pdf",
  "status": "needs_review",
  "fields": {
    "project_name": {
      "value": "Hardeeville Area Reliability Project - Jasper to Bluffton 115 kV Line Rebuild",
      "confidence": "high",
      "evidence": "Project name: Hardeeville Area Reliability Project - Jasper to Bluffton 115 kV Line Rebuild"
    },
    "owner_company": {
      "value": "Lowcountry Line Builders LLC (fictional)",
      "confidence": "high",
      "evidence": "Owner: Lowcountry Line Builders LLC (fictional)"
    },
    "utility": {
      "value": "Dominion Energy South Carolina",
      "confidence": "high",
      "evidence": "Utility: Dominion Energy South Carolina"
    },
    "work_type": {
      "value": "Transmission line rebuild",
      "confidence": "high",
      "evidence": "Work type: Transmission line rebuild"
    },
    "voltage_kv": {
      "value": 115,
      "confidence": "high",
      "evidence": "Voltage: 115 kV"
    },
    "endpoints": {
      "value": [
        "Jasper Substation",
        "Bluffton Substation"
      ],
      "confidence": "high",
      "evidence": "Endpoints: Jasper Substation to Bluffton Substation"
    },
    "location_text": {
      "value": "Hardeeville, Jasper County, SC",
      "confidence": "high",
      "evidence": "Location: Hardeeville, Jasper County, SC"
    },
    "line_miles": {
      "value": 17.5,
      "confidence": "high",
      "evidence": "Line length: 17.5 miles"
    },
    "start_date": {
      "value": "2027-06-01",
      "confidence": "high",
      "evidence": "Start date: June 1, 2027"
    },
    "end_date": {
      "value": "2027-12-15",
      "confidence": "high",
      "evidence": "Completion date: December 15, 2027"
    },
    "budget_usd": {
      "value": 9850000,
      "confidence": "high",
      "evidence": "Contract price: $9,850,000"
    },
    "crew_size": {
      "value": 14,
      "confidence": "high",
      "evidence": "Crew size: 14 workers"
    },
    "equipment": {
      "value": [
        {
          "type": "bucket trucks",
          "quantity": 3
        },
        {
          "type": "60-ton crane",
          "quantity": 1
        },
        {
          "type": "digger derricks",
          "quantity": 2
        }
      ],
      "confidence": "high",
      "evidence": "Equipment: 3 bucket trucks, 1 60-ton crane, 2 digger derricks"
    },
    "roads_affected": {
      "value": "US-17, I-95",
      "confidence": "high",
      "evidence": "Roads affected: US-17, I-95"
    },
    "lane_closures": {
      "value": "Nighttime northbound lane closure on US-17 near Hardeeville",
      "confidence": "high",
      "evidence": "Lane closures: Nighttime northbound lane closure on US-17 near Hardeeville"
    },
    "work_hours": {
      "value": "21:00-05:00",
      "confidence": "high",
      "evidence": "Work hours: 21:00-05:00"
    }
  },
  "missing": [],
  "dropped_fields": [],
  "ready": true,
  "follow_up_questions": [],
  "
```

Example file: `examples/POST_contracts_analyze.json`

---

### `POST /contracts/{id}/match`

Body: the reviewed fields (`{fields: {...}}`, only the ones the user changed). Locates the work (substation matcher, else Nominatim), compares it with every planned project under 25 mi, and returns `matches` sorted by score (with `score_breakdown`, `cost_estimate` v2, `suggestion`, `shared_roads`), `best_match`, the contract's own `traffic`, and a `summary`.

Headers: `X-Company-Id: CMP_A`

Request body:
```json
{
  "fields": {}
}
```

Response `200`:

```json
{
  "contract_id": "CTR_TJYZLK",
  "project": {
    "id": "CTR_TJYZLK",
    "utility": "USER",
    "utility_name": "Lowcountry Line Builders LLC (fictional)",
    "state": null,
    "name": "Hardeeville Area Reliability Project - Jasper to Bluffton 115 kV Line Rebuild",
    "short_name": "Hardeeville Area Reliability Project - …",
    "voltage_kv": 115,
    "project_type": "line",
    "status": "Planned",
    "in_service_date": "2027-12-15",
    "construction_window": {
      "start": "2027-06-01",
      "end": "2027-12-15",
      "source": "contract"
    },
    "endpoints": [
      {
        "name": "Jasper Substation",
        "lat": 32.360699,
        "lon": -81.124152,
        "confidence": "medium",
        "source": "OSM way/185380597 \"Jasper Substation\"",
        "county": null
      },
      {
        "name": "Bluffton Substation",
        "lat": 32.235027,
        "lon": -80.853384,
        "confidence": "high",
        "source": "OSM way/498967268 \"Bluffton Substation\"",
        "county": null
      }
    ],
    "center": {
      "lat": 32.297863,
      "lon": -80.988768
    },
    "geometry": {
      "type": "LineString",
      "coordinates": [
        [
          -81.124152,
          32.360699
        ],
        [
          -80.853384,
          32.235027
        ]
      ]
    },
    "location_confidence": "high",
    "description": "Transmission line rebuild",
    "cost": null,
    "source": {
      "document": "Uploaded contract",
      "page": null,
      "type": "contract"
    },
    "quality_flags": [],
    "overlap_ids": [],
    "work_type_label": "Transmission line rebuild",
    "counties": [],
    "company_id": "CMP_A",
    "roads_affected": [
      "US-17",
      "I-95"
    ],
    "lane_closures": "Nighttime northbound lane closure on US-17 near Hardeeville",
    "work_hours": "21:00-05:00",
    "geocoded": null,
    "line_miles": 17.5,
    "budget_usd": 9850000,
    "budget_source": "contract",
    "budget_note": "Stated in the uploaded contract"
  },
  "work_timing": {
    "headline": "Do the road-crossing work at night, 8 PM to 4 AM. Other construction nearby runs through your whole schedule, so the month doesn't change much.",
    "best_hours": {
      "start_hour": 20,
      "hours": 8,
      "label": "8 PM to 4 AM"
    },
    "best_months": [
      "Jun–Dec 2027"
    ],
    "reasons": [
      "I-95 is one of the busiest roads in the area. Closing a lane there during the day would cause very long backups, with traffic stopped for hours; from 8 PM to 4 AM traffic keeps moving.",
      "Buckwalter Parkway is a busy road. Closing a lane there during the day would cause very long backups, with traffic stopped for hours; from 8 PM to 4 AM traffic keeps moving.",
      "SC-46 is a busy road. Closing a lane there during the day would cause long backups; from 7 PM to 3 AM traffic keeps moving.",
      "US-278, Bruin Road, US-17, SC-170 and US-321 are quiet enough to work on at any time of day.",
      "Corridor upgrade (Demo Contractor B) will also be working on US-17 during Jun–Dec 2027. Avoid those months for that road, or agree on one shared closure with them so drivers are only disrupted once.",
      "Coleman–Dean Forest, Magnolia–Truman Parkway, Boulevard–Magnolia and 1 more are also under construction within 25 miles during your schedule, which adds trucks and crews to the area's roads."
    ],
    "nearby_active": [
      {
        "project_id": "GPC_20783",
        "short_name": "Coleman–Dean Forest",
        "window": {
          "start": "2025-06-01",
          "end": "2028-06-01",
          "source": "gpc_start_date"
        },
        "shared_roads": []
      },
      {
        "project_id": "GPC_20407",
        "short_name": "Magnolia–Truman Parkway",
        "window": {
          "start": "2025-06-01",
          "end": "2028-06-01",
          "source": "gpc_start_date"
        },
        "shared_roads": []
      },
      {
        "project_id": "GPC_21006",
        "short_name": "Boulevard–Magnolia",
        "window": {
          "start": "2027-01-01",
          "end": "2029-06-01",
          "source": "gpc_start_date"
        },
        "shared_roads": []
      },
      {
        "project_id": "GPC_21023",
        "short_name": "Dean Forest–Little Ogeechee",
        "window": {
          "start": "2026-01-01",
          "end": "2029-06-01",
          "source": "gpc_start_date"
        },
        "shared_roads": []
      },
      {
        "project_id": "USR_H010FE",
        "short_name": "Corridor upgrade",
        "window": {
          "start": "2027-06-01",
          "end": "2028-02-01",
          "source": "user"
        },
        "shared_roads": [
          "US-17"
        ]
      }
    ],
    "basis": "Road traffic counts (SCDOT/GDOT, else road-class estimates), a work-zone queue model, and the construction windows of every planned project within 25 miles."
  },
  "matches": [
    {
      "project_id": "USR_H010FE",
      "short_name": "Corridor upgrade",
      "name": "Corridor upgrade",
      "utility": "USER",
      "utility_name": "Demo Contractor B",
      "center_distance_mi": 5.32,
      "closest_distance_km": 5.13,
      "tier": "shared_site",
      "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
      "window_overlap_months": 6,
      "schedule_shift_possible": false,
      "score": 54.4,
      "score_breakdown": {
        "proximity": 24.3,
        "savings": 20.1,
        "timing": 10.0
      },
      "potential": "moderate",
      "cost_estimate": {
        "total_estimated_savings_usd": 247473,
        "range_usd": [
          98848,
          496874
        ],
        "components": {
          "mobilization": {
            "low": 98500,
            "point": 246250,
            "high": 492500,
            "applies": true,
            "requires_schedule_shift": false
          },
          "logistics": {
            "low": 348,
            "point": 1223,
            "high": 4374,
            "applies": true,
            "site_to_site_road_miles": 6.4
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 9850000,
        "reference_budget_source": "contract",
        "shared_row_acres": null,
        "mobilization_savings_usd": 246250,
        "assumptions": [
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "Uploaded contract (budget): Hardeeville Area Reliability Project - …",
            "value_used": "$9,850,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "suggestion": {
        "shift_months": 1,
        "suggested_window": {
          "start": "2027-07-01",
          "end": "2028-01-15"
        },
        "explanation": "Moving the window 1 months later increases shared construction time with nearby projects from 6 to 7 months, so crews and equipment can be shared."
      },
      "shared_roads": []
    },
    {
      "project_id": "GPC_20065",
      "short_name": "Goshen–McIntosh",
      "name": "SAV: GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "center_distance_mi": 11.89,
      "closest_distance_km": 4.89,
      "tier": "shared_site",
      "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
      "window_overlap_months": 0,
      "schedule_shift_possible": true,
      "score": 40.5,
      "score_breakdown": {
        "proximity": 24.4,
        "savings": 10.1,
        "timing": 6.0
      },
      "potential": "moderate",
      "cost_estimate": {
        "total_estimated_savings_usd": 93427,
        "range_usd": [
          25401,
          275180
        ],
        "components": {
          "mobilization": {
            "low": 25200,
            "point": 92425,
            "high": 271175,
            "applies": true,
            "requires_schedule_shift": true
          },
          "logistics": {
            "low": 201,
            "point": 1002,
            "high": 4005,
            "applies": true,
            "site_to_site_road_miles": 14.3
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 7394000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": 92425,
        "assumptions": [
          "The reference budget is an ML prediction (likely $5,040,000–$10,847,000); the savings range uses that budget range",
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Mobilization savings halved: the construction windows only overlap after a schedule shift",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Goshen–McIntosh",
            "value_used": "$7,394,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "suggestion": {
        "shift_months": -6,
        "suggested_window": {
          "start": "2026-12-01",
          "end": "2027-06-15"
        },
        "explanation": "Moving the window 6 months earlier increases shared construction time with nearby projects from 0 to 6 months, so crews and equipment can be shared."
      },
      "shared_roads": []
    },
    {
      "project_id": "DESC_10",
      "short_name": "Okatie–Bluffton",
      "name": "Okatie-Bluffton 115kV: Rebuild",
      "utility": "DESC",
      "utility_name": "Dominion Energy South Carolina",
      "center_distance_mi": 2.83,
      "closest_distance_km": 0.0,
      "tier": "crossing",
      "tier_explanation": "Touching/crossing: must coordinate outages and crossing structures",
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "score": 40.0,
      "score_breakdown": {
        "proximity": 40.0,
        "savings": 0.0,
        "timing": 0.0
      },
      "potential": "moderate",
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap",
            "acres": 139.5
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 9850000,
        "reference_budget_source": "contract",
        "shared_row_acres": 139.5,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "Uploaded contract (budget): Hardeeville Area Reliability Project - …",
            "value_used": "$9,850,000"
          }
        ]
      },
      "suggestion": {
        "shift_months": 0,
        "suggested_window": {
          "start": "2027-06-01",
          "end": "2027-12-15"
        },
        "explanation": "Nearby projects finish before this one could start, so no future shift creates shared construction time. Coordinate on staging yards and permits instead."
      },
      "shared_roads": []
    },
    {
      "project_id": "DESC_23",
      "short_name": "Jasper–Okatie",
      "name": "Jasper – Okatie 230 kV #2: Construct",
      "utility": "DESC",
      "utility_name": "Dominion Energy South Carolina",
      "center_distance_mi": 6.24,
      "closest_distance_km": 0.0,
      "tier": "crossing",
      "tier_explanation": "Touching/crossing: must coordinate outages and crossing structures",
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "score": 40.0,
      "score_breakdown": {
        "proximity": 40.0,
        "savings": 0.0,
        "timing": 0.0
      },
      "potential": "moderate",
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap",
            "acres": 89.8
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 9850000,
        "reference_budget_source": "contract",
        "shared_row_acres": 89.8,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "Uploaded contract (budget): Hardeeville Area Reliability Project - …",
            "value_used": "$9,850,000"
          }
        ]
      },
      "suggestion": {
        "shift_months": 0,
        "suggested_window": {
          "start": "2027-06-01",
          "end": "2027-12-15"
        },
        "explanation": "Nearby projects finish before this one could start, so no future shift creates shared construction time. Coordinate on staging yards and permits instead."
      },
      "shared_roads": []
    },
    {
      "project_id": "GPC_20783",
      "short_name": "Coleman–Dean Forest",
      "name": "SAV: COLEMAN - DEAN FOREST 115KV LINE REBUILD",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "center_distance_mi": 17.23,
      "closest_distance_km": 25.27,
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "window_overlap_months": 6,
      "schedule_shift_possible": false,
      "score": 39.7,
      "score_breakdown": {
        "proximity": 9.6,
        "savings": 20.1,
        "timing": 10.0
      },
      "potential": "moderate",
      "cost_estimate": {
        "total_estimated_savings_usd": 185297,
        "range_usd": [
          50381,
          544956
        ],
        "components": {
          "mobilization": {
            "low": 50300,
            "point": 184475,
            "high": 541250,
            "applies": true,
            "requires_schedule_shift": false
          },
          "logistics": {
            "low": 81,
            "point": 822,
            "high": 3706,
            "applies": true,
            "site_to_site_road_miles": 20.7
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 7379000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": 184475,
        "assumptions": [
          "The reference budget is an ML prediction (likely $5,030,000–$10,825,000); the savings range uses that budget range",
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Coleman–Dean Forest",
            "value_used": "$7,379,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "suggestion": {
        "shift_months": -1,
        "suggested_window": {
          "start": "2027-05-01",
          "end": "2027-11-15"
        },
        "explanation": "Moving the window 1 months earlier increases shared construction time with nearby projects from 6 to 7 months, so crews and equipment can be shared."
      },
      "shared_roads": []
    },
    {
      "project_id": "GPC_21023",
      "short_name": "Dean Forest–Little Ogeechee",
      "name": "SAV: DEAN FOREST - LITTLE OGEECHEE 230 KV REBUILD",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "center_distance_mi": 22.12,
      "closest_distance_km": 29.89,
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "window_overlap_months": 6,
      "schedule_shift_possible": false,
      "score": 38.9,
      "score_breakdown": {
        "proximity": 8.8,
        "savings": 20.1,
        "timing": 10.0
      },
      "potential": "moderate",
      "cost_estimate": {
        "total_estimated_savings_usd": 246908,
        "range_usd": [
          98471,
          495932
        ],
        "components": {
          "mobilization": {
            "low": 98500,
            "point": 246250,
            "high": 492500,
            "applies": true,
            "requires_schedule_shift": false
          },
          "logistics": {
            "low": -29,
            "point": 658,
            "high": 3432,
            "applies": true,
            "site_to_site_road_miles": 26.5
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 9850000,
        "reference_budget_source": "contract",
        "shared_row_acres": null,
        "mobilization_savings_usd": 246250,
        "assumptions": [
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "Uploaded contract (budget): Hardeeville Area Reliability Project - …",
            "value_used": "$9,850,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "suggestion": {
        "shift_months": -1,
        "suggested_window": {
          "start": "2027-05-01",
          "end": "2027-11-15"
        },
        "explanation": "Moving the window 1 months earlier increases shared construction time with nearby projects from 6 to 7 months, so crews and equipment can be shared."
      },
      "shared_roads": []
    },
    {
      "project_id": "GPC_21006",
      "short_name": "Boulevard–Magnolia",
      "name": "SAV: BOULEVARD - MAGNOLIA 115 KV LINE REBUILD",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "center_distance_mi": 19.81,
      "closest_distance_km": 31.19,
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "window_overlap_months": 6,
      "schedule_shift_possible": false,
      "score": 38.6,
      "score_breakdown": {
        "proximity": 8.5,
        "savings": 20.1,
        "timing": 10.0
      },
      "potential": "moderate",
      "cost_estimate": {
        "total_estimated_savings_usd": 156485,
        "range_usd": [
          42493,
          460561
        ],
        "components": {
          "mobilization": {
            "low": 42470,
            "point": 155750,
            "high": 457000,
            "applies": true,
            "requires_schedule_shift": false
          },
          "logistics": {
            "low": 23,
            "point": 735,
            "high": 3561,
            "applies": true,
            "site_to_site_road_miles": 23.8
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 6230000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": 155750,
        "assumptions": [
          "The reference budget is an ML prediction (likely $4,247,000–$9,140,000); the savings range uses that budget range",
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Boulevard–Magnolia",
            "value_used": "$6,230,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "suggestion": {
        "shift_months": -1,
        "suggested_window": {
          "start": "2027-05-01",
          "end": "2027-11-15"
        },
        "explanation": "Moving the window 1 months earlier increases shared construction time with nearby projects from 6 to 7 months, so crews and equipment can be shared."
      },
      "shared_roads": []
    },
    {
      "project_id": "GPC_20407",
      "short_name": "Magnolia–Truman Parkway",
      "name": "SAV: MAGNOLIA - TRUMAN PARKWAY 115KV REBUILD",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "center_distance_mi": 19.85,
      "closest_distance_km": 31.19,
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "window_overlap_months": 6,
      "schedule_shift_possible": false,
      "score": 38.6,
      "score_breakdown": {
        "proximity": 8.5,
        "savings": 20.1,
        "timing": 10.0
      },
      "potential": "moderate",
      "cost_estimate": {
        "total_estimated_savings_usd": 131709,
        "range_usd": [
          35732,
          387859
        ],
        "components": {
          "mobilization": {
            "low": 35710,
            "point": 130975,
            "high": 384300,
            "applies": true,
            "requires_schedule_shift": false
          },
          "logistics": {
            "low": 22,
            "point": 734,
            "high": 3559,
            "applies": true,
            "site_to_site_road_miles": 23.8
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 5239000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": 130975,
        "assumptions": [
          "The reference budget is an ML prediction (likely $3,571,000–$7,686,000); the savings range uses that budget range",
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Magnolia–Truman Parkway",
            "value_used": "$5,239,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "suggestion": {
        "shift_months": -1,
        "suggested_window": {
          "start": "2027-05-01",
          "end": "2027-11-15"
        },
        "explanation": "Moving the window 1 months earlier increases shared construction time with nearby projects from 6 to 7 months, so crews and equipment can be shared."
      },
      "shared_roads": []
    },
    {
      "project_id": "DESC_3",
      "short_name": "Okatie",
      "name": "Okatie 230-115kV Substation, Jasper – Yemassee 230kV #1 Fold-in",
      "utility": "DESC",
      "utility_name": "Dominion Energy South Carolina",
      "center_distance_mi": 3.56,
      "closest_distance_km": 1.51,
      "tier": "shared_land",
      "tier_explanation": "Under 1.6 km: can share right-of-way, access roads, permits",
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "score": 33.4,
      "score_breakdown": {
        "proximity": 33.4,
        "savings": 0.0,
        "timing": 0.0
      },
      "potential": "lower",
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 9850000,
        "reference_budget_source": "contract",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "Uploaded contract (budget): Hardeeville Area Reliability Project - …",
            "value_used": "$9,850,000"
          }
        ]
      },
      "suggestion": {
        "shift_months": 0,
        "suggested_window": {
          "start": "2027-06-01",
          "end": "2027-12-15"
        },
        "explanation": "Nearby projects finish before this one could start, so no future shift creates shared construction time. Coordinate on staging yards and permits instead."
      },
      "shared_roads": []
    },
    {
      "project_id": "GPC_20785",
      "short_name": "Goshen–Kraft",
      "name": "SAV: GOSHEN (SAV) - KRAFT 115KV LINE REBUILD",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "center_distance_mi": 13.01,
      "closest_distance_km": 14.79,
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "window_overlap_months": 0,
      "schedule_shift_possible": true,
      "score": 27.5,
      "score_breakdown": {
        "proximity": 11.4,
        "savings": 10.1,
        "timing": 6.0
      },
      "potential": "lower",
      "cost_estimate": {
        "total_estimated_savings_usd": 108676,
        "range_usd": [
          29545,
          319968
        ],
        "components": {
          "mobilization": {
            "low": 29370,
            "point": 107712,
            "high": 316025,
            "applies": true,
            "requires_schedule_shift": true
          },
          "logistics": {
            "low": 175,
            "point": 964,
            "high": 3943,
            "applies": true,
            "site_to_site_road_miles": 15.6
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 8617000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": 107712,
        "assumptions": [
          "The reference budget is an ML prediction (likely $5,874,000–$12,641,000); the savings range uses that budget range",
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Mobilization savings halved: the construction windows only overlap after a schedule shift",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Goshen–Kraft",
            "value_used": "$8,617,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "suggestion": {
        "shift_months": -6,
        "suggested_window": {
          "start": "2026-12-01",
          "end": "2027-06-15"
        },
        "explanation": "Moving the window 6 months earlier increases shared construction time with nearby projects from 0 to 6 months, so crews and equipment can be shared."
      },
      "shared_roads": []
    },
    {
      "project_id": "GPC_20277",
      "short_name": "McIntosh–Purrysburg",
      "name": "SAV: MCINTOSH - PURRYSBURG 230KV REACTORS",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "center_distance_mi": 11.51,
      "closest_distance_km": 4.89,
      "tier": "shared_site",
      "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "score": 24.4,
      "score_breakdown": {
        "proximity": 24.4,
        "savings": 0.0,
        "timing": 0.0
      },
      "potential": "lower",
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 5034000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): McIntosh–Purrysburg",
            "value_used": "$5,034,000"
          }
        ]
      },
      "suggestion": {
        "shift_months": 0,
        "suggested_window": {
          "start": "2027-06-01",
          "end": "2027-12-15"
        },
        "explanation": "Nearby projects finish before this one could start, so no future shift creates shared construction time. Coordinate on staging yards and permits instead."
      },
      "shared_roads": []
    },
    {
      "project_id": "GPC_20066",
      "short_name": "Boulevard–Deptford",
      "name": "SAV: BOULEVARD - DEPTFORD 115KV RECONDUCTOR",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "center_distance_mi": 17.99,
      "closest_distance_km": 25.18,
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "score": 9.6,
      "score_breakdown": {
        "proximity": 9.6,
        "savings": 0.0,
        "timing": 0.0
      },
      "potential": "lower",
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 7838000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Boulevard–Deptford",
            "value_used": "$7,838,000"
          }
        ]
      },
      "suggestion": {
        "shift_months": 0,
        "suggested_window": {
          "start": "2027-06-01",
          "end": "2027-12-15"
        },
        "explanation": "Nearby projects finish before this one could start, so no future shift creates shared construction time. Coordinate on staging yards and permits instead."
      },
      "shared_roads": []
    },
    {
      "project_id": "GPC_20067",
      "short_name": "Deptford–Magnolia",
      "name": "SAV: DEPTFORD - MAGNOLIA 115KV RECONDUCTOR",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "center_distance_mi": 18.08,
      "closest_distance_km": 25.18,
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "score": 9.6,
      "score_breakdown": {
        "proximity": 9.6,
        "savings": 0.0,
        "timing": 0.0
      },
      "potential": "lower",
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 6333000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Deptford–Magnolia",
            "value_used": "$6,333,000"
          }
        ]
      },
      "suggestion": {
        "shift_months": 0,
        "suggested_window": {
          "start": "2027-06-01",
          "end": "2027-12-15"
        },
        "explanation": "Nearby projects finish before this one could start, so no future shift creates shared construction time. Coordinate on staging yards and permits instead."
      },
      "shared_roads": []
    },
    {
      "project_id": "GPC_20784",
      "short_name": "Coleman–Meldrim",
      "name": "SAV: COLEMAN - MELDRIM 115KV LINE REBUILD",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "center_distance_mi": 18.98,
      "closest_distance_km": 25.27,
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "score": 9.6,
      "score_breakdown": {
        "proximity": 9.6,
        "savings": 0.0,
        "timing": 0.0
      },
      "potential": "lower",
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 5239000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Coleman–Meldrim",
            "value_used": "$5,239,000"
          }
        ]
      },
      "suggestion": {
        "shift_months": 0,
        "suggested_window": {
          "start": "2027-06-01",
          "end": "2027-12-15"
        },
        "explanation": "Nearby projects finish before this one could start, so no future shift creates shared construction time. Coordinate on staging yards and permits instead."
      },
      "shared_roads": []
    },
    {
      "project_id": "DESC_6",
      "short_name": "Burton–St Helena",
      "name": "Burton-St Helena 115kV: Rebuild Burton-Frogmore Transmission Section",
      "utility": "DESC",
      "utility_name": "Dominion Energy South Carolina",
      "center_distance_mi": 18.33,
      "closest_distance_km": 25.57,
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "score": 9.5,
      "score_breakdown": {
        "proximity": 9.5,
        "savings": 0.0,
        "timing": 0.0
      },
      "potential": "lower",
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 8580000,
        "reference_budget_source": "filing",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "Dominion Energy SC filing (budget): Burton–St Helena",
            "value_used": "$8,580,000"
          }
        ]
      },
      "suggestion": {
        "shift_months": 0,
        "suggested_window": {
          "start": "2027-06-01",
          "end": "2027-12-15"
        },
        "explanation": "Nearby projects finish before this one could start, so no future shift creates shared construction time. Coordinate on staging yards and permits instead."
      },
      "shared_roads": []
    },
    {
      "project_id": "DESC_7",
      "short_name": "Burton–St Helena",
      "name": "Burton-St Helena 115kV: Frogmore Distribution - St Helena",
      "utility": "DESC",
      "utility_name": "Dominion Energy South Carolina",
      "center_distance_mi": 18.33,
      "closest_distance_km": 25.57,
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "score": 9.5,
      "score_breakdown": {
        "proximity": 9.5,
        "savings": 0.0,
        "timing": 0.0
      },
      "potential": "lower",
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 6925000,
        "reference_budget_source": "filing",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "Dominion Energy SC filing (budget): Burton–St Helena",
            "value_used": "$6,925,000"
          }
        ]
      },
      "suggestion": {
        "shift_months": 0,
        "suggested_window": {
          "start": "2027-06-01",
          "end": "2027-12-15"
        },
        "explanation": "Nearby projects finish before this one could start, so no future shift creates shared construction time. Coordinate on staging yards and permits instead."
      },
      "shared_roads": []
    },
    {
      "project_id": "GPC_20796",
      "short_name": "Meldrim",
      "name": "SAV: MELDRIM BANK D REPLACEMENT",
      "utility": "GPC",
      "utility_name": "Georgia Power",
      "center_distance_mi": 24.28,
      "closest_distance_km": 32.37,
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "score": 8.3,
      "score_breakdown": {
        "proximity": 8.3,
        "savings": 0.0,
        "timing": 0.0
      },
      "potential": "lower",
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 9850000,
        "reference_budget_source": "contract",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "Uploaded contract (budget): Hardeeville Area Reliability Project - …",
            "value_used": "$9,850,000"
          }
        ]
      },
      "suggestion": {
        "shift_months": 0,
        "suggested_window": {
          "start": "2027-06-01",
          "end": "2027-12-15"
        },
        "explanation": "Nearby projects finish before this one could start, so no future shift creates shared construction time. Coordinate on staging yards and permits instead."
      },
      "shared_roads": []
    }
  ],
  "best_match": "USR_H010FE",
  "traffic": {
    "crossings": [
      {
        "id": "XING_CTR_TJYZLK_1",
        "project_id": "CTR_TJYZLK",
        "road_name": "Deerfield Road",
        "road_ref": "US-321",
        "road_refs": [
          "US-321"
        ],
        "road_class": "primary",
        "lanes": 2,
        "lanes_assumed": false,
        "oneway": false,
        "aadt": 4400,
        "aadt_source": "SCDOT 2025 statewide traffic counts (US-321, station 1.6 km away)",
        "osm_id": 358992417,
        "point": {
          "lat": 32.346021,
          "lon": -81.092423
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "flagging",
        "closure_hours": 8,
        "recommended_window": "00:00–08:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 832,
        "delay_cost_usd": 0,
        "worst_window": "00:00–08:00",
        "worst_delay_veh_hours": 0.0
      },
      {
        "id": "XING_CTR_TJYZLK_2",
        "project_id": "CTR_TJYZLK",
        "road_name": "North Whyte Hardee Boulevard",
        "road_ref": "US-17",
        "road_refs": [
          "US-17",
          "US-278"
        ],
        "road_class": "primary",
        "lanes": 2,
        "lanes_assumed": false,
        "oneway": false,
        "aadt": 6300,
        "aadt_source": "SCDOT 2025 statewide traffic counts (US-278, station 2.0 km away)",
        "osm_id": 12428605,
        "point": {
          "lat": 32.329202,
          "lon": -81.056101
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "flagging",
        "closure_hours": 8,
        "recommended_window": "00:00–08:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 1191,
        "delay_cost_usd": 0,
        "worst_window": "00:00–08:00",
        "worst_delay_veh_hours": 0.0
      },
      {
        "id": "XING_CTR_TJYZLK_3",
        "project_id": "CTR_TJYZLK",
        "road_name": null,
        "road_ref": "I-95",
        "road_refs": [
          "I-95"
        ],
        "road_class": "motorway",
        "lanes": 2,
        "lanes_assumed": false,
        "oneway": true,
        "aadt": 65900,
        "aadt_source": "SCDOT 2025 statewide traffic counts (I-95, station 4.8 km away)",
        "osm_id": 156558742,
        "point": {
          "lat": 32.328111,
          "lon": -81.053746
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "lane_closure",
        "closure_hours": 8,
        "recommended_window": "20:00–04:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 4676,
        "delay_cost_usd": 0,
        "worst_window": "13:00–21:00",
        "worst_delay_veh_hours": 25582.5
      },
      {
        "id": "XING_CTR_TJYZLK_4",
        "project_id": "CTR_TJYZLK",
        "road_name": "Tradition Avenue",
        "road_ref": null,
        "road_refs": [],
        "road_class": "tertiary",
        "lanes": 2,
        "lanes_assumed": true,
        "oneway": false,
        "aadt": 2500,
        "aadt_source": "estimated by road class",
        "osm_id": 111768001,
        "point": {
          "lat": 32.312565,
          "lon": -81.020207
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "flagging",
        "closure_hours": 8,
        "recommended_window": "00:00–08:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 472,
        "delay_cost_usd": 0,
        "worst_window": "00:00–08:00",
        "worst_delay_veh_hours": 0.0
      },
      {
        "id": "XING_CTR_TJYZLK_5",
        "project_id": "CTR_TJYZLK",
        "road_name": "Independence Boulevard",
        "road_ref": "US-278",
        "road_refs": [
          "US-278"
        ],
        "road_class": "trunk",
        "lanes": 2,
        "lanes_assumed": false,
        "oneway": true,
        "aadt": 20000,
        "aadt_source": "estimated by road class",
        "osm_id": 459241516,
        "point": {
          "lat": 32.307111,
          "lon": -81.008449
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "lane_closure",
        "closure_hours": 8,
        "recommended_window": "00:00–08:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 2079,
        "delay_cost_usd": 0,
        "worst_window": "00:00–08:00",
        "worst_delay_veh_hours": 0.0
      },
      {
        "id": "XING_CTR_TJYZLK_6",
        "project_id": "CTR_TJYZLK",
        "road_name": "Okatie Highway",
        "road_ref": "SC-170",
        "road_refs": [
          "SC-170"
        ],
        "road_class": "secondary",
        "lanes": 2,
        "lanes_assumed": true,
        "oneway": false,
        "aadt": 6000,
        "aadt_source": "estimated by road class",
        "osm_id": 1268117705,
        "point": {
          "lat": 32.278305,
          "lon": -80.946403
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "flagging",
        "closure_hours": 8,
        "recommended_window": "00:00–08:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 1134,
        "delay_cost_usd": 0,
        "worst_window": "00:00–08:00",
        "worst_delay_veh_hours": 0.0
      },
      {
        "id": "XING_CTR_TJYZLK_7",
        "project_id": "CTR_TJYZLK",
        "road_name": "Hampton Parkway",
        "road_ref": null,
        "road_refs": [],
        "road_class": "tertiary",
        "lanes": 2,
        "lanes_assumed": true,
        "oneway": false,
        "aadt": 2500,
        "aadt_source": "estimated by road class",
        "osm_id": 71135538,
        "point": {
          "lat": 32.271181,
          "lon": -80.931076
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "flagging",
        "closure_hours": 8,
        "recommended_window": "00:00–08:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 472,
        "delay_cost_usd": 0,
        "worst_window": "00:00–08:00",
        "worst_delay_veh_hours": 0.0
      },
      {
        "id": "XING_CTR_TJYZLK_8",
        "project_id": "CTR_TJYZLK",
        "road_name": "Bluffton Parkway",
        "road_ref": null,
        "road_refs": [],
        "road_class": "tertiary",
        "lanes": 2,
        "lanes_assumed": true,
        "oneway": false,
        "aadt": 2500,
        "aadt_source": "estimated by road class",
        "osm_id": 260415726,
        "point": {
          "lat": 32.267682,
          "lon": -80.923548
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "flagging",
        "closure_hours": 8,
        "recommended_window": "00:00–08:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 472,
        "delay_cost_usd": 0,
        "worst_window": "00:00–08:00",
        "worst_delay_veh_hours": 0.0
      },
      {
        "id": "XING_CTR_TJYZLK_9",
        "project_id": "CTR_TJYZLK",
        "road_name": "Buckwalter Parkway",
        "road_ref": null,
        "road_refs": [],
        "road_class": "tertiary",
        "lanes": 2,
        "lanes_assumed": true,
        "oneway": false,
        "aadt": 26400,
        "aadt_source": "SCDOT 2025 statewide traffic counts (station 118 m away)",
        "osm_id": 42207742,
        "point": {
          "lat": 32.258505,
          "lon": -80.903816
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "flagging",
        "closure_hours": 8,
        "recommended_window": "20:00–04:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 3406,
        "delay_cost_usd": 0,
        "worst_window": "13:00–21:00",
        "worst_delay_veh_hours": 24879.2
      },
      {
        "id": "XING_CTR_TJYZLK_10",
        "project_id": "CTR_TJYZLK",
        "road_name": "Bluffton Parkway",
        "road_ref": null,
        "road_refs": [],
        "road_class": "tertiary",
        "lanes": 2,
        "lanes_assumed": false,
        "oneway": true,
        "aadt": 2500,
        "aadt_source": "estimated by road class",
        "osm_id": 189259580,
        "point": {
          "lat": 32.257781,
          "lon": -80.902261
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "lane_closure",
        "closure_hours": 8,
        "recommended_window": "00:00–08:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 260,
        "delay_cost_usd": 0,
        "worst_window": "00:00–08:00",
        "worst_delay_veh_hours": 0.0
      },
      {
        "id": "XING_CTR_TJYZLK_11",
        "project_id": "CTR_TJYZLK",
        "road_name": "Buck Island Road",
        "road_ref": null,
        "road_refs": [],
        "road_class": "tertiary",
        "lanes": 2,
        "lanes_assumed": true,
        "oneway": false,
        "aadt": 2500,
        "aadt_source": "estimated by road class",
        "osm_id": 12130469,
        "point": {
          "lat": 32.248161,
          "lon": -80.881589
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "flagging",
        "closure_hours": 8,
        "recommended_window": "00:00–08:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 472,
        "delay_cost_usd": 0,
        "worst_window": "00:00–08:00",
        "worst_delay_veh_hours": 0.0
      },
      {
        "id": "XING_CTR_TJYZLK_12",
        "project_id": "CTR_TJYZLK",
        "road_name": "Simmonsville Road",
        "road_ref": null,
        "road_refs": [],
        "road_class": "tertiary",
        "lanes": 2,
        "lanes_assumed": true,
        "oneway": false,
        "aadt": 2500,
        "aadt_source": "estimated by road class",
        "osm_id": 765908496,
        "point": {
          "lat": 32.246133,
          "lon": -80.877233
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "flagging",
        "closure_hours": 8,
        "recommended_window": "00:00–08:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 472,
        "delay_cost_usd": 0,
        "worst_window": "00:00–08:00",
        "worst_delay_veh_hours": 0.0
      },
      {
        "id": "XING_CTR_TJYZLK_13",
        "project_id": "CTR_TJYZLK",
        "road_name": "Bluffton Road",
        "road_ref": "SC-46",
        "road_refs": [
          "SC-46"
        ],
        "road_class": "secondary",
        "lanes": 2,
        "lanes_assumed": false,
        "oneway": false,
        "aadt": 17700,
        "aadt_source": "SCDOT 2025 statewide traffic counts (SC-46, station 1.2 km away)",
        "osm_id": 12128039,
        "point": {
          "lat": 32.238248,
          "lon": -80.860299
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "flagging",
        "closure_hours": 8,
        "recommended_window": "19:00–03:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 2974,
        "delay_cost_usd": 0,
        "worst_window": "14:00–22:00",
        "worst_delay_veh_hours": 4125.9
      },
      {
        "id": "XING_CTR_TJYZLK_14",
        "project_id": "CTR_TJYZLK",
        "road_name": "Bruin Road",
        "road_ref": null,
        "road_refs": [],
        "road_class": "tertiary",
        "lanes": 2,
        "lanes_assumed": false,
        "oneway": false,
        "aadt": 7500,
        "aadt_source": "SCDOT 2025 statewide traffic counts (station 209 m away)",
        "osm_id": 12127099,
        "point": {
          "lat": 32.236925,
          "lon": -80.857458
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "flagging",
        "closure_hours": 8,
        "recommended_window": "00:00–08:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 1418,
        "delay_cost_usd": 0,
        "worst_window": "00:00–08:00",
        "worst_delay_veh_hours": 0.0
      },
      {
        "id": "XING_CTR_TJYZLK_15",
        "project_id": "CTR_TJYZLK",
        "road_name": "Burnt Church Road",
        "road_ref": null,
        "road_refs": [],
        "road_class": "tertiary",
        "lanes": 2,
        "lanes_assumed": false,
        "oneway": false,
        "aadt": 4200,
        "aadt_source": "SCDOT 2025 statewide traffic counts (station 83 m away)",
        "osm_id": 12130728,
        "point": {
          "lat": 32.235225,
          "lon": -80.853808
        },
        "point_approximate": true,
        "est_closure_hours": 8,
        "work_window": {
          "start": "2027-06-01",
          "end": "2027-12-15",
          "source": "contract"
        },
        "owner": "CMP_A",
        "closure_type": "flagging",
        "closure_hours": 8,
        "recommended_window": "00:00–08:00",
        "delay_veh_hours": 0.0,
        "vehicles_affected": 794,
        "delay_cost_usd": 0,
        "worst_window": "00:00–08:00",
        "worst_delay_veh_hours": 0.0
      }
    ],
    "access_roads": [],
    "conflicts": []
  },
  "summary": {
    "matches_count": 17,
    "total_savings_range_usd": [
      98848,
      496874
    ],
    "best_savings_usd": 247473,
    "best_savings_project_id": "USR_H010FE",
    "savings_range_basis": "best single partner (savings from several partners are not added: they mostly share the same mobilization of this contract, which happens once)",
    "high_potential": 0
  }
}
```

Example file: `examples/POST_contracts_match.json`

---

### `POST /contracts/{id}/save`

Saves the reviewed contract as the company's user project (same as `POST /projects`, events emitted). The assistant tool `save_contract_as_project` does this only after confirmation.

Headers: `X-Company-Id: CMP_A`

Response `201`:

```json
{
  "contract_id": "CTR_TJYZLK",
  "project": {
    "id": "USR_TKKP71",
    "utility": "USER",
    "utility_name": "Demo Contractor A",
    "state": null,
    "name": "Hardeeville Area Reliability Project - Jasper to Bluffton 115 kV Line Rebuild",
    "voltage_kv": 115,
    "project_type": "line",
    "status": "Planned",
    "in_service_date": "2027-12-15",
    "construction_window": {
      "start": "2027-06-01",
      "end": "2027-12-15",
      "source": "user"
    },
    "endpoints": [
      {
        "name": "Jasper Substation",
        "lat": 32.360699,
        "lon": -81.124152,
        "confidence": "high",
        "source": "user",
        "county": null
      },
      {
        "name": "Bluffton Substation",
        "lat": 32.235027,
        "lon": -80.853384,
        "confidence": "high",
        "source": "user",
        "county": null
      }
    ],
    "center": {
      "lat": 32.297863,
      "lon": -80.988768
    },
    "geometry": {
      "type": "LineString",
      "coordinates": [
        [
          -81.124152,
          32.360699
        ],
        [
          -80.853384,
          32.235027
        ]
      ]
    },
    "location_confidence": "high",
    "description": "Transmission line rebuild",
    "cost": null,
    "source": {
      "document": null,
      "page": null,
      "type": "user"
    },
    "quality_flags": [],
    "overlap_ids": [
      "OVL_USR_TKKP71__DESC_3",
      "OVL_USR_TKKP71__DESC_6",
      "OVL_USR_TKKP71__DESC_7",
      "OVL_USR_TKKP71__DESC_10",
      "OVL_USR_TKKP71__DESC_23",
      "OVL_USR_TKKP71__GPC_20067",
      "OVL_USR_TKKP71__GPC_20066",
      "OVL_USR_TKKP71__GPC_20277",
      "OVL_USR_TKKP71__GPC_20785",
      "OVL_USR_TKKP71__GPC_20065",
      "OVL_USR_TKKP71__GPC_20783",
      "OVL_USR_TKKP71__GPC_20407",
      "OVL_USR_TKKP71__GPC_21006",
      "OVL_USR_TKKP71__GPC_21023",
      "OVL_USR_TKKP71__GPC_20784",
      "OVL_USR_TKKP71__GPC_20796",
      "OVL_USR_TKKP71__USR_H010FE"
    ],
    "short_name": "Hardeeville Area Reliability Project - …",
    "work_type_label": "Transmission line rebuild",
    "counties": [],
    "county_source": null,
    "company_id": "CMP_A",
    "work_type": "Transmission line rebuild",
    "roads_affected": [
      "US-17",
      "I-95"
    ],
    "lane_closures": "Nighttime northbound lane closure on US-17 near Hardeeville",
    "work_hours": "21:00-05:00",
    "planning_authority": null,
    "location_text": null,
    "geocoded": null,
    "contract_text_hash": "2d93bbbbfa1b6cfc5f26657dce78de245db5059ea9435ab9d5868bf372d85ca6",
    "line_miles": 17.5,
    "budget_usd": 9850000,
    "budget_source": "contract",
    "budget_note": "Stated in the uploaded contract",
    "created_at": "2026-09-27T00:11:02.755887+00:00",
    "updated_at": "2026-09-27T00:11:02.755887+00:00"
  },
  "overlaps": [
    {
      "id": "OVL_USR_TKKP71__DESC_3",
      "project_a": "USR_TKKP71",
      "project_b": "DESC_3",
      "center_distance_mi": 3.56,
      "closest_distance_km": 1.51,
      "closest_points": {
        "a": {
          "lat": 32.32182,
          "lon": -81.04017
        },
        "b": {
          "lat": 32.333758,
          "lon": -81.032495
        }
      },
      "tier": "shared_land",
      "tier_explanation": "Under 1.6 km: can share right-of-way, access roads, permits",
      "shared_endpoint": false,
      "time_gap_days": 1079,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "predicted",
      "score": 33.4,
      "score_breakdown": {
        "proximity": 33.4,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 9,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 9850000,
        "reference_budget_source": "contract",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "Uploaded contract (budget): Hardeeville Area Reliability Project - …",
            "value_used": "$9,850,000"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Okatie",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 246200,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2022-12-31"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 1,
          "start_date_a": "2027-06-01",
          "start_date_b": "2022-12-31"
        },
        "totals": {
          "separate": 532400,
          "coordinated": 527400,
          "savings": 5000,
          "savings_pct": 0.9,
          "separate_by_project": {
            "a": 266200,
            "b": 266200
          },
          "coordinated_by_project": {
            "a": 263700,
            "b": 263700
          }
        },
        "range": {
          "separate": [
            452540,
            612260
          ],
          "coordinated": [
            448290,
            606510
          ],
          "savings": [
            3750,
            6250
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__DESC_6",
      "project_a": "USR_TKKP71",
      "project_b": "DESC_6",
      "center_distance_mi": 18.33,
      "closest_distance_km": 25.57,
      "closest_points": {
        "a": {
          "lat": 32.235027,
          "lon": -80.853384
        },
        "b": {
          "lat": 32.436488,
          "lon": -80.721016
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 1079,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "predicted",
      "score": 9.5,
      "score_breakdown": {
        "proximity": 9.5,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 19,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 8580000,
        "reference_budget_source": "filing",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "Dominion Energy SC filing (budget): Burton–St Helena",
            "value_used": "$8,580,000"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Burton–St Helena",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 214500,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2022-09-30"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2022-09-30"
        },
        "totals": {
          "separate": 469000,
          "coordinated": 469000,
          "savings": 0,
          "savings_pct": 0.0,
          "separate_by_project": {
            "a": 234500,
            "b": 234500
          },
          "coordinated_by_project": {
            "a": 234500,
            "b": 234500
          }
        },
        "range": {
          "separate": [
            398650,
            539350
          ],
          "coordinated": [
            398650,
            539350
          ],
          "savings": [
            0,
            0
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__DESC_7",
      "project_a": "USR_TKKP71",
      "project_b": "DESC_7",
      "center_distance_mi": 18.33,
      "closest_distance_km": 25.57,
      "closest_points": {
        "a": {
          "lat": 32.235027,
          "lon": -80.853384
        },
        "b": {
          "lat": 32.436488,
          "lon": -80.721016
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 714,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "predicted",
      "score": 9.5,
      "score_breakdown": {
        "proximity": 9.5,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 20,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 6925000,
        "reference_budget_source": "filing",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "Dominion Energy SC filing (budget): Burton–St Helena",
            "value_used": "$6,925,000"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Burton–St Helena",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 173100,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2023-10-31"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2023-10-31"
        },
        "totals": {
          "separate": 386200,
          "coordinated": 386200,
          "savings": 0,
          "savings_pct": 0.0,
          "separate_by_project": {
            "a": 193100,
            "b": 193100
          },
          "coordinated_by_project": {
            "a": 193100,
            "b": 193100
          }
        },
        "range": {
          "separate": [
            328270,
            444130
          ],
          "coordinated": [
            328270,
            444130
          ],
          "savings": [
            0,
            0
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__DESC_10",
      "project_a": "USR_TKKP71",
      "project_b": "DESC_10",
      "center_distance_mi": 2.83,
      "closest_distance_km": 0.0,
      "closest_points": {
        "a": {
          "lat": 32.235027,
          "lon": -80.853384
        },
        "b": {
          "lat": 32.235027,
          "lon": -80.853384
        }
      },
      "tier": "crossing",
      "tier_explanation": "Touching/crossing: must coordinate outages and crossing structures",
      "shared_endpoint": true,
      "time_gap_days": 927,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "predicted",
      "score": 40.0,
      "score_breakdown": {
        "proximity": 40.0,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 3,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap",
            "acres": 139.5
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 9850000,
        "reference_budget_source": "contract",
        "shared_row_acres": 139.5,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "Uploaded contract (budget): Hardeeville Area Reliability Project - …",
            "value_used": "$9,850,000"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Okatie–Bluffton",
      "potential": "moderate",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 246200,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2023-03-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 1,
          "start_date_a": "2027-06-01",
          "start_date_b": "2023-03-01"
        },
        "totals": {
          "separate": 532400,
          "coordinated": 527400,
          "savings": 5000,
          "savings_pct": 0.9,
          "separate_by_project": {
            "a": 266200,
            "b": 266200
          },
          "coordinated_by_project": {
            "a": 263700,
            "b": 263700
          }
        },
        "range": {
          "separate": [
            452540,
            612260
          ],
          "coordinated": [
            448290,
            606510
          ],
          "savings": [
            3750,
            6250
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__DESC_23",
      "project_a": "USR_TKKP71",
      "project_b": "DESC_23",
      "center_distance_mi": 6.24,
      "closest_distance_km": 0.0,
      "closest_points": {
        "a": {
          "lat": 32.360699,
          "lon": -81.124152
        },
        "b": {
          "lat": 32.360699,
          "lon": -81.124152
        }
      },
      "tier": "crossing",
      "tier_explanation": "Touching/crossing: must coordinate outages and crossing structures",
      "shared_endpoint": true,
      "time_gap_days": 714,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "predicted",
      "score": 40.0,
      "score_breakdown": {
        "proximity": 40.0,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 4,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap",
            "acres": 89.8
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 9850000,
        "reference_budget_source": "contract",
        "shared_row_acres": 89.8,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "Uploaded contract (budget): Hardeeville Area Reliability Project - …",
            "value_used": "$9,850,000"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Jasper–Okatie",
      "potential": "moderate",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 246200,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2023-08-31"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 1,
          "start_date_a": "2027-06-01",
          "start_date_b": "2023-08-31"
        },
        "totals": {
          "separate": 532400,
          "coordinated": 527400,
          "savings": 5000,
          "savings_pct": 0.9,
          "separate_by_project": {
            "a": 266200,
            "b": 266200
          },
          "coordinated_by_project": {
            "a": 263700,
            "b": 263700
          }
        },
        "range": {
          "separate": [
            452540,
            612260
          ],
          "coordinated": [
            448290,
            606510
          ],
          "savings": [
            3750,
            6250
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__GPC_20067",
      "project_a": "USR_TKKP71",
      "project_b": "GPC_20067",
      "center_distance_mi": 18.08,
      "closest_distance_km": 25.18,
      "closest_points": {
        "a": {
          "lat": 32.266173,
          "lon": -80.920304
        },
        "b": {
          "lat": 32.066828,
          "lon": -81.048384
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 927,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 9.6,
      "score_breakdown": {
        "proximity": 9.6,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 17,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 6333000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Deptford–Magnolia",
            "value_used": "$6,333,000"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Deptford–Magnolia",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 158300,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1260
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2023-01-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2023-01-01"
        },
        "totals": {
          "separate": 356600,
          "coordinated": 356600,
          "savings": 0,
          "savings_pct": 0.0,
          "separate_by_project": {
            "a": 178300,
            "b": 178300
          },
          "coordinated_by_project": {
            "a": 178300,
            "b": 178300
          }
        },
        "range": {
          "separate": [
            303110,
            410090
          ],
          "coordinated": [
            303110,
            410090
          ],
          "savings": [
            0,
            0
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__GPC_20066",
      "project_a": "USR_TKKP71",
      "project_b": "GPC_20066",
      "center_distance_mi": 17.99,
      "closest_distance_km": 25.18,
      "closest_points": {
        "a": {
          "lat": 32.266173,
          "lon": -80.920304
        },
        "b": {
          "lat": 32.066828,
          "lon": -81.048384
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 562,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 9.6,
      "score_breakdown": {
        "proximity": 9.6,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 16,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 7838000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Boulevard–Deptford",
            "value_used": "$7,838,000"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Boulevard–Deptford",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 196000,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1260
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2025-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2025-06-01"
        },
        "totals": {
          "separate": 432000,
          "coordinated": 432000,
          "savings": 0,
          "savings_pct": 0.0,
          "separate_by_project": {
            "a": 216000,
            "b": 216000
          },
          "coordinated_by_project": {
            "a": 216000,
            "b": 216000
          }
        },
        "range": {
          "separate": [
            367200,
            496800
          ],
          "coordinated": [
            367200,
            496800
          ],
          "savings": [
            0,
            0
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__GPC_20277",
      "project_a": "USR_TKKP71",
      "project_b": "GPC_20277",
      "center_distance_mi": 11.51,
      "closest_distance_km": 4.89,
      "closest_points": {
        "a": {
          "lat": 32.360699,
          "lon": -81.124152
        },
        "b": {
          "lat": 32.352116,
          "lon": -81.175112
        }
      },
      "tier": "shared_site",
      "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
      "shared_endpoint": false,
      "time_gap_days": 562,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 24.4,
      "score_breakdown": {
        "proximity": 24.4,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 11,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 5034000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): McIntosh–Purrysburg",
            "value_used": "$5,034,000"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ McIntosh–Purrysburg",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 125800,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1260
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2024-01-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 1,
          "start_date_a": "2027-06-01",
          "start_date_b": "2024-01-01"
        },
        "totals": {
          "separate": 291600,
          "coordinated": 286600,
          "savings": 5000,
          "savings_pct": 1.7,
          "separate_by_project": {
            "a": 145800,
            "b": 145800
          },
          "coordinated_by_project": {
            "a": 143300,
            "b": 143300
          }
        },
        "range": {
          "separate": [
            247860,
            335340
          ],
          "coordinated": [
            243610,
            329590
          ],
          "savings": [
            3750,
            6250
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__GPC_20785",
      "project_a": "USR_TKKP71",
      "project_b": "GPC_20785",
      "center_distance_mi": 13.01,
      "closest_distance_km": 14.79,
      "closest_points": {
        "a": {
          "lat": 32.360699,
          "lon": -81.124152
        },
        "b": {
          "lat": 32.248701,
          "lon": -81.209472
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 197,
      "window_overlap_months": 0,
      "schedule_shift_possible": true,
      "timing_confidence": "filed",
      "score": 27.5,
      "score_breakdown": {
        "proximity": 11.4,
        "savings": 10.1,
        "timing": 6.0
      },
      "rank": 10,
      "cost_estimate": {
        "total_estimated_savings_usd": 108676,
        "range_usd": [
          29545,
          319968
        ],
        "components": {
          "mobilization": {
            "low": 29370,
            "point": 107712,
            "high": 316025,
            "applies": true,
            "requires_schedule_shift": true
          },
          "logistics": {
            "low": 175,
            "point": 964,
            "high": 3943,
            "applies": true,
            "site_to_site_road_miles": 15.6
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 8617000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": 107712,
        "assumptions": [
          "The reference budget is an ML prediction (likely $5,874,000–$12,641,000); the savings range uses that budget range",
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Mobilization savings halved: the construction windows only overlap after a schedule shift",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Goshen–Kraft",
            "value_used": "$8,617,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Goshen–Kraft",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 215400,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1260
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2024-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2024-06-01"
        },
        "totals": {
          "separate": 470800,
          "coordinated": 470800,
          "savings": 0,
          "savings_pct": 0.0,
          "separate_by_project": {
            "a": 235400,
            "b": 235400
          },
          "coordinated_by_project": {
            "a": 235400,
            "b": 235400
          }
        },
        "range": {
          "separate": [
            400180,
            541420
          ],
          "coordinated": [
            400180,
            541420
          ],
          "savings": [
            0,
            0
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__GPC_20065",
      "project_a": "USR_TKKP71",
      "project_b": "GPC_20065",
      "center_distance_mi": 11.89,
      "closest_distance_km": 4.89,
      "closest_points": {
        "a": {
          "lat": 32.360699,
          "lon": -81.124152
        },
        "b": {
          "lat": 32.352116,
          "lon": -81.175112
        }
      },
      "tier": "shared_site",
      "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
      "shared_endpoint": false,
      "time_gap_days": 197,
      "window_overlap_months": 0,
      "schedule_shift_possible": true,
      "timing_confidence": "filed",
      "score": 40.5,
      "score_breakdown": {
        "proximity": 24.4,
        "savings": 10.1,
        "timing": 6.0
      },
      "rank": 2,
      "cost_estimate": {
        "total_estimated_savings_usd": 93427,
        "range_usd": [
          25401,
          275180
        ],
        "components": {
          "mobilization": {
            "low": 25200,
            "point": 92425,
            "high": 271175,
            "applies": true,
            "requires_schedule_shift": true
          },
          "logistics": {
            "low": 201,
            "point": 1002,
            "high": 4005,
            "applies": true,
            "site_to_site_road_miles": 14.3
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 7394000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": 92425,
        "assumptions": [
          "The reference budget is an ML prediction (likely $5,040,000–$10,847,000); the savings range uses that budget range",
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Mobilization savings halved: the construction windows only overlap after a schedule shift",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Goshen–McIntosh",
            "value_used": "$7,394,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Goshen–McIntosh",
      "potential": "moderate",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 184800,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1260
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2025-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 1,
          "start_date_a": "2027-06-01",
          "start_date_b": "2025-06-01"
        },
        "totals": {
          "separate": 409600,
          "coordinated": 404600,
          "savings": 5000,
          "savings_pct": 1.2,
          "separate_by_project": {
            "a": 204800,
            "b": 204800
          },
          "coordinated_by_project": {
            "a": 202300,
            "b": 202300
          }
        },
        "range": {
          "separate": [
            348160,
            471040
          ],
          "coordinated": [
            343910,
            465290
          ],
          "savings": [
            3750,
            6250
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__GPC_20783",
      "project_a": "USR_TKKP71",
      "project_b": "GPC_20783",
      "center_distance_mi": 17.23,
      "closest_distance_km": 25.27,
      "closest_points": {
        "a": {
          "lat": 32.297455,
          "lon": -80.987638
        },
        "b": {
          "lat": 32.09732,
          "lon": -81.116077
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 169,
      "window_overlap_months": 6,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 39.7,
      "score_breakdown": {
        "proximity": 9.6,
        "savings": 20.1,
        "timing": 10.0
      },
      "rank": 5,
      "cost_estimate": {
        "total_estimated_savings_usd": 185297,
        "range_usd": [
          50381,
          544956
        ],
        "components": {
          "mobilization": {
            "low": 50300,
            "point": 184475,
            "high": 541250,
            "applies": true,
            "requires_schedule_shift": false
          },
          "logistics": {
            "low": 81,
            "point": 822,
            "high": 3706,
            "applies": true,
            "site_to_site_road_miles": 20.7
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 7379000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": 184475,
        "assumptions": [
          "The reference budget is an ML prediction (likely $5,030,000–$10,825,000); the savings range uses that budget range",
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Coleman–Dean Forest",
            "value_used": "$7,379,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Coleman–Dean Forest",
      "potential": "moderate",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 184500,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1260
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2025-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 12,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2025-06-01"
        },
        "totals": {
          "separate": 409000,
          "coordinated": 397000,
          "savings": 12000,
          "savings_pct": 2.9,
          "separate_by_project": {
            "a": 204500,
            "b": 204500
          },
          "coordinated_by_project": {
            "a": 198500,
            "b": 198500
          }
        },
        "range": {
          "separate": [
            347650,
            470350
          ],
          "coordinated": [
            337450,
            456550
          ],
          "savings": [
            9000,
            15000
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (yes for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__GPC_20407",
      "project_a": "USR_TKKP71",
      "project_b": "GPC_20407",
      "center_distance_mi": 19.85,
      "closest_distance_km": 31.19,
      "closest_points": {
        "a": {
          "lat": 32.269593,
          "lon": -80.927658
        },
        "b": {
          "lat": 32.022687,
          "lon": -81.086181
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 169,
      "window_overlap_months": 6,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 38.6,
      "score_breakdown": {
        "proximity": 8.5,
        "savings": 20.1,
        "timing": 10.0
      },
      "rank": 8,
      "cost_estimate": {
        "total_estimated_savings_usd": 131709,
        "range_usd": [
          35732,
          387859
        ],
        "components": {
          "mobilization": {
            "low": 35710,
            "point": 130975,
            "high": 384300,
            "applies": true,
            "requires_schedule_shift": false
          },
          "logistics": {
            "low": 22,
            "point": 734,
            "high": 3559,
            "applies": true,
            "site_to_site_road_miles": 23.8
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 5239000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": 130975,
        "assumptions": [
          "The reference budget is an ML prediction (likely $3,571,000–$7,686,000); the savings range uses that budget range",
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Magnolia–Truman Parkway",
            "value_used": "$5,239,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Magnolia–Truman Parkway",
      "potential": "moderate",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 131000,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1260
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2025-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 12,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2025-06-01"
        },
        "totals": {
          "separate": 302000,
          "coordinated": 290000,
          "savings": 12000,
          "savings_pct": 4.0,
          "separate_by_project": {
            "a": 151000,
            "b": 151000
          },
          "coordinated_by_project": {
            "a": 145000,
            "b": 145000
          }
        },
        "range": {
          "separate": [
            256700,
            347300
          ],
          "coordinated": [
            246500,
            333500
          ],
          "savings": [
            9000,
            15000
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (yes for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__GPC_21006",
      "project_a": "USR_TKKP71",
      "project_b": "GPC_21006",
      "center_distance_mi": 19.81,
      "closest_distance_km": 31.19,
      "closest_points": {
        "a": {
          "lat": 32.269593,
          "lon": -80.927658
        },
        "b": {
          "lat": 32.022687,
          "lon": -81.086181
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 534,
      "window_overlap_months": 6,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 38.6,
      "score_breakdown": {
        "proximity": 8.5,
        "savings": 20.1,
        "timing": 10.0
      },
      "rank": 7,
      "cost_estimate": {
        "total_estimated_savings_usd": 156485,
        "range_usd": [
          42493,
          460561
        ],
        "components": {
          "mobilization": {
            "low": 42470,
            "point": 155750,
            "high": 457000,
            "applies": true,
            "requires_schedule_shift": false
          },
          "logistics": {
            "low": 23,
            "point": 735,
            "high": 3561,
            "applies": true,
            "site_to_site_road_miles": 23.8
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 6230000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": 155750,
        "assumptions": [
          "The reference budget is an ML prediction (likely $4,247,000–$9,140,000); the savings range uses that budget range",
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Boulevard–Magnolia",
            "value_used": "$6,230,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Boulevard–Magnolia",
      "potential": "moderate",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 155800,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1260
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-01-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 12,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2027-01-01"
        },
        "totals": {
          "separate": 351600,
          "coordinated": 339600,
          "savings": 12000,
          "savings_pct": 3.4,
          "separate_by_project": {
            "a": 175800,
            "b": 175800
          },
          "coordinated_by_project": {
            "a": 169800,
            "b": 169800
          }
        },
        "range": {
          "separate": [
            298860,
            404340
          ],
          "coordinated": [
            288660,
            390540
          ],
          "savings": [
            9000,
            15000
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (yes for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__GPC_21023",
      "project_a": "USR_TKKP71",
      "project_b": "GPC_21023",
      "center_distance_mi": 22.12,
      "closest_distance_km": 29.89,
      "closest_points": {
        "a": {
          "lat": 32.320323,
          "lon": -81.036941
        },
        "b": {
          "lat": 32.08351,
          "lon": -81.188722
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 534,
      "window_overlap_months": 6,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 38.9,
      "score_breakdown": {
        "proximity": 8.8,
        "savings": 20.1,
        "timing": 10.0
      },
      "rank": 6,
      "cost_estimate": {
        "total_estimated_savings_usd": 246908,
        "range_usd": [
          98471,
          495932
        ],
        "components": {
          "mobilization": {
            "low": 98500,
            "point": 246250,
            "high": 492500,
            "applies": true,
            "requires_schedule_shift": false
          },
          "logistics": {
            "low": -29,
            "point": 658,
            "high": 3432,
            "applies": true,
            "site_to_site_road_miles": 26.5
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 9850000,
        "reference_budget_source": "contract",
        "shared_row_acres": null,
        "mobilization_savings_usd": 246250,
        "assumptions": [
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "Uploaded contract (budget): Hardeeville Area Reliability Project - …",
            "value_used": "$9,850,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Dean Forest–Little Ogeechee",
      "potential": "moderate",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 246200,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1260
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2026-01-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 12,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2026-01-01"
        },
        "totals": {
          "separate": 532400,
          "coordinated": 520400,
          "savings": 12000,
          "savings_pct": 2.3,
          "separate_by_project": {
            "a": 266200,
            "b": 266200
          },
          "coordinated_by_project": {
            "a": 260200,
            "b": 260200
          }
        },
        "range": {
          "separate": [
            452540,
            612260
          ],
          "coordinated": [
            442340,
            598460
          ],
          "savings": [
            9000,
            15000
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (yes for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__GPC_20784",
      "project_a": "USR_TKKP71",
      "project_b": "GPC_20784",
      "center_distance_mi": 18.98,
      "closest_distance_km": 25.27,
      "closest_points": {
        "a": {
          "lat": 32.297455,
          "lon": -80.987638
        },
        "b": {
          "lat": 32.09732,
          "lon": -81.116077
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 1630,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 9.6,
      "score_breakdown": {
        "proximity": 9.6,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 18,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 5239000,
        "reference_budget_source": "predicted (ridge, Dominion budgets)",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "ML cost model trained on 44 Dominion filed budgets (budget predicted): Coleman–Meldrim",
            "value_used": "$5,239,000"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Coleman–Meldrim",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 131000,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1260
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2029-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2029-06-01"
        },
        "totals": {
          "separate": 302000,
          "coordinated": 302000,
          "savings": 0,
          "savings_pct": 0.0,
          "separate_by_project": {
            "a": 151000,
            "b": 151000
          },
          "coordinated_by_project": {
            "a": 151000,
            "b": 151000
          }
        },
        "range": {
          "separate": [
            256700,
            347300
          ],
          "coordinated": [
            256700,
            347300
          ],
          "savings": [
            0,
            0
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__GPC_20796",
      "project_a": "USR_TKKP71",
      "project_b": "GPC_20796",
      "center_distance_mi": 24.28,
      "closest_distance_km": 32.37,
      "closest_points": {
        "a": {
          "lat": 32.360699,
          "lon": -81.124152
        },
        "b": {
          "lat": 32.155282,
          "lon": -81.368377
        }
      },
      "tier": "shared_crews",
      "tier_explanation": "Under 40 km: can share crews and equipment",
      "shared_endpoint": false,
      "time_gap_days": 1995,
      "window_overlap_months": 0,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 8.3,
      "score_breakdown": {
        "proximity": 8.3,
        "savings": 0.0,
        "timing": 0.0
      },
      "rank": 21,
      "cost_estimate": {
        "total_estimated_savings_usd": 0,
        "range_usd": [
          0,
          0
        ],
        "components": {
          "mobilization": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap within 12 months"
          },
          "logistics": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false,
            "reason": "construction windows cannot overlap"
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 9850000,
        "reference_budget_source": "contract",
        "shared_row_acres": null,
        "mobilization_savings_usd": null,
        "assumptions": [],
        "sources": [
          {
            "name": "Uploaded contract (budget): Hardeeville Area Reliability Project - …",
            "value_used": "$9,850,000"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Meldrim",
      "potential": "lower",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 246200,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1260
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2030-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 20,
          "laydown_sites": 2,
          "start_date_a": "2027-06-01",
          "start_date_b": "2030-06-01"
        },
        "totals": {
          "separate": 532400,
          "coordinated": 532400,
          "savings": 0,
          "savings_pct": 0.0,
          "separate_by_project": {
            "a": 266200,
            "b": 266200
          },
          "coordinated_by_project": {
            "a": 266200,
            "b": 266200
          }
        },
        "range": {
          "separate": [
            452540,
            612260
          ],
          "coordinated": [
            452540,
            612260
          ],
          "savings": [
            0,
            0
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (no for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (no for this pair)."
        ]
      },
      "kind": "user_project"
    },
    {
      "id": "OVL_USR_TKKP71__USR_H010FE",
      "project_a": "USR_TKKP71",
      "project_b": "USR_H010FE",
      "center_distance_mi": 5.32,
      "closest_distance_km": 5.13,
      "closest_points": {
        "a": {
          "lat": 32.327722,
          "lon": -81.052907
        },
        "b": {
          "lat": 32.2871,
          "lon": -81.079
        }
      },
      "tier": "shared_site",
      "tier_explanation": "Under 8 km: can share laydown yards and deliveries",
      "shared_endpoint": false,
      "time_gap_days": 48,
      "window_overlap_months": 6,
      "schedule_shift_possible": false,
      "timing_confidence": "filed",
      "score": 54.4,
      "score_breakdown": {
        "proximity": 24.3,
        "savings": 20.1,
        "timing": 10.0
      },
      "rank": 1,
      "cost_estimate": {
        "total_estimated_savings_usd": 247473,
        "range_usd": [
          98848,
          496874
        ],
        "components": {
          "mobilization": {
            "low": 98500,
            "point": 246250,
            "high": 492500,
            "applies": true,
            "requires_schedule_shift": false
          },
          "logistics": {
            "low": 348,
            "point": 1223,
            "high": 4374,
            "applies": true,
            "site_to_site_road_miles": 6.4
          },
          "shared_land": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          },
          "traffic_delay": {
            "low": 0,
            "point": 0,
            "high": 0,
            "applies": false
          }
        },
        "reference_budget_usd": 9850000,
        "reference_budget_source": "contract",
        "shared_row_acres": null,
        "mobilization_savings_usd": 246250,
        "assumptions": [
          "Share of one mobilization that can be shared: 25%–50% (assumption)",
          "Hauling: 4–10 equipment loads per project, contractor base 25–100 miles from site, road miles = 1.2 x straight-line (assumptions)"
        ],
        "sources": [
          {
            "name": "Uploaded contract (budget): Hardeeville Area Reliability Project - …",
            "value_used": "$9,850,000"
          },
          {
            "name": "MoDOT Engineering Policy Guide, Category 618 Mobilization",
            "value_used": "4%–10% of the budget",
            "url": "https://epg.modot.org/index.php/Category:618_Mobilization"
          },
          {
            "name": "ATRI, An Analysis of the Operational Costs of Trucking, 2025 data (published July 2026)",
            "value_used": "$2.336/mile",
            "url": "https://truckingresearch.org/about-atri/atri-research/operational-costs-of-trucking/"
          }
        ]
      },
      "brief": null,
      "label": "Hardeeville Area Reliability Project - … ↔ Corridor upgrade",
      "potential": "moderate",
      "cost_scenario": {
        "illustrative": true,
        "defaults_source": "cost_sources.json",
        "unit_rates": {
          "mobilization_per_event": 246200,
          "bucket_truck_per_day": 1500,
          "laydown_per_site": 5000,
          "crew_size": 4,
          "crew_cost_per_day": 1160
        },
        "separate": {
          "a": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          },
          "b": {
            "mobilization_events": 1,
            "truck_days": 10,
            "laydown_sites": 1,
            "start_date": "2027-06-01"
          }
        },
        "coordinated": {
          "mobilization_events_a": 1,
          "mobilization_events_b": 1,
          "shared_truck_days": 12,
          "laydown_sites": 1,
          "start_date_a": "2027-06-01",
          "start_date_b": "2027-06-01"
        },
        "totals": {
          "separate": 532400,
          "coordinated": 515400,
          "savings": 17000,
          "savings_pct": 3.2,
          "separate_by_project": {
            "a": 266200,
            "b": 266200
          },
          "coordinated_by_project": {
            "a": 257700,
            "b": 257700
          }
        },
        "range": {
          "separate": [
            452540,
            612260
          ],
          "coordinated": [
            438090,
            592710
          ],
          "savings": [
            12750,
            21250
          ]
        },
        "formula": "Separate = sum per project of (mobilization_events x mobilization rate + truck_days x truck rate + laydown_sites x laydown rate). Coordinated = mobilization_events_a x rate + mobilization_events_b x rate + shared_truck_days x truck rate + laydown_sites x laydown rate. Shared costs split 50/50 per project.",
        "assumptions": [
          "Unit rates are placeholders; replace with real bids.",
          "Trucks are shared only when construction windows overlap (yes for this pair).",
          "One laydown yard is shared only when projects are under 8 km apart (yes for this pair)."
        ]
      },
      "kind": "user_project"
    }
  ],
  "closure_conflicts": [
    {
      "project_id": "USR_H010FE",
      "short_name": "Corridor upgrade",
      "road": "US-17",
      "overlap_start": "2027-06-01",
      "overlap_end": "2027-12-15",
      "hours": "21:00-05:00",
      "severity": "requires_review"
    }
  ]
}
```

Example file: `examples/POST_contracts_save.json`

---

## Live updates

### `GET /events?since=0`

Poll every few seconds with the last `latest_seq` you saw; refetch the collections that changed. Only events visible to the caller (public collections, or ones involving the caller's company).

Headers: `X-Company-Id: CMP_B`

Response `200`:

```json
{
  "latest_seq": 46,
  "events": [
    {
      "seq": 1,
      "ts": "2026-09-27T00:11:01.752241+00:00",
      "company_id": "CMP_B",
      "collection": "projects",
      "op": "insert",
      "doc_id": "USR_H010FE",
      "summary": "Demo Contractor B added project Corridor upgrade",
      "visibility": "all",
      "id": "EVT_1"
    },
    {
      "seq": 2,
      "ts": "2026-09-27T00:11:01.782680+00:00",
      "company_id": "CMP_B",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_H010FE__DESC_3",
      "summary": "Overlap Corridor upgrade ↔ Jasper–Okatie",
      "visibility": "all",
      "id": "EVT_2"
    },
    {
      "seq": 3,
      "ts": "2026-09-27T00:11:01.782680+00:00",
      "company_id": "CMP_B",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_H010FE__DESC_5",
      "summary": "Overlap Corridor upgrade ↔ Okatie–Bluffton",
      "visibility": "all",
      "id": "EVT_3"
    },
    {
      "seq": 4,
      "ts": "2026-09-27T00:11:01.782680+00:00",
      "company_id": "CMP_B",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_H010FE__GPC_2",
      "summary": "Overlap Corridor upgrade ↔ McIntosh–Purrysburg",
      "visibility": "all",
      "id": "EVT_4"
    },
    {
      "seq": 5,
      "ts": "2026-09-27T00:11:01.782680+00:00",
      "company_id": "CMP_B",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_H010FE__GPC_3",
      "summary": "Overlap Corridor upgrade ↔ Goshen–McIntosh",
      "visibility": "all",
      "id": "EVT_5"
    },
    {
      "seq": 6,
      "ts": "2026-09-27T00:11:01.794586+00:00",
      "company_id": "CMP_B",
      "collection": "projects",
      "op": "update",
      "doc_id": "USR_H010FE",
      "summary": "Demo Contractor B updated project Corridor upgrade",
      "visibility": "all",
      "id": "EVT_6"
    },
    {
      "seq": 7,
      "ts": "2026-09-27T00:11:01.812037+00:00",
      "company_id": "CMP_B",
      "collection": "overlaps",
      "op": "update",
      "doc_id": "OVL_USR_H010FE__DESC_3",
      "summary": "Overlap Corridor upgrade ↔ Jasper–Okatie",
      "visibility": "all",
      "id": "EVT_7"
    },
    {
      "seq": 8,
      "ts": "2026-09-27T00:11:01.813034+00:00",
      "company_id": "CMP_B",
      "collection": "overlaps",
      "op": "update",
      "doc_id": "OVL_USR_H010FE__DESC_5",
      "summary": "Overlap Corridor upgrade ↔ Okatie–Bluffton",
      "visibility": "all",
      "id": "EVT_8"
    },
    {
      "seq": 9,
      "ts": "2026-09-27T00:11:01.813034+00:00",
      "company_id": "CMP_B",
      "collection": "overlaps",
      "op": "update",
      "doc_id": "OVL_USR_H010FE__GPC_2",
      "summary": "Overlap Corridor upgrade ↔ McIntosh–Purrysburg",
      "visibility": "all",
      "id": "EVT_9"
    },
    {
      "seq": 10,
      "ts": "2026-09-27T00:11:01.813034+00:00",
      "company_id": "CMP_B",
      "collection": "overlaps",
      "op": "update",
      "doc_id": "OVL_USR_H010FE__GPC_3",
      "summary": "Overlap Corridor upgrade ↔ Goshen–McIntosh",
      "visibility": "all",
      "id": "EVT_10"
    },
    {
      "seq": 11,
      "ts": "2026-09-27T00:11:01.871520+00:00",
      "company_id": "CMP_C",
      "collection": "resources",
      "op": "insert",
      "doc_id": "RES_VN17K4",
      "summary": "Coastal Crane (demo) listed 2 x 60-ton crane",
      "visibility": "all",
      "id": "EVT_11"
    },
    {
      "seq": 12,
      "ts": "2026-09-27T00:11:01.896931+00:00",
      "company_id": "CMP_C",
      "collection": "resources",
      "op": "update",
      "doc_id": "RES_VN17K4",
      "summary": "Coastal Crane (demo) updated 60-ton crane",
      "visibility": "all",
      "id": "EVT_12"
    },
    {
      "seq": 17,
      "ts": "2026-09-27T00:11:01.977719+00:00",
      "company_id": "CMP_B",
      "collection": "jobs",
      "op": "insert",
      "doc_id": "JOB_TMHGR1",
      "summary": "Demo Contractor B posted Transmission lineworker",
      "visibility": "all",
      "id": "EVT_17"
    },
    {
      "seq": 18,
      "ts": "2026-09-27T00:11:01.997615+00:00",
      "company_id": null,
      "collection": "applications",
      "op": "insert",
      "doc_id": "APP_2ZPGWZ",
      "summary": "New application for Transmission lineworker",
      "visibility": "CMP_B",
      "id": "EVT_18"
    },
    {
      "seq": 19,
      "ts": "2026-09-27T00:11:02.015597+00:00",
      "company_id": "CMP_B",
      "collection": "applications",
      "op": "update",
      "doc_id": "APP_2ZPGWZ",
      "summary": "Application for Transmission lineworker reviewed",
      "visibility": "CMP_B",
      "id": "EVT_19"
    },
    {
      "seq": 26,
      "ts": "2026-09-27T00:11:02.112146+00:00",
      "company_id": "CMP_A",
      "collection": "resources",
      "op": "insert",
      "doc_id": "RES_AB4MPO",
      "summary": "Demo Contractor A listed 2 x Crane",
      "visibility": "all",
      "id": "EVT_26"
    },
    {
      "seq": 28,
      "ts": "2026-09-27T00:11:02.755887+00:00",
      "company_id": "CMP_A",
      "collection": "projects",
      "op": "insert",
      "doc_id": "USR_TKKP71",
      "summary": "Demo Contractor A added project Hardeeville Area Reliability Project - Jasper to Bluffton 115 kV Line Rebuild",
      "visibility": "all",
      "id": "EVT_28"
    },
    {
      "seq": 29,
      "ts": "2026-09-27T00:11:02.801006+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__DESC_3",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Okatie",
      "visibility": "all",
      "id": "EVT_29"
    },
    {
      "seq": 30,
      "ts": "2026-09-27T00:11:02.802011+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__DESC_6",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Burton–St Helena",
      "visibility": "all",
      "id": "EVT_30"
    },
    {
      "seq": 31,
      "ts": "2026-09-27T00:11:02.802011+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__DESC_7",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Burton–St Helena",
      "visibility": "all",
      "id": "EVT_31"
    },
    {
      "seq": 32,
      "ts": "2026-09-27T00:11:02.802011+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__DESC_10",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Okatie–Bluffton",
      "visibility": "all",
      "id": "EVT_32"
    },
    {
      "seq": 33,
      "ts": "2026-09-27T00:11:02.803017+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__DESC_23",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Jasper–Okatie",
      "visibility": "all",
      "id": "EVT_33"
    },
    {
      "seq": 34,
      "ts": "2026-09-27T00:11:02.803017+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__GPC_20067",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Deptford–Magnolia",
      "visibility": "all",
      "id": "EVT_34"
    },
    {
      "seq": 35,
      "ts": "2026-09-27T00:11:02.803017+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__GPC_20066",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Boulevard–Deptford",
      "visibility": "all",
      "id": "EVT_35"
    },
    {
      "seq": 36,
      "ts": "2026-09-27T00:11:02.803017+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__GPC_20277",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ McIntosh–Purrysburg",
      "visibility": "all",
      "id": "EVT_36"
    },
    {
      "seq": 37,
      "ts": "2026-09-27T00:11:02.804009+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__GPC_20785",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Goshen–Kraft",
      "visibility": "all",
      "id": "EVT_37"
    },
    {
      "seq": 38,
      "ts": "2026-09-27T00:11:02.804009+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__GPC_20065",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Goshen–McIntosh",
      "visibility": "all",
      "id": "EVT_38"
    },
    {
      "seq": 39,
      "ts": "2026-09-27T00:11:02.804666+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__GPC_20783",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Coleman–Dean Forest",
      "visibility": "all",
      "id": "EVT_39"
    },
    {
      "seq": 40,
      "ts": "2026-09-27T00:11:02.804666+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__GPC_20407",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Magnolia–Truman Parkway",
      "visibility": "all",
      "id": "EVT_40"
    },
    {
      "seq": 41,
      "ts": "2026-09-27T00:11:02.804666+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__GPC_21006",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Boulevard–Magnolia",
      "visibility": "all",
      "id": "EVT_41"
    },
    {
      "seq": 42,
      "ts": "2026-09-27T00:11:02.804666+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__GPC_21023",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Dean Forest–Little Ogeechee",
      "visibility": "all",
      "id": "EVT_42"
    },
    {
      "seq": 43,
      "ts": "2026-09-27T00:11:02.804666+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__GPC_20784",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Coleman–Meldrim",
      "visibility": "all",
      "id": "EVT_43"
    },
    {
      "seq": 44,
      "ts": "2026-09-27T00:11:02.804666+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__GPC_20796",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Meldrim",
      "visibility": "all",
      "id": "EVT_44"
    },
    {
      "seq": 45,
      "ts": "2026-09-27T00:11:02.804666+00:00",
      "company_id": "CMP_A",
      "collection": "overlaps",
      "op": "insert",
      "doc_id": "OVL_USR_TKKP71__USR_H010FE",
      "summary": "Overlap Hardeeville Area Reliability Project - … ↔ Corridor upgrade",
      "visibility": "all",
      "id": "EVT_45"
    }
  ]
}
```

Example file: `examples/GET_events.json`

---

## Errors

### `POST /resources`

Writes without `X-Company-Id`.

Request body:
```json
{
  "name": "Crane",
  "type": "equipment",
  "quantity": 1
}
```

Response `401`:

```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Select a company first"
  }
}
```

Example file: `examples/ERROR_401.json`

---

### `PATCH /resources/{id}`

Changing another company's record, or a public filing.

Headers: `X-Company-Id: CMP_A`

Request body:
```json
{
  "quantity": 9
}
```

Response `403`:

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "You can only change your own company's resources"
  }
}
```

Example file: `examples/ERROR_403.json`

---

<!-- NEW_ENDPOINTS_END -->
