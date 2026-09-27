// Gridlock mock API server. Same routes and response shapes as the real backend (see API_README.md).
// Run: node mock-server.js        (no npm install needed, Node 18+)
// Options: PORT=8000  GEMINI_LATENCY_MS=1500  MOCK_GEMINI_FAIL=1 (simulate Gemini outage -> fallback briefs, 503 on /ask)

const http = require("http");
const fs = require("fs");
const path = require("path");
const { URL } = require("url");

const PORT = Number(process.env.PORT || 8000);
const GEMINI_LATENCY_MS = Number(process.env.GEMINI_LATENCY_MS || 1500);
const GEMINI_FAIL = process.env.MOCK_GEMINI_FAIL === "1";

const DATA = JSON.parse(fs.readFileSync(path.join(__dirname, "mock_api.json"), "utf8"));
const projects = DATA.projects;
const overlaps = DATA.overlaps;
const byId = (arr) => Object.fromEntries(arr.map((x) => [x.id, x]));
const P = byId(projects);
const O = byId(overlaps);
const briefCache = {};

// ---------- helpers ----------
function send(res, status, body, headers = {}) {
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    ...headers,
  });
  res.end(typeof body === "string" || Buffer.isBuffer(body) ? body : JSON.stringify(body, null, 2));
}
const err = (res, status, code, message) => send(res, status, { error: { code, message } });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      if (!raw) return resolve({});
      try { resolve(JSON.parse(raw)); } catch { reject(new Error("Body is not valid JSON")); }
    });
  });
}

function haversineMi(a, b) {
  const R = 3958.8, rad = (d) => (d * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat), dLon = rad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
// Local planar approximation (km) for closest-point distance, good enough for a mock.
function toXY(p, lat0) { return { x: p.lon * 111.32 * Math.cos((lat0 * Math.PI) / 180), y: p.lat * 110.574 }; }
function ptSeg(p, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y, L = dx * dx + dy * dy;
  const t = L ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L)) : 0;
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}
function closestKm(ptsA, ptsB) {
  const lat0 = ptsA[0].lat, A = ptsA.map((p) => toXY(p, lat0)), B = ptsB.map((p) => toXY(p, lat0));
  const segs = (S) => (S.length === 1 ? [[S[0], S[0]]] : [[S[0], S[1]]]);
  let best = Infinity;
  for (const [a1, a2] of segs(A)) for (const [b1, b2] of segs(B))
    best = Math.min(best, ptSeg(a1, b1, b2), ptSeg(a2, b1, b2), ptSeg(b1, a1, a2), ptSeg(b2, a1, a2));
  return best;
}
function tierFor(km) {
  if (km <= 0.05) return ["crossing", "Touching/crossing: must coordinate outages and crossing structures"];
  if (km < 1.6) return ["shared_land", "Under 1.6 km: can share right-of-way, access roads, permits"];
  if (km < 8) return ["shared_site", "Under 8 km: can share laydown yards and deliveries"];
  if (km < 40) return ["shared_crews", "Under 40 km: can share crews and equipment"];
  return [null, null];
}
const d = (s) => new Date(s + "T00:00:00Z");
const iso = (dt) => dt.toISOString().slice(0, 10);
const addMonths = (s, m) => { const x = d(s); x.setUTCMonth(x.getUTCMonth() + m); return iso(x); };
function overlapMonths(w1, w2) {
  const s = Math.max(d(w1.start), d(w2.start)), e = Math.min(d(w1.end), d(w2.end));
  return e > s ? Math.round((e - s) / (1000 * 60 * 60 * 24 * 30.44)) : 0;
}
// Mock geocoder. The real backend uses Nominatim for free-text locations.
const PLACES = {
  hardeeville: { lat: 32.2871, lon: -81.079, label: "Hardeeville, SC" }, savannah: { lat: 32.0809, lon: -81.0912, label: "Savannah, GA" },
  okatie: { lat: 32.3338, lon: -81.0325, label: "Okatie, SC" }, bluffton: { lat: 32.2371, lon: -80.8604, label: "Bluffton, SC" },
  ridgeland: { lat: 32.4802, lon: -80.9801, label: "Ridgeland, SC" }, pooler: { lat: 32.1155, lon: -81.247, label: "Pooler, GA" },
  rincon: { lat: 32.296, lon: -81.2354, label: "Rincon, GA" }, augusta: { lat: 33.4735, lon: -82.0105, label: "Augusta, GA" },
  "north augusta": { lat: 33.5018, lon: -81.9651, label: "North Augusta, SC" }, evans: { lat: 33.5337, lon: -82.1307, label: "Evans, GA" },
  charleston: { lat: 32.7765, lon: -79.9311, label: "Charleston, SC" }, jasper: { lat: 32.3591, lon: -81.1246, label: "Jasper County, SC" },
};
function geocode(text) {
  const t = (text || "").toLowerCase();
  const key = Object.keys(PLACES).sort((a, b) => b.length - a.length).find((k) => t.includes(k));
  return key ? { ...PLACES[key], query: text, source: "mock gazetteer" } : null;
}
const yearOf = (s) => Number(String(s).slice(0, 4));
function textMatch(p, q) {
  const hay = [p.name, p.short_name, p.utility_name, ...(p.counties || []), ...p.endpoints.map((e) => e.name)].join(" ").toLowerCase();
  return q.toLowerCase().split(/\s+/).every((w) => hay.includes(w));
}
const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
const WORDNUM = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, a: 1, an: 1 };
const toNum = (w) => (w ? (isNaN(Number(w)) ? WORDNUM[w.toLowerCase()] ?? null : Number(w)) : null);
function parseDates(text) {
  // Handles "June to December 2027", "June 1, 2027 to December 15, 2027", "Jun 3-10 2027"
  const re = /\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:\s+(\d{1,2})(?!\d))?(?:\s*[-–]\s*(\d{1,2})(?!\d))?(?:,?\s+(20\d\d))?/gi;
  const hits = [...text.matchAll(re)].map((m) => ({ m: MONTHS[m[1].toLowerCase().slice(0, 3)], d: m[2] ? Number(m[2]) : null, d2: m[3] ? Number(m[3]) : null, y: m[4] ? Number(m[4]) : null }));
  if (!hits.length) return {};
  const yr = (text.match(/\b(20\d\d)\b/) || [])[1];
  const lastDay = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();
  const fmt = (h, day) => { const y = h.y || (yr ? Number(yr) : null); return y ? `${y}-${String(h.m).padStart(2, "0")}-${String(day).padStart(2, "0")}` : null; };
  const first = hits[0];
  if (hits.length === 1) {
    const y = first.y || (yr ? Number(yr) : null);
    return { start: fmt(first, first.d || 1), end: first.d2 ? fmt(first, first.d2) : y ? fmt(first, first.d ? first.d : lastDay(y, first.m)) : null, has_year: !!y };
  }
  const last = hits[hits.length - 1], y2 = last.y || (yr ? Number(yr) : null);
  return { start: fmt(first, first.d || 1), end: y2 ? fmt(last, last.d || lastDay(y2, last.m)) : null, has_year: !!yr };
}

function validDate(s) { return typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s) && !isNaN(d(s)); }

// ---------- routes ----------
async function handle(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const parts = url.pathname.replace(/\/+$/, "").split("/").filter(Boolean);
  const q = url.searchParams;

  if (req.method === "OPTIONS") return send(res, 204, "");

  if (req.method === "GET") {
    if (url.pathname === "/health") return send(res, 200, { status: "ok" });
    if (url.pathname === "/meta") return send(res, 200, DATA.meta);

    if (parts[0] === "projects" && parts.length === 1) {
      let out = projects;
      const u = q.get("utility"), c = q.get("confidence"), h = q.get("has_overlap");
      if (u && !["DESC", "GPC"].includes(u)) return err(res, 400, "BAD_REQUEST", "utility must be DESC or GPC");
      if (c && !["high", "medium", "low", "not_found"].includes(c)) return err(res, 400, "BAD_REQUEST", "invalid confidence");
      if (u) out = out.filter((p) => p.utility === u);
      if (c) out = out.filter((p) => p.location_confidence === c);
      if (h === "true") out = out.filter((p) => p.overlap_ids.length > 0);
      if (h === "false") out = out.filter((p) => p.overlap_ids.length === 0);
      if (q.get("year_from")) out = out.filter((p) => yearOf(p.in_service_date) >= Number(q.get("year_from")));
      if (q.get("year_to")) out = out.filter((p) => yearOf(p.in_service_date) <= Number(q.get("year_to")));
      if (q.get("q")) out = out.filter((p) => textMatch(p, q.get("q")));
      return send(res, 200, out);
    }
    if (parts[0] === "projects" && parts.length === 2) {
      return P[parts[1]] ? send(res, 200, P[parts[1]]) : err(res, 404, "NOT_FOUND", `Project ${parts[1]} does not exist`);
    }

    if (parts[0] === "overlaps" && parts.length === 1) {
      const maxMi = q.has("max_mi") ? Number(q.get("max_mi")) : 25;
      const minWin = q.has("min_window_overlap_months") ? Number(q.get("min_window_overlap_months")) : 0;
      const tier = q.get("tier"), sort = q.get("sort") || "score";
      if (isNaN(maxMi) || isNaN(minWin)) return err(res, 400, "BAD_REQUEST", "max_mi and min_window_overlap_months must be numbers");
      if (!["score", "distance", "timeline"].includes(sort)) return err(res, 400, "BAD_REQUEST", "sort must be score, distance or timeline");
      const pot = q.get("potential");
      if (pot && !["high", "moderate", "lower"].includes(pot)) return err(res, 400, "BAD_REQUEST", "potential must be high, moderate or lower");
      const yf = q.get("year_from") ? Number(q.get("year_from")) : -Infinity, yt = q.get("year_to") ? Number(q.get("year_to")) : Infinity;
      const inYears = (o) => [P[o.project_a], P[o.project_b]].some((p) => yearOf(p.in_service_date) >= yf && yearOf(p.in_service_date) <= yt);
      let out = overlaps.filter((o) => o.center_distance_mi <= maxMi && o.window_overlap_months >= minWin && (!tier || o.tier === tier) && (!pot || o.potential === pot) && inYears(o)
        && (!q.get("q") || textMatch(P[o.project_a], q.get("q")) || textMatch(P[o.project_b], q.get("q"))));
      const cmp = { score: (a, b) => b.score - a.score, distance: (a, b) => a.center_distance_mi - b.center_distance_mi, timeline: (a, b) => b.window_overlap_months - a.window_overlap_months }[sort];
      return send(res, 200, [...out].sort(cmp));
    }
    if (parts[0] === "overlaps" && parts.length === 2) {
      return O[parts[1]] ? send(res, 200, O[parts[1]]) : err(res, 404, "NOT_FOUND", `Overlap ${parts[1]} does not exist`);
    }

    if (url.pathname === "/quality") return send(res, 200, DATA.quality);

    if (url.pathname === "/export/overlaps.xlsx") {
      const f = path.join(__dirname, "overlaps.xlsx");
      if (!fs.existsSync(f)) return err(res, 500, "INTERNAL", "overlaps.xlsx missing next to mock-server.js");
      return send(res, 200, fs.readFileSync(f), {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": 'attachment; filename="overlaps.xlsx"',
      });
    }
  }

  if (req.method === "POST") {
    let body;
    try { body = await readBody(req); } catch (e) { return err(res, 400, "BAD_REQUEST", e.message); }

    // POST /whatif
    if (url.pathname === "/whatif") {
      const { name, utility = null, voltage_kv = null, location_text = null, construction_window: w, max_shift_months = 24 } = body;
      let endpoints = body.endpoints;
      if (!name) return err(res, 400, "BAD_REQUEST", "name is required");
      if (utility !== null && !["DESC", "GPC"].includes(utility)) return err(res, 400, "BAD_REQUEST", "utility must be DESC, GPC or omitted");
      let geocoded = null;
      if (!endpoints && location_text) {
        geocoded = geocode(location_text);
        if (!geocoded) return err(res, 400, "BAD_REQUEST", `Could not locate "${location_text}". Try a town name or drop a pin on the map.`);
        endpoints = [{ name: geocoded.label, lat: geocoded.lat, lon: geocoded.lon }];
      }
      if (!Array.isArray(endpoints) || endpoints.length < 1 || endpoints.length > 2 || endpoints.some((e) => typeof e.lat !== "number" || typeof e.lon !== "number"))
        return err(res, 400, "BAD_REQUEST", "provide endpoints (1 or 2 with numeric lat and lon) or location_text");
      if (!w || !validDate(w.start) || !validDate(w.end) || d(w.end) <= d(w.start))
        return err(res, 400, "BAD_REQUEST", "construction_window needs valid start and end (YYYY-MM-DD), end after start");

      const center = { lat: endpoints.reduce((s, e) => s + e.lat, 0) / endpoints.length, lon: endpoints.reduce((s, e) => s + e.lon, 0) / endpoints.length };
      const found = [];
      for (const p of projects) {
        if ((utility && p.utility === utility) || !p.center) continue;
        const mi = haversineMi(center, p.center);
        if (mi >= 25) continue;
        const pts = p.endpoints.filter((e) => e.lat !== null);
        const km = closestKm(endpoints, pts);
        const [tier] = tierFor(km);
        found.push({ project_id: p.id, short_name: p.short_name, name: p.name, utility: p.utility, utility_name: p.utility_name, construction_window: p.construction_window,
          center_distance_mi: +mi.toFixed(2), closest_distance_km: +km.toFixed(2), tier, window_overlap_months: overlapMonths(w, p.construction_window) });
      }
      found.sort((a, b) => a.center_distance_mi - b.center_distance_mi);

      const total = (win) => found.reduce((s, f) => s + overlapMonths(win, P[f.project_id].construction_window), 0);
      const before = total(w);
      let best = { shift: 0, months: before };
      const today = iso(new Date());
      for (let m = -max_shift_months; m <= max_shift_months; m++) {
        const win = { start: addMonths(w.start, m), end: addMonths(w.end, m) };
        if (m !== 0 && win.start < today) continue; // never suggest starting in the past
        const t = total(win);
        if (t > best.months || (t === best.months && Math.abs(m) < Math.abs(best.shift))) best = { shift: m, months: t };
      }
      const suggested = { start: addMonths(w.start, best.shift), end: addMonths(w.end, best.shift) };
      const explanation = found.length === 0
        ? "No projects from the other utility are within 25 miles, so no shift is needed."
        : best.shift === 0
          ? (best.months > 0 ? "The current window already gives the most shared construction time with nearby projects." : "Nearby projects finish before this one could start, so no future shift creates shared construction time. Coordinate on staging yards and permits instead.")
          : `Moving the window ${Math.abs(best.shift)} months ${best.shift < 0 ? "earlier" : "later"} increases shared construction time with nearby projects from ${before} to ${best.months} months, so crews and equipment can be shared.`;

      return send(res, 200, {
        proposed: { name, utility, voltage_kv, endpoints, construction_window: w, center, geocoded },
        overlaps: found,
        closure_conflicts: [],
        closure_data_available: false,
        closure_note: "No public road-closure data is connected. Closure conflicts are not evaluated.",
        suggestion: { shift_months: best.shift, suggested_window: suggested, window_overlap_months_before: before, window_overlap_months_after: best.months, explanation },
      });
    }

    // POST /overlaps/{id}/brief
    if (parts[0] === "overlaps" && parts.length === 3 && parts[2] === "brief") {
      const o = O[parts[1]];
      if (!o) return err(res, 404, "NOT_FOUND", `Overlap ${parts[1]} does not exist`);
      const mode = body.mode || "summary";
      if (!["summary", "plan", "risks"].includes(mode)) return err(res, 400, "BAD_REQUEST", "mode must be summary, plan or risks");
      const ck = `${o.id}:${mode}`;
      if (briefCache[ck] && !body.refresh) return send(res, 200, { overlap_id: o.id, mode, brief: briefCache[ck].brief, source: briefCache[ck].source, cached: true });
      await sleep(GEMINI_LATENCY_MS);
      const a = P[o.project_a], b = P[o.project_b];
      let text =
        `${a.utility_name}'s "${a.name}" and ${b.utility_name}'s "${b.name}" are ${o.center_distance_mi} miles apart center to center, ` +
        `and their closest points are ${o.closest_distance_km} km apart (${o.tier_explanation.toLowerCase()}). ` +
        (o.shared_endpoint ? "Both projects connect to the same substation, so outages and work at that site must be coordinated. " : "") +
        (o.window_overlap_months > 0
          ? `They are under construction at the same time for about ${o.window_overlap_months} months, which is the window to share crews and equipment. `
          : `Their construction windows do not overlap (in-service dates are ${o.time_gap_days} days apart), so sharing would require shifting one schedule. `) +
        (o.cost_estimate.total_estimated_savings_usd ? `Estimated savings from coordinating: about $${o.cost_estimate.total_estimated_savings_usd.toLocaleString("en-US")}.` : "");
      if (mode === "plan") text =
        `Coordination plan for ${o.label}: 1) Planners from ${a.utility_name} and ${b.utility_name} confirm construction windows (${a.construction_window.start} to ${a.construction_window.end} and ${b.construction_window.start} to ${b.construction_window.end}). ` +
        `2) ${o.window_overlap_months > 0 ? `Schedule shared crews and equipment during the ${o.window_overlap_months} overlapping months.` : "Decide whether one schedule can move so construction overlaps."} ` +
        `3) ${o.closest_distance_km < 8 ? "Share one laydown yard and delivery route." : "Share crews and contractors; staging stays separate."} ` +
        `4) ${o.shared_endpoint ? "Coordinate outages at the shared substation." : "Exchange contacts and review permits for common roads."}`;
      if (mode === "risks") text =
        `Risks for ${o.label}: ` + [
          o.window_overlap_months === 0 ? `construction windows do not overlap, so sharing requires a schedule change` : null,
          o.shared_endpoint ? "work at a shared substation needs coordinated outages" : null,
          P[o.project_a].location_confidence !== "high" || P[o.project_b].location_confidence !== "high" ? "one or more locations are not fully confirmed" : null,
          "cost figures are illustrative until real bids are available",
        ].filter(Boolean).join("; ") + ".";
      const source = GEMINI_FAIL ? "fallback" : "gemini";
      briefCache[ck] = { brief: (GEMINI_FAIL ? "" : "(mock Gemini) ") + text, source };
      return send(res, 200, { overlap_id: o.id, mode, brief: briefCache[ck].brief, source, cached: false });
    }

    // POST /draft : turn a free-text description into a reviewable structured draft (Gemini with a JSON schema)
    if (url.pathname === "/draft") {
      const { kind, text = "", draft = {} } = body;
      const FIELDS = {
        project: ["name", "description", "location", "start_date", "end_date", "work_type", "lane_closures", "work_hours", "roads_affected"],
        resource: ["name", "quantity", "location", "dates", "rate"],
        job: ["role", "openings", "project", "dates", "requirements"],
      };
      if (!FIELDS[kind]) return err(res, 400, "BAD_REQUEST", "kind must be project, resource or job");
      if (!text.trim()) return err(res, 400, "BAD_REQUEST", "text is required");
      await sleep(GEMINI_LATENCY_MS);
      if (GEMINI_FAIL) return err(res, 503, "GEMINI_UNAVAILABLE", "Gemini is not responding. Use the manual form.");
      const t = text.toLowerCase(), f = {};
      const set = (k, v, c = "high") => { if (v !== null && v !== undefined && v !== "") f[k] = { value: v, confidence: c }; };
      const g = geocode(text), dt = parseDates(text);
      if (kind === "project") {
        set("name", /corridor/.test(t) ? "Corridor upgrade" : /substation/.test(t) ? "Substation upgrade" : /bridge/.test(t) ? "Bridge replacement" : /resurfac/.test(t) ? "Road resurfacing" : null);
        set("description", text.length > 20 ? text.slice(0, 160) : null, "medium");
        set("location", g ? `Near ${g.label}` : null);
        set("start_date", dt.start, dt.has_year ? "high" : "medium");
        set("end_date", dt.end, dt.has_year ? "high" : "medium");
        set("work_type", /road|corridor|resurfac|lane/.test(t) ? "Roadway improvement" : /line|transmission|substation/.test(t) ? "Utility construction" : null, "medium");
        set("lane_closures", /lane closure/.test(t) ? (/north/.test(t) ? "Lane closure (northbound)" : /south/.test(t) ? "Lane closure (southbound)" : "Lane closure, direction not stated") : null, /north|south/.test(t) ? "high" : "medium");
        const hrs = text.match(/(\d{1,2}\s*(?:am|pm))\s*(?:to|-|–)\s*(\d{1,2}\s*(?:am|pm))/i);
        set("work_hours", hrs ? `${hrs[1].toUpperCase()} – ${hrs[2].toUpperCase()}` : /night/.test(t) ? "Nighttime (hours not stated)" : null, hrs ? "high" : "medium");
        const road = text.match(/\b(US-?\d+|I-?\d+|SC-?\d+|GA-?\d+)\b/i);
        set("roads_affected", road ? road[1].toUpperCase().replace(/^(US|I|SC|GA)(\d)/, "$1-$2") : null);
      } else if (kind === "resource") {
        set("name", /bucket truck/.test(t) ? "Bucket trucks with operators" : /crane/.test(t) ? "Crane" : /lineworker/.test(t) ? "Certified lineworkers" : null);
        set("quantity", toNum((t.match(/\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an)\s+(?:bucket|truck|crane|lineworker|worker|crew)/) || [])[1]));
        set("location", g ? g.label : null);
        set("dates", dt.start ? `${dt.start}${dt.end ? " to " + dt.end : ""}` : null, "medium");
        set("rate", (text.match(/\$[\d,]+/) || [])[0] || null);
      } else {
        set("role", /lineworker/.test(t) ? "Transmission lineworker" : /operator/.test(t) ? "Bucket truck operator" : /electrician/.test(t) ? "Substation electrician" : null);
        set("openings", toNum((t.match(/\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an)\s+(?:certified\s+)?(?:lineworker|worker|operator|electrician)/) || [])[1]));
        set("dates", dt.start ? `${dt.start}${dt.end ? " to " + dt.end : ""}` : /winter/.test(t) ? "Winter (dates not stated)" : null, "medium");
        set("requirements", /certified/.test(t) ? "Relevant certification required" : null, "medium");
      }
      const fields = {};
      for (const k of FIELDS[kind]) fields[k] = f[k] || (draft[k] ? { value: draft[k], confidence: "user" } : { value: null, confidence: null });
      const missing = FIELDS[kind].filter((k) => !fields[k].value);
      const Q = { location: "Where exactly is the work? A town or road segment works.", start_date: "What is the exact start date?", end_date: "What is the end date?",
        lane_closures: "Is there a lane closure, and in which direction?", roads_affected: "Which road or segment is affected?", work_hours: "What are the work hours?",
        quantity: "How many units are available?", dates: "Which dates?", rate: "What is the daily rate?", openings: "How many openings?", project: "Which project is this for?", requirements: "What qualifications are required?" };
      return send(res, 200, {
        kind, fields, missing, ready: missing.length <= 2,
        follow_up_questions: missing.map((k) => Q[k]).filter(Boolean).slice(0, 3),
        location_point: g ? { lat: g.lat, lon: g.lon, label: g.label } : null,
        source: "gemini", note: "(mock Gemini) Draft only. Nothing is saved until the user reviews it.",
      });
    }

    // POST /scenario/assist : Gemini proposes edits to an overlap's cost scenario
    if (url.pathname === "/scenario/assist") {
      const { overlap_id, message = "" } = body;
      const o = O[overlap_id];
      if (!o) return err(res, 404, "NOT_FOUND", `Overlap ${overlap_id} does not exist`);
      if (!message.trim()) return err(res, 400, "BAD_REQUEST", "message is required");
      await sleep(GEMINI_LATENCY_MS);
      if (GEMINI_FAIL) return err(res, 503, "GEMINI_UNAVAILABLE", "Gemini is not responding. Edit the inputs directly.");
      const sc = JSON.parse(JSON.stringify(body.scenario || o.cost_scenario));
      const r = sc.unit_rates, t = message.toLowerCase(), changes = [];
      const m1 = t.match(/(\d+)\s*(?:shared\s+)?(?:bucket\s+)?trucks?\s+for\s+(\d+)\s*days?/), m2 = t.match(/(\d+)\s*truck[- ]days?/);
      if (m1) changes.push({ path: "coordinated.shared_truck_days", value: Number(m1[1]) * Number(m1[2]), label: `Use ${m1[1]} shared bucket trucks for ${m1[2]} days (${Number(m1[1]) * Number(m1[2])} truck-days)` });
      else if (m2) changes.push({ path: "coordinated.shared_truck_days", value: Number(m2[1]), label: `Use ${m2[1]} shared truck-days` });
      if (/yard|laydown/.test(t)) changes.push({ path: "coordinated.laydown_sites", value: 1, label: "Share a single laydown yard" });
      const next = JSON.parse(JSON.stringify(sc));
      for (const c of changes) { const [a, b] = c.path.split("."); next[a][b] = c.value; }
      const proj = (x) => x.mobilization_events * r.mobilization_per_event + x.truck_days * r.bucket_truck_per_day + x.laydown_sites * r.laydown_per_site;
      const S = proj(next.separate.a) + proj(next.separate.b);
      const C = (next.coordinated.mobilization_events_a + next.coordinated.mobilization_events_b) * r.mobilization_per_event + next.coordinated.shared_truck_days * r.bucket_truck_per_day + next.coordinated.laydown_sites * r.laydown_per_site;
      const reply = changes.length
        ? `(mock Gemini) Applying these changes gives separate work at $${S.toLocaleString("en-US")} and coordinated work at $${C.toLocaleString("en-US")}, about $${(S - C).toLocaleString("en-US")} (${S ? Math.round(((S - C) / S) * 100) : 0}%) lower. ${o.window_overlap_months === 0 ? "Note: these construction windows do not overlap today, so sharing trucks requires moving one schedule." : ""}`
        : /date|shift|schedule/.test(t)
          ? `(mock Gemini) The construction windows overlap for ${o.window_overlap_months} months. Use "+ Add project" to test a shifted window, or ask me to try a specific number of truck-days.`
          : "(mock Gemini) I can adjust shared truck-days, the laydown yard, or explain the assumptions. Try: \"Share 2 bucket trucks for 5 days\".";
      return send(res, 200, { overlap_id, reply, suggested_changes: changes, preview_totals: { separate: S, coordinated: C, savings: S - C, savings_pct: S ? Math.round(((S - C) / S) * 1000) / 10 : 0 } });
    }

    // POST /ask
    if (url.pathname === "/ask") {
      const question = (body.question || "").trim();
      if (!question) return err(res, 400, "BAD_REQUEST", "question is required");
      await sleep(GEMINI_LATENCY_MS);
      if (GEMINI_FAIL) return err(res, 503, "GEMINI_UNAVAILABLE", "Gemini is not responding. Try again in a moment.");
      const ql = question.toLowerCase();
      let pick;
      const ranked = [...overlaps].sort((a, b) => b.score - a.score);
      if (/\b(save|saves|saving|savings|money|cost|cheap)/.test(ql)) {
        pick = [...overlaps].sort((a, b) => (b.cost_estimate.total_estimated_savings_usd || 0) - (a.cost_estimate.total_estimated_savings_usd || 0)).slice(0, 1);
      } else if (ql.includes("augusta")) {
        pick = ranked.filter((o) => ["DESC_1", "DESC_2"].includes(o.project_a));
      } else if (ql.includes("savannah") || ql.includes("hilton head") || ql.includes("bluffton")) {
        pick = ranked.filter((o) => ["DESC_3", "DESC_5"].includes(o.project_a)).slice(0, 2);
      } else {
        pick = ranked.slice(0, 1);
      }
      const lines = pick.map((o) => `${o.id}: ${P[o.project_a].name} (Dominion) and ${P[o.project_b].name} (Georgia Power), ${o.center_distance_mi} mi apart, ${o.window_overlap_months} months of overlapping construction`);
      let intent = { action: "none" };
      if (/\b(truck|crane|crew|resource|equipment|inventory)/.test(ql)) intent = { action: "navigate", page: "inventory" };
      else if (/\b(save|saves|saving|savings|money|cost)/.test(ql)) intent = { action: "navigate", page: "cost", overlap_id: pick[0]?.id };
      else if (/\b(job|hire|worker|certification)/.test(ql)) intent = { action: "navigate", page: "jobs" };
      else if (/\b(add|new|propos|describe|draft)/.test(ql)) intent = { action: "navigate", page: "addProject" };
      else if (/\b(closure|traffic|feasib|lane)/.test(ql)) intent = { action: "navigate", page: "feasibility" };
      else if (pick.length) intent = { action: "navigate", page: "opportunities", overlap_id: pick[0].id };
      return send(res, 200, {
        intent,
        answer: `(mock Gemini) Based on the planned projects: ${lines.join("; ")}.`,
        cited_project_ids: [...new Set(pick.flatMap((o) => [o.project_a, o.project_b]))],
        cited_overlap_ids: pick.map((o) => o.id),
      });
    }
  }

  return err(res, 404, "NOT_FOUND", `No route for ${req.method} ${url.pathname}`);
}

http.createServer((req, res) => handle(req, res).catch((e) => err(res, 500, "INTERNAL", e.message)))
  .listen(PORT, () => console.log(`Gridlock mock API on http://localhost:${PORT}  (Gemini latency ${GEMINI_LATENCY_MS} ms${GEMINI_FAIL ? ", Gemini FAILING" : ""})`));
