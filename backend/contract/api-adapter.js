// api-adapter.js
// Lets the existing design prototype (app.js) run on the Gridlock API without rewriting it.
// It fetches /projects and /overlaps, converts them to the starter-workbook shape that app.js already reads
// (window.GRIDLOCK_CHALLENGE), keeps every new API field on each record, then loads app.js.
// If the API is down, app.js runs on the bundled data/challenge.js instead.
//
// index.html change:
//   <script src="data/challenge.js"></script>
//   <script>window.GRIDLOCK_API_URL = "http://localhost:8000";</script>
//   <script src="api-adapter.js"></script>
//   (remove the <script src="app.js"> tag; the adapter loads it)

(function () {
  const BASE = (window.GRIDLOCK_API_URL || "http://localhost:8000").replace(/\/$/, "");

  function toWorkbookProject(p) {
    const [a = {}, b = {}] = p.endpoints || [];
    const ids = p.overlap_ids || [];
    return {
      ...p, // every API field stays available (short_name, counties, construction_window, quality_flags, ...)
      project_id: p.id,
      utility: p.utility_name,
      utility_code: p.utility,
      state: p.state,
      project_name: p.name,
      name_a: a.name ?? null, lat_a: a.lat ?? null, lon_a: a.lon ?? null,
      name_b: b.name ?? null, lat_b: b.lat ?? null, lon_b: b.lon ?? null,
      lat_center: p.center ? p.center.lat : null,
      lon_center: p.center ? p.center.lon : null,
      in_service_date: p.in_service_date,
      overlap_count: ids.length,
      overlap_1: ids[0] ?? null, overlap_2: ids[1] ?? null, overlap_3: ids[2] ?? null,
    };
  }

  function toWorkbookOverlap(o, byId) {
    const a = byId[o.project_a], b = byId[o.project_b];
    return {
      ...o, // label, potential, tier, cost_scenario, window_overlap_months, ...
      overlap_id: o.id,
      distance_mi: o.center_distance_mi,
      "time_gap (day)": o.time_gap_days,
      utility_a: a ? a.utility_name : null, project_id_a: o.project_a, project_name_a: a ? a.name : null,
      utility_b: b ? b.utility_name : null, project_id_b: o.project_b, project_name_b: b ? b.name : null,
    };
  }

  // Small client the new features can call directly.
  async function call(method, path, body) {
    const r = await fetch(BASE + path, {
      method, headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(data?.error?.message || r.statusText), { code: data?.error?.code, status: r.status });
    return data;
  }
  window.GridlockAPI = {
    base: BASE,
    projects: (params = {}) => call("GET", "/projects?" + new URLSearchParams(params)),
    overlaps: (params = {}) => call("GET", "/overlaps?" + new URLSearchParams(params)),
    overlap: (id) => call("GET", `/overlaps/${id}`),
    project: (id) => call("GET", `/projects/${id}`),
    quality: () => call("GET", "/quality"),
    whatif: (body) => call("POST", "/whatif", body),
    brief: (id, mode = "summary", refresh = false) => call("POST", `/overlaps/${id}/brief`, { mode, refresh }),
    draft: (kind, text, draft = {}) => call("POST", "/draft", { kind, text, draft }),
    scenarioAssist: (overlap_id, message, scenario) => call("POST", "/scenario/assist", { overlap_id, message, scenario }),
    ask: (question) => call("POST", "/ask", { question }),
    exportUrl: () => BASE + "/export/overlaps.xlsx",
  };

  function loadApp() {
    const s = document.createElement("script");
    s.src = "app.js";
    document.body.appendChild(s);
  }

  (async function boot() {
    try {
      const [projects, overlaps] = await Promise.all([window.GridlockAPI.projects(), window.GridlockAPI.overlaps()]);
      const byId = Object.fromEntries(projects.map((p) => [p.id, p]));
      window.GRIDLOCK_CHALLENGE = {
        projects: projects.map(toWorkbookProject),
        overlaps: overlaps.map((o) => toWorkbookOverlap(o, byId)), // already ranked by the API
      };
      window.GRIDLOCK_DATA_SOURCE = "api";
    } catch (e) {
      console.warn("Gridlock API unavailable, using bundled starter data:", e.message);
      window.GRIDLOCK_DATA_SOURCE = "bundled";
    }
    loadApp();
  })();
})();
