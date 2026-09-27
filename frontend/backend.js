// Connects the UI in app.js to the Gridlock backend (api.js).
// Backend records are converted to the shapes app.js already renders; actions call the real endpoints.
const API = window.GridlockAPI;
const COMPANY_ID = (window.GRIDLOCK_CONFIG || {}).companyId || 'CMP_A';
const WORKER_ID = (window.GRIDLOCK_CONFIG || {}).workerId || 'WRK_1';
const money = n => '$' + Math.round(Number(n) || 0).toLocaleString();
const moneyRange = r => r ? `${money(r[0])} – ${money(r[1])}` : '';

// ---- Backend record -> app.js shape ----
function toProject(p) {
  const eps = p.endpoints || [], mine = !!p.company_id, w = p.construction_window || {};
  return {
    ...p, _raw: p, project_id: p.id, project_name: p.name,
    utility: mine ? (p.company_id === COMPANY_ID ? 'Your company' : companyName(p.company_id)) : (p.utility_name || p.utility),
    lat_center: p.center?.lat, lon_center: p.center?.lon, name_a: eps[0]?.name || '', name_b: eps[1]?.name || '',
    in_service_date: p.in_service_date || w.end || '', overlap_count: (p.overlap_ids || []).length,
    source: mine ? 'contract-upload' : 'public', mine: p.company_id === COMPANY_ID,
    location: p.location_text || eps.map(e => e.name).filter(Boolean).join(' – '),
    start_date: w.start || '', end_date: w.end || ''
  };
}
function toOverlap(o) {
  return { ...o, overlap_id: o.id, project_id_a: o.project_a, project_id_b: o.project_b, distance_mi: o.closest_distance_mi ?? o.center_distance_mi, 'time_gap (day)': o.time_gap_days };
}
const RES_TYPE = { equipment: 'Equipment', crew: 'Crew', materials: 'Materials' };
function guessCategory(r) {
  const t = `${r.name} ${r.notes || ''}`;
  const m = t.match(/Category: ([^.]+)\./);
  if (m && CATEGORIES[m[1]]) return m[1];
  return /bucket/i.test(t) ? 'Bucket trucks' : /digger|derrick/i.test(t) ? 'Digger derricks' : /crane/i.test(t) ? 'Cranes' : /excavator/i.test(t) ? 'Excavators' : /trench/i.test(t) ? 'Trenchers' : r.type === 'crew' || /lineworker|crew/i.test(t) ? 'Line crew' : r.type === 'materials' ? 'Materials' : 'Other';
}
function toResource(r) {
  return {
    id: r.id, _raw: r, category: guessCategory(r), name: r.name, quantity: r.quantity, date: r.date_label || '',
    start: r.available_from, end: r.available_to, place: r.location?.label || '', rate: r.daily_rate || 0,
    type: RES_TYPE[r.type] || 'Equipment', owner: r.company_name || '', mine: r.company_id === COMPANY_ID, notes: r.notes || ''
  };
}
function toJob(j) {
  return {
    id: j.id, _raw: j, name: j.title, openings: j.openings, place: j.location?.label || '', lat: j.location?.lat, lon: j.location?.lon,
    pay: j.pay_label || 'Pay to confirm', dates: j.date_label || '', quals: j.qualifications || [], owner: j.company_name || '', status: j.status
  };
}
function toReservation(x) {
  return {
    id: x.resource_id, rid: x.id, name: x.resource_name, date: `${fmtDate(x.from)} – ${fmtDate(x.to)}`,
    project: byId[x.project_id]?.project_name || '', status: `${x.status} · ${x.quantity} requested`,
    incoming: x.owner_company_id === COMPANY_ID && x.requester_company_id !== COMPANY_ID, requester: x.requester_company_name, raw: x
  };
}
const companyName = id => (state.companies || []).find(c => c.id === id)?.name || 'Another company';

// ---- Loading ----
function setIdentity() {
  API.setIdentity(state.role === 'worker' ? { workerId: WORKER_ID } : { companyId: COMPANY_ID });
}
async function loadCore() {
  const [companies, ps, cross, user] = await Promise.all([
    API.get('/companies'), API.get('/projects'), API.get('/overlaps', { kind: 'cross_utility' }), API.get('/overlaps', { kind: 'user_project' }).catch(() => [])
  ]);
  state.companies = companies;
  projects.splice(0, projects.length, ...ps.map(toProject));
  Object.keys(byId).forEach(k => delete byId[k]);
  projects.forEach(p => { byId[p.project_id] = p; });
  overlaps.splice(0, overlaps.length, ...cross.map(toOverlap).filter(o => byId[o.project_id_a] && byId[o.project_id_b]));
  state.userOverlaps = user.map(toOverlap).filter(o => byId[o.project_id_a] && byId[o.project_id_b]);
  state.companyProjects = projects.filter(p => p.mine);
  const keepO = state.selectedOverlap && overlaps.find(o => o.overlap_id === state.selectedOverlap.overlap_id);
  state.selectedOverlap = keepO || overlaps[0] || null;
  const keepP = state.selectedProject && byId[state.selectedProject.project_id];
  state.selectedProject = keepP || byId[state.selectedOverlap?.project_id_a] || projects[0] || null;
}
async function loadMarket() {
  const [res, jobs] = await Promise.all([API.get('/resources'), API.get('/jobs')]);
  state.resources = res.map(toResource);
  state.jobs = jobs.map(toJob);
  if (!state.selectedJob || !state.jobs.find(j => j.id === state.selectedJob.id)) state.selectedJob = state.jobs[0] || null;
}
async function loadRoleData() {
  setIdentity();
  if (state.role === 'worker') {
    const [saved, apps, me] = await Promise.all([API.get('/saved-jobs').catch(() => []), API.get('/applications').catch(() => []), API.get('/me').catch(() => null)]);
    state.savedJobs = saved.map(j => j.id);
    state.applications = apps.map(a => ({ name: a.job_title, place: state.jobs.find(j => j.id === a.job_id)?.place || '', date: fmtDate(String(a.created_at).slice(0, 10)), status: a.status }));
    state.me = me?.worker || null;
  } else {
    const [rsv, myJobs, sugg] = await Promise.all([API.get('/reservations').catch(() => []), API.get('/jobs', { status: 'all' }).catch(() => []),
      API.get('/resources/suggested', state.myFocus ? { project_id: state.myFocus } : undefined).catch(() => null)]);
    state.reservations = rsv.map(toReservation);
    state.suggested = sugg; state.suggestedFor = sugg?.project_id || null;
    state.myJobs = myJobs.filter(j => j.company_id === COMPANY_ID).map(toJob);
  }
}
async function boot() {
  state.loaded = false; state.loadError = ''; render();
  try {
    setIdentity();
    await loadCore();
    await loadMarket();
    await loadRoleData();
    state.loaded = true;
  } catch (e) {
    state.loadError = e.message;
  }
  render();
  fitMapToProjects();
}
function fitMapToProjects() {
  const map = window.gridlockMap;
  if (!map || !window.google) return;
  const b = new google.maps.LatLngBounds();
  projects.filter(hasXY).forEach(p => b.extend({ lat: p.lat_center, lng: p.lon_center }));
  if (!b.isEmpty()) map.fitBounds(b, { top: 120, left: 220, right: 60, bottom: 120 });
}
window.addEventListener('gridlock-map-ready', fitMapToProjects);
async function refresh(parts = ['core', 'market', 'role']) {
  try {
    if (parts.includes('core')) await loadCore();
    if (parts.includes('market')) await loadMarket();
    if (parts.includes('role')) await loadRoleData();
  } catch (e) { toast(e.message); return; }
  render();
}
async function onRoleChange() {
  setIdentity();
  try { await loadRoleData(); } catch (e) { toast(e.message); }
  render();
}

// ---- Contract upload ----
async function analyzeContract(file) {
  state.projectUpload = { name: file.name, status: 'Reading the contract with Gridlock AI…', draft: {} }; render();
  try {
    const fd = new FormData(); fd.append('file', file);
    const r = await fetch(API.base + '/contracts/analyze', { method: 'POST', body: fd, headers: { 'X-Company-Id': COMPANY_ID } });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data?.error?.message || `Could not read the contract (${r.status})`);
    const f = data.fields || {}, v = k => { const x = f[k]?.value; return Array.isArray(x) ? x.map(i => typeof i === 'object' ? (i.name || i.type || JSON.stringify(i)) : i).join('; ') : (x ?? ''); };
    const draft = { project_name: v('project_name'), utility: v('owner_company') || v('utility'), location: v('location_text') || v('endpoints'), start_date: v('start_date'), end_date: v('end_date'), description: v('work_type'), roads: v('roads_affected'), contact: '' };
    const missing = (data.missing || []).length ? `Not found in the contract: ${data.missing.join(', ')}.` : '';
    state.projectUpload = { name: file.name, status: 'Read successfully · review the fields', parsed: true, draft, original: { ...draft }, contractId: data.contract_id, note: [missing, ...(data.follow_up_questions || [])].filter(Boolean).join(' ') };
    render();
    await refreshTiming();
    return;
  } catch (e) {
    // Backend unavailable: fall back to reading the PDF in the browser; the project is then saved with POST /projects.
    try {
      const draft = await parseProjectPdf(file);
      state.projectUpload = { name: file.name, status: 'Read in the browser (Gridlock AI unavailable)', parsed: true, draft, error: e.message };
    } catch (e2) {
      state.projectUpload = { name: file.name, status: 'Could not read the PDF', error: e2.message, draft: {} };
    }
  }
  render();
}
const CONTRACT_FIELD = { project_name: 'project_name', utility: 'owner_company', location: 'location_text', start_date: 'start_date', end_date: 'end_date', description: 'work_type', roads: 'roads_affected' };
// Fields the user changed after the contract was read, in the backend's field names.
function contractEdits(up) {
  const d = up.draft || {}, fields = {};
  Object.entries(CONTRACT_FIELD).forEach(([k, f]) => { if ((d[k] || '') !== (up.original?.[k] || '')) fields[f] = d[k] || null; });
  return fields;
}
// Best time to work + coordination matches for the uploaded contract, without saving it.
async function refreshTiming() {
  const up = state.projectUpload; if (!up?.contractId) return;
  up.timingLoading = true; up.timingError = ''; render();
  try {
    const m = await API.post(`/contracts/${up.contractId}/match`, { fields: contractEdits(up) });
    if (state.projectUpload !== up) return; // a different file was uploaded meanwhile
    Object.assign(up, { match: m, timing: m.work_timing, summary: m.summary, stale: false });
  } catch (e) {
    up.timing = null;
    up.timingError = /end date|in-service/i.test(e.message) ? 'Add an end date (completion or in-service date) to get a suggestion.' : e.message;
  }
  up.timingLoading = false; render();
}
async function publishProject() {
  const up = state.projectUpload, d = up?.draft || {};
  if (!up) { toast('Upload a contract PDF first.'); return; }
  if (up.saving) return;
  up.saving = true; up.saveError = ''; render();
  try {
    let project, match = null, already = false;
    if (up.contractId) {
      // Save uses the last reviewed fields: re-run the match only if details changed since the suggestion.
      match = up.match && !up.stale ? up.match : await API.post(`/contracts/${up.contractId}/match`, { fields: contractEdits(up) });
      const saved = await API.post(`/contracts/${up.contractId}/save`, {});
      project = saved.project; already = !!saved.already_saved;
    } else {
      const r = await API.post('/projects', { name: d.project_name || up.name.replace(/\.pdf$/i, ''), description: d.description || undefined, location_text: d.location, start_date: d.start_date || undefined, end_date: d.end_date });
      project = r.project || r;
    }
    await loadCore();
    state.contractResults = state.contractResults || {};
    if (match) state.contractResults[project.id] = match;
    state.selectedProject = byId[project.id] || toProject(project);
    state.projectUpload = null;
    // Go to the map, zoomed to the saved project, with its coordination partners.
    if (byId[project.id]) focusMyProject(project.id); else state.page = 'projectDetail';
    toast(already ? 'This contract was already saved, so your existing project is shown.' : 'Project saved. Your coordination partners are listed on the left.');
  } catch (e) {
    up.saving = false; up.saveError = e.message; render(); toast('Could not save: ' + e.message);
  }
}

// ---- Suggested inventory: for the project selected on the map, else for all your projects ----
async function loadSuggestions(pid) {
  try {
    const s = await API.get('/resources/suggested', pid ? { project_id: pid } : undefined);
    if ((pid || null) !== (state.myFocus || null)) return; // selection changed while loading
    state.suggested = s; state.suggestedFor = pid || null;
  } catch (e) { /* keep the previous suggestions */ }
  render();
}

// ---- Predicted congestion around your project ----
async function loadCongestion(id, force = false) {
  state.congestion = state.congestion || {};
  if (state.congestion[id] && !force) return;
  try {
    state.congestion[id] = await API.get(`/projects/${id}/congestion`);
    // The congestion popup takes over from the project's info card on the map.
    if (state.myFocus === id && !state.pairFocus) state.hoverClosed = true;
  } catch (e) {
    state.congestion[id] = { error: 'Could not predict congestion: ' + e.message, roads: [] };
  }
  render();
}

// ---- Views that use backend numbers ----
function overlapSavings(o) {
  const ce = o?.cost_estimate || {};
  return { point: ce.total_estimated_savings_usd || 0, range: ce.range_usd };
}
function projectOverlaps(pid) {
  return [...overlaps, ...(state.userOverlaps || [])].filter(o => o.project_id_a === pid || o.project_id_b === pid)
    .sort((a, b) => (b.score || 0) - (a.score || 0));
}
function partnerOf(o, pid) { return byId[o.project_id_a === pid ? o.project_id_b : o.project_id_a]; }

// ---- Actions (return true when handled here) ----
function apiAction(act) {
  if (act === 'retryLoad') { boot(); return true; }
  if (act === 'publish:project') { publishProject(); return true; }
  if (act === 'refreshTiming') { refreshTiming(); return true; }
  if (act === 'publish:resource') { publishResource(); return true; }
  if (act === 'publish:job') { publishJob(); return true; }
  if (act === 'placeOrder') { placeOrder(); return true; }
  if (act === 'apply') { applyJob(); return true; }
  if (act.startsWith('toggleSaveJob:')) { toggleSave(act.split(':')[1]); return true; }
  if (act === 'globalChat') { agentChat(); return true; }
  if (act.startsWith('agentConfirm:')) { agentDecide(act.split(':')[1], 'confirm'); return true; }
  if (act.startsWith('agentCancel:')) { agentDecide(act.split(':')[1], 'cancel'); return true; }
  if (act === 'closeAgent') { state.agent = null; render(); return true; }
  if (act === 'analyze') { analyzeFeasibility(); return true; }
  if (act === 'saveProfile') { saveProfile(); return true; }
  if (act === 'searchJobs') { searchJobs(); return true; }
  if (act.startsWith('rsv:')) { const [, id, status] = act.split(':'); updateReservation(id, status); return true; }
  return false;
}
async function publishResource() {
  const d = state.resourceDraft, miss = resourceMissing(d);
  if (miss.length) { toast('Add ' + miss.join(', ') + ' before publishing.'); return; }
  const notes = [`Category: ${d.category}.`, d.operator === 'Yes' ? 'Operators included.' : d.operator === 'No' ? 'No operators.' : '', d.notes || ''].filter(Boolean).join(' ');
  try {
    await API.post('/resources', {
      name: d.name || d.category, type: (CATEGORIES[d.category] || 'Equipment').toLowerCase(), quantity: Number(d.quantity) || 1,
      location_text: d.location, available_from: d.start, available_to: d.end || d.start, daily_rate: d.rate ? Number(d.rate) : null, notes
    });
    state.resourceDraft = {}; state.resourceChat = []; state.resourceModal = false; state.invFind = true; state.page = 'inventory';
    await loadMarket(); render(); toast('Listing published. Other contractors can now find it.');
  } catch (e) { toast(e.message); }
}
async function placeOrder() {
  const r = state.resources.find(x => x.id === state.invSelected); if (!r) return;
  if (r.mine) { toast('This is your own listing.'); return; }
  const q = Math.max(1, Number($('#orderQty')?.value) || 1);
  if (q > r.quantity) { toast(`Only ${r.quantity} available in this listing.`); return; }
  const from = state.invFrom || r.start, to = state.invTo || r.end;
  const pid = $('#orderProject')?.value || undefined;
  try {
    await API.post(`/resources/${r.id}/reservations`, { quantity: q, from, to, project_id: pid });
    await loadRoleData(); render(); toast('Order request sent. The owner still needs to accept it.');
  } catch (e) { toast(e.message); }
}
async function updateReservation(id, status) {
  try { await API.patch(`/reservations/${id}`, { status }); await refresh(['market', 'role']); toast(`Request ${status}.`); } catch (e) { toast(e.message); }
}
async function publishJob() {
  const d = state.jobDraft;
  if (!d.role) { toast('Add the role before publishing.'); return; }
  const dates = parseDateRange(d.dates);
  try {
    await API.post('/jobs', {
      title: d.role, openings: Number(d.openings) || 1, location_text: d.location || undefined, start_date: dates?.[0], end_date: dates?.[1],
      qualifications: String(d.requirements || '').split(/[,;]/).map(s => s.trim()).filter(Boolean)
    });
    state.jobDraft = {}; state.page = 'jobs'; await refresh(['market', 'role']); toast('Job posted. Workers can now apply.');
  } catch (e) { toast(e.message); }
}
function parseDateRange(text) {
  const iso = String(text || '').match(/\d{4}-\d{2}-\d{2}/g);
  if (iso?.length) return [iso[0], iso[1] || iso[0]];
  const m = [...String(text || '').matchAll(/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(\d{1,2})?(?:,?\s*(\d{4}))?/gi)];
  if (!m.length) return null;
  const year = (String(text).match(/\b(20\d\d)\b/) || [])[1] || String(new Date().getFullYear() + 1);
  const one = (x, end) => { const mo = MONTHS[x[1].toLowerCase().slice(0, 3)]; const day = x[2] || (end ? new Date(Number(x[3] || year), mo, 0).getDate() : 1); return `${x[3] || year}-${String(mo).padStart(2, '0')}-${String(day).padStart(2, '0')}`; };
  return [one(m[0], false), one(m[m.length - 1], true)];
}
async function applyJob() {
  const j = state.selectedJob; if (!j) return;
  try {
    await API.post(`/jobs/${j.id}/applications`, { name: $('#applicantName')?.value, qualifications: $('#applicantSkills')?.value, availability: $('#applicantAvailability')?.value });
    await loadRoleData(); state.page = 'applications'; render(); toast('Application sent to ' + j.owner + '.');
  } catch (e) { toast(e.message); }
}
async function toggleSave(id) {
  const saved = state.savedJobs.includes(id);
  try {
    if (saved) await API.del(`/jobs/${id}/save`); else await API.post(`/jobs/${id}/save`, {});
    await loadRoleData(); render(); toast(saved ? 'Job removed from saved.' : 'Job saved.');
  } catch (e) { toast(e.message); }
}
async function searchJobs() {
  const q = $('#jobSearch')?.value.trim();
  try { state.jobs = (await API.get('/jobs', { q })).map(toJob); state.jobQuery = q; render(); } catch (e) { toast(e.message); }
}
async function saveProfile() {
  const v = id => $('#' + id)?.value.trim();
  try {
    await API.patch('/me', { trade: v('pfTrade'), certifications: String(v('pfCerts') || '').split(',').map(s => s.trim()).filter(Boolean), experience: v('pfExp'), availability: v('pfAvail') });
    await loadRoleData(); render(); toast('Profile saved.');
  } catch (e) { toast(e.message); }
}

// ---- Feasibility: nearby planned work, road traffic and the best time to work ----
async function analyzeFeasibility() {
  const p = state.proposed;
  if (!p.location || !p.start || !p.end) { toast('Add a location, start date and end date.'); return; }
  state.feas = { loading: true }; render();
  try {
    const w = await API.post('/whatif', { name: p.name || 'Proposed project', location_text: p.location, construction_window: { start: p.start, end: p.end }, lane_closures: Number(state.closure.lanes) || undefined, work_hours: state.closure.hours || undefined });
    let plan = null;
    const c = w.proposed?.center;
    if (c) plan = await API.post('/traffic/plan', { point: { lat: c.lat, lon: c.lon } }).catch(() => null);
    state.feas = { result: w, plan };
  } catch (e) { state.feas = { error: e.message }; }
  render();
}

// ---- Gridlock assistant (bottom chat bar) ----
async function agentChat() {
  const input = $('#globalChat'), text = input?.value.trim(); if (!text) return;
  state.agent = { ...(state.agent || {}), question: text, loading: true, reply: '' }; render();
  try {
    const r = await API.post('/agent/chat', { message: text, thread_id: state.agent.threadId, context: { page: state.page, overlap_id: state.selectedOverlap?.overlap_id, project_id: state.selectedProject?.project_id } });
    state.agent = { threadId: r.thread_id, question: text, reply: r.reply, pending: r.pending_actions || [] };
    if (r.intent?.page && r.intent.action === 'navigate') state.page = r.intent.page;
  } catch (e) { state.agent = { ...(state.agent || {}), loading: false, reply: e.message }; }
  render();
}
async function agentDecide(id, how) {
  try {
    const r = await API.post(`/agent/actions/${id}/${how}`, {});
    state.agent = { ...state.agent, pending: (state.agent.pending || []).filter(p => p.id !== id), reply: r.message || r.reply || (how === 'confirm' ? 'Done.' : 'Cancelled.') };
    if (how === 'confirm') await refresh();
    else render();
  } catch (e) { toast(e.message); }
}
function agentPanel() {
  const a = state.agent; if (!a) return '';
  const pend = (a.pending || []).map(p => `<div class="item"><p>${esc(p.summary || p.description || p.tool || 'Pending action')}</p><div class="row wrap">${btn('Confirm', 'agentConfirm:' + p.id, 'primary')}${btn('Cancel', 'agentCancel:' + p.id)}</div></div>`).join('');
  return `<div class="card agent-panel" style="position:fixed;left:50%;transform:translateX(-50%);bottom:84px;z-index:25;width:min(640px,calc(100vw - 32px));max-height:50vh;overflow:auto"><button class="close-x" data-action="closeAgent" aria-label="Close" title="Close">×</button><p class="tiny">You asked: ${esc(a.question || '')}</p><div class="bubble">${a.loading ? 'Thinking…' : esc(a.reply || '')}</div>${pend}</div>`;
}

boot();
