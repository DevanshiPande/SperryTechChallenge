const source = window.GRIDLOCK_CHALLENGE;
const projects = source.projects;
const overlaps = source.overlaps;
const byId = Object.fromEntries(projects.map(p => [p.project_id, p]));
const demoResources = [
  { id: 'R1', name: 'Bucket trucks with operators', quantity: 2, date: 'Jun 3–10, 2027', place: 'Savannah yard', rate: 1250, type: 'Equipment', owner: 'Demo Contractor B' },
  { id: 'R2', name: '60-ton crane', quantity: 1, date: 'Jun 12–18, 2027', place: 'Pooler, GA', rate: 2100, type: 'Equipment', owner: 'Coastal Crane (demo)' },
  { id: 'R3', name: 'Certified lineworkers', quantity: 5, date: 'Jul 1–20, 2027', place: 'Savannah, GA', rate: 0, type: 'Crew', owner: 'Line Crews Co. (demo)' }
];
const demoJobs = [
  { id: 'J1', name: 'Transmission lineworker', openings: 5, place: 'Savannah, GA', lat: 32.0809, lon: -81.0912, pay: '$34–$42/hr', dates: 'Dec 2026–Mar 2027', quals: ['OSHA 30', 'CDL Class A', 'Aerial lift'], owner: 'Southeast Power Co. (demo)' },
  { id: 'J2', name: 'Substation electrician', openings: 4, place: 'Okatie, SC', lat: 32.3363, lon: -80.9387, pay: '$32–$38/hr', dates: 'Jan–Apr 2027', quals: ['NFPA 70E', 'Substation experience'], owner: 'Coastal Grid Solutions (demo)' },
  { id: 'J3', name: 'Bucket truck operator', openings: 2, place: 'Savannah, GA', lat: 32.1286, lon: -81.2073, pay: '$30–$36/hr', dates: 'Jun–Aug 2027', quals: ['CDL', 'Aerial lift'], owner: 'Demo Contractor A' }
];
const state = {
  role: 'contractor', page: 'map', selectedOverlap: overlaps[1], selectedProject: projects[2], selectedJob: demoJobs[0],
  hoverProject: null, hoverClosed: true, pairClosed: true, pairFocus: false, chat: [], chatMode: null, draft: {}, resourceDraft: {}, resourceModal: false, resourceManual: false, resourceChat: [], jobDraft: {},
  resources: [...demoResources], jobs: [...demoJobs], reservations: [], applications: [],
  cost: { mobilization: 3000, truckRate: 1300, separateDays: 20, coordinatedDays: 12, yard: 5000 },
  closure: { lanes: 1, start: '2027-06-01', end: '2027-12-15', hours: '21:00–05:00' },
  proposed: { name: 'Savannah corridor upgrade', location: 'Near Hardeeville, SC', start: '2027-06-01', end: '2027-12-15' },
  toast: ''
};
const $ = q => document.querySelector(q);
const esc = s => String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const btn = (label, action, cls = 'secondary') => `<button class="${cls}" data-action="${action}">${label}</button>`;
const pill = (label, cls = '') => `<span class="pill ${cls}">${esc(label)}</span>`;
const demo = '<span class="demo">DEMO DATA</span>';
function nav() {
  const items = state.role === 'contractor' ? [
    ['map','◫','Explore map'],['opportunities','≡','Opportunities'],['feasibility','△','Feasibility'],['cost','▥','Cost comparison'],['projects','▣','My projects'],['inventory','♧','Inventory'],['messages','▤','Messages']
  ] : [['findjobs','⌕','Find jobs'],['saved','♡','Saved'],['applications','▤','Applications'],['workerprofile','♙','Profile']];
  return `<aside class="sidebar"><div class="brand"><span>G</span>Gridlock</div><div class="role">${state.role === 'contractor' ? 'CONTRACT MANAGEMENT COMPANY' : 'PROSPECTIVE WORKER'}</div>${items.map(([id,icon,name]) => `<button class="nav ${state.page === id ? 'active' : ''}" data-page="${id}"><span class="icon">${icon}</span>${name}</button>`).join('')}<div class="sidefoot">Design prototype<br>Public plan fields and illustrative data are labeled separately.</div></aside>`;
}
function topbar() {
  return `<header class="topbar"><div class="top-title">Utility project coordination</div><div class="top-search"><input id="topSearch" placeholder="Search projects, resources, or jobs" aria-label="Search"></div><div class="segmented" role="group" aria-label="Role"><button class="switch ${state.role==='contractor'?'active':''}" data-role="contractor">Contractor</button><button class="switch ${state.role==='worker'?'active':''}" data-role="worker">Worker</button></div>${state.role==='contractor'?btn('+ Describe project','addProject','primary'):btn('Find jobs','findjobs','primary')}</header>`;
}
const head = (title, subtitle, action = '') => `<div class="heading"><div><h1>${title}</h1><p class="sub">${subtitle}</p></div>${action}</div>`;
function projectLine(p) { return `${esc(p.project_name)} <span class="tiny">${esc(p.utility)}</span>`; }
function mapHtml({small=false, hover=true, pair=true, jobs=false}={}) {
  const valid = projects.filter(p => Number.isFinite(p.lat_center) && Number.isFinite(p.lon_center));
  const x = lon => 8 + (lon + 82.3) / 1.65 * 84;
  const y = lat => 91 - (lat - 31.8) / 2.15 * 82;
  const markers = jobs ? demoJobs.map((j,i) => `<button title="${esc(j.name)}" class="pin ${i?'gpc':'desc'} ${state.selectedJob.id===j.id?'selected':''}" style="left:${42+i*13}%;top:${38+i*16}%" data-job="${j.id}"></button>`).join('') : valid.map(p => `<button title="${esc(p.project_name)}" class="pin ${p.utility.includes('Dominion')?'desc':'gpc'} ${selectedPinIds().includes(p.project_id)?'selected':''}" style="left:${Math.max(4,Math.min(96,x(p.lon_center)))}%;top:${Math.max(4,Math.min(96,y(p.lat_center)))}%" data-project="${p.project_id}"></button>`).join('');
  const hv = state.hoverProject || state.selectedProject;
  const closeX='<button class="close-x" data-action="closeHover" aria-label="Close" title="Close">×</button>';
  const projectCard=(p,place='')=>`<div class="hovercard" data-anchor="${p.project_id}" data-place="${place}">${closeX}<div class="row wrap">${pill(p.utility.includes('Dominion')?'Dominion Energy SC':'Georgia Power',p.utility.includes('Dominion')?'':'amber')}</div><h3>${esc(p.project_name)}</h3><p>In-service: ${String(p.in_service_date).slice(0,10)} · ${p.state}. Inventory and closure details are not in the public filing.</p>${btn('View full project','selectProject:'+p.project_id,'primary')}</div>`;
  let hcard='';
  if(hover&&!state.hoverClosed){
    if(jobs){const j=state.selectedJob;hcard=`<div class="hovercard" data-anchor="${j.id}">${closeX}<div class="row wrap">${pill('Job preview','amber')}</div><h3>${esc(j.name)}</h3><p>${j.openings} openings · ${esc(j.place)} · ${esc(j.pay)}</p>${btn('View job details','jobDetail','primary')}</div>`}
    else if(state.pairFocus){
      // One card per project in the selected pair: the northern one above its pin, the southern one below.
      const pair=pairProjects().filter(hasXY).sort((x,y)=>y.lat_center-x.lat_center);
      hcard=pair.map((p,i)=>projectCard(p,pair.length>1?(i?'below':'above'):'')).join('');
    }
    else hcard=projectCard(hv);
  }
  return `<div class="map ${small?'mini-map':''}"><svg viewBox="0 0 1000 700" preserveAspectRatio="none" aria-hidden="true"><rect width="1000" height="700" fill="#e4f1e9"/><path d="M450 0 C510 170 410 300 510 440 S500 630 580 700" stroke="#98c9dc" stroke-width="55" fill="none"/><path d="M450 0 C510 170 410 300 510 440 S500 630 580 700" stroke="#bbdfea" stroke-width="33" fill="none"/><g stroke="#fff" stroke-width="7" opacity=".85"><path d="M0 85L1000 190M0 275L1000 330M0 530L1000 480M120 0L260 700M770 0L630 700M960 0L830 700"/></g><path d="M210 60L460 640" stroke="#d3a95a" stroke-width="6" fill="none"/><text x="130" y="68" fill="#667f86" font-size="20">GEORGIA</text><text x="685" y="68" fill="#667f86" font-size="20">SOUTH CAROLINA</text><text x="416" y="445" fill="#237d9c" font-size="18" transform="rotate(-76 416 445)">SAVANNAH RIVER</text><text x="175" y="540" fill="#315a6d" font-size="25">Savannah</text><text x="610" y="264" fill="#315a6d" font-size="19">Okatie</text></svg>${markers}<div class="map-label">${jobs?'Job locations':window.gridlockMapLive?'Project locations · Google Maps':'Project locations · schematic map'}</div><div class="map-legend"><span class="dot desc"></span>${jobs?'Selected job':'Dominion Energy SC'}<br><span class="dot gpc"></span>${jobs?'Other jobs':'Georgia Power'}<br>Click a pin for details</div>${hcard}</div>`;
}
const hasXY=p=>Number.isFinite(p?.lat_center)&&Number.isFinite(p?.lon_center);
const pairProjects=()=>[byId[state.selectedOverlap.project_id_a],byId[state.selectedOverlap.project_id_b]].filter(Boolean);
const selectedPinIds=()=>state.pairFocus?pairProjects().map(p=>p.project_id):[state.selectedProject.project_id];
function opportunityButton(o) {
  const selected = state.selectedOverlap.overlap_id === o.overlap_id;
  return `<button class="opportunity ${selected?'selected':''}" data-overlap="${o.overlap_id}"><strong>${esc(byId[o.project_id_a]?.project_name.split(':')[0])} ↔ ${esc(byId[o.project_id_b]?.project_name.split(':')[0])}</strong><span class="muted">Dominion Energy SC ↔ Georgia Power</span><div class="stats"><span><b>${o.distance_mi} mi</b>center-point distance</span><span><b>${Number(o['time_gap (day)']).toLocaleString()} days</b>in-service date gap</span></div></button>`;
}
function pairPanel() {
  if(state.pairClosed && state.page==='map') return '<div></div>';
  const o=state.selectedOverlap, a=byId[o.project_id_a], b=byId[o.project_id_b];
  return `<div class="card stack closable"><button class="close-x" data-action="closePair" aria-label="Close" title="Close">×</button><div>${pill('Potential coordination','coral')}</div><h2>${esc(a.project_name.split(':')[0])} ↔ ${esc(b.project_name.split(':')[0])}</h2><div class="row wrap">${pill('Dominion SC')}${pill('Georgia Power','amber')}</div><hr class="divider"><div class="metric-grid"><div><strong>${o.distance_mi} mi</strong><div class="tiny">starter workbook center distance</div></div><div><strong>${Number(o['time_gap (day)']).toLocaleString()} days</strong><div class="tiny">in-service date gap</div></div></div><div class="timeline"></div><div class="note">These projects are geographically near. Their construction windows and shared-resource feasibility still need confirmation.</div><div class="card" style="background:#fff5f2"><div class="muted">Illustrative coordination scenario</div><div class="metric green">$15,400</div><div class="tiny">Based on editable rates and quantities; not verified savings.</div></div><div class="row wrap">${btn('Compare costs','cost','primary')}${btn('Check feasibility','feasibility','secondary')}${btn('Discuss resources','messages','secondary')}</div></div>`;
}
function mapPage() {
  const list=state.oppsClosed
    ? `<div><button class="reopen-chip" data-action="openOpps">≡ Coordination opportunities <span>${overlaps.length}</span></button></div>`
    : `<div class="card closable"><button class="close-x" data-action="closeOpps" aria-label="Close" title="Close">×</button><h2>Coordination opportunities</h2><p class="muted">${overlaps.length} candidate pairs · distance first</p>${overlaps.map(opportunityButton).join('')}</div>`;
  return `<div class="grid three">${list}${mapHtml()}${pairPanel()}</div>`;
}
function opportunityPage() {const o=state.selectedOverlap;return head('Coordination opportunity','Compare two planned projects and the evidence for their match.',btn('Open conversation','messages','primary'))+`<div class="grid two"><div class="stack">${mapHtml({hover:false})}<div class="card"><h2>Source and uncertainty</h2><p class="muted">The starter workbook links these project names to the supplied Dominion and Georgia Power planning PDFs. Coordinates are approximate. Dates are in-service targets, not construction windows.</p><div class="row wrap">${btn('Check feasibility','feasibility')}${btn('Compare costs','cost')}</div></div></div>${pairPanel()}</div>`;}
function feasibilityPage() {return head('Check project feasibility','Contractor-led review of nearby work and a proposed closure.',btn('Describe a new project','addProject','primary'))+`<div class="grid three"><div class="card"><h2>Proposed work</h2><p class="muted">Editable demo scenario</p>${[['Project name','name'],['Location','location'],['Start date','start'],['End date','end']].map(([l,k])=>`<div class="fieldgroup"><label>${l}</label><input class="field" data-proposed="${k}" value="${esc(state.proposed[k])}" type="${k==='start'||k==='end'?'date':'text'}"></div>`).join('')}<div class="formgrid"><div class="fieldgroup"><label>Closed lanes</label><input class="field" type="number" min="0" max="4" data-closure="lanes" value="${state.closure.lanes}"></div><div class="fieldgroup"><label>Work hours</label><input class="field" data-closure="hours" value="${esc(state.closure.hours)}"></div></div>${btn('Analyze scenario','analyze','primary accent')}</div>${mapHtml({hover:false})}<div class="card stack"><h2>Feasibility review</h2><div class="item"><h3>Existing work nearby</h3><p class="muted">Projects in the starter workbook appear within the selected 25-mile planning radius.</p></div><div class="item"><h3>Closure conflict</h3><p class="muted">Requires road segment and permit data. The sample closure is illustrative.</p></div><div class="item"><h3>Historical traffic</h3><p class="muted">No traffic history was included in the challenge files. Add a source before estimating congestion.</p><div class="bar amber" style="width:65%">Illustrative peak baseline</div><div class="bar" style="width:82%">Illustrative closure scenario</div></div><div class="note">Possible alternative: test nighttime work. This is a scenario for review, not a feasibility decision.</div>${btn('Compare cost impact','cost')}</div></div>`;}
function costTotals(){const c=state.cost;return {separate:2*c.mobilization+c.separateDays*c.truckRate+2*c.yard,coordinated:2*c.mobilization+c.coordinatedDays*c.truckRate+c.yard};}
function costPage(){const c=state.cost,t=costTotals(),save=t.separate-t.coordinated,pct=t.separate?Math.round(save/t.separate*1000)/10:0;return head('Estimate the value of coordination','Compare separate work with a shared-resource scenario. All inputs are illustrative.',btn('Share scenario in conversation','messages','primary'))+`<div class="grid two"><div class="stack"><div class="card"><h2>Two projects on the map</h2><p class="muted">${esc(byId[state.selectedOverlap.project_id_a].project_name)} ↔ ${esc(byId[state.selectedOverlap.project_id_b].project_name)}</p>${mapHtml({small:true,hover:false})}</div><div class="grid two"><div class="card"><h2>Separate work</h2><p class="muted">Two mobilizations · ${c.separateDays} truck-days · two yards</p><div class="metric">$${t.separate.toLocaleString()}</div></div><div class="card"><h2>Coordinated work</h2><p class="muted">Two mobilizations · ${c.coordinatedDays} truck-days · one yard</p><div class="metric green">$${t.coordinated.toLocaleString()}</div></div></div></div><div class="card stack"><div>${pill('Illustrative estimate','amber')}</div><h2>Edit assumptions</h2>${[['Mobilization per event','mobilization'],['Truck rate per day','truckRate'],['Separate truck-days','separateDays'],['Coordinated truck-days','coordinatedDays'],['Yard cost per site','yard']].map(([l,k])=>`<div class="statusline"><label class="muted" for="cost-${k}">${l}</label><input id="cost-${k}" class="field" style="max-width:145px" type="number" min="0" data-cost="${k}" value="${c[k]}"></div>`).join('')}<hr class="divider"><div class="calcout">$${save.toLocaleString()}</div><strong>${pct}% potential reduction</strong><div class="warning">In-service dates do not prove construction overlap. Actual rates, logistics, and schedules must be verified before treating this as savings.</div><div class="tiny">Separate = 2 × mobilization + separate truck-days × rate + 2 × yard. Coordinated = 2 × mobilization + coordinated truck-days × rate + 1 × yard.</div></div></div>`;}
function projectsPage(){return head('My projects','Imported public plans and contractor-authored drafts.',btn('+ Describe project','addProject','primary'))+`<div class="grid two"><div class="card"><h2>Project portfolio</h2>${projects.map(p=>`<div class="item"><div class="statusline"><div><h3>${esc(p.project_name)}</h3><div class="muted">${esc(p.utility)} · ${esc(p.state)} · in-service ${String(p.in_service_date).slice(0,10)}</div></div>${pill('Imported plan','amber')}</div><div class="action">${btn('View project','selectProject:'+p.project_id)}</div></div>`).join('')}</div>${mapHtml({hover:false})}</div>`;}
function projectDetailPage(){const p=state.selectedProject;return head(esc(p.project_name),'Project record from the supplied starter workbook.',btn('Back to map','map'))+`<div class="grid two"><div class="stack">${mapHtml({hover:false})}<div class="card"><h2>Project evidence</h2><p>Utility: ${esc(p.utility)} · ${esc(p.state)}</p><p>In-service target: ${esc(String(p.in_service_date).slice(0,10))}</p><p class="muted">Named endpoints: ${esc(p.name_a)} and ${esc(p.name_b)}. Some endpoint coordinates in the starter workbook are missing; the map is schematic.</p></div></div><div class="card stack"><h2>Coordination context</h2>${pill('Public-plan data')}<div class="item"><h3>Nearby matches: ${p.overlap_count}</h3><p class="muted">Review distance and timing on the Opportunities page.</p>${btn('View matches','opportunities')}</div><div class="item"><h3>Available inventory</h3><p class="muted">Not listed in the public filing. Demo marketplace resources are separate.</p>${btn('Open inventory','inventory')}</div><div class="item"><h3>Road access</h3><p class="muted">Closure and traffic history were not included in the public project record.</p>${btn('Check feasibility','feasibility')}</div></div></div>`;}
function chatPage(kind,manual=false){
  const resource=kind==='resource', job=kind==='job';
  const title=resource?'Describe an available resource':job?'Describe a job requirement':'Describe a new project';
  const draft=resource?state.resourceDraft:job?state.jobDraft:state.draft;
  const question=resource?'Tell me what equipment or crew you can share, how many, when, and where.':job?'What role, headcount, project, dates, and qualifications do you need?':'Tell me the planned work, location, dates, and any affected roads.';
  const hints=resource?['Two bucket trucks near Savannah June 3–10 at $1,250 each','Five lineworkers free next month']:job?['We need five certified lineworkers near Savannah in December','Post two bucket truck operator openings']:['A corridor upgrade near Hardeeville June to December 2027','A substation upgrade near Savannah next year'];
  const fields=resource?['name','quantity','location','dates','rate']:job?['role','openings','project','dates','requirements']:['name','location','start','end','closure'];
  const labels={name:'Name',quantity:'Quantity',location:'Location',dates:'Dates',rate:'Daily rate',role:'Role',openings:'Openings',project:'Linked project',requirements:'Requirements',start:'Start date',end:'End date',closure:'Road closure'};
  return head(title,manual?'Manual entry is an alternative. You can return to chat anytime.':'Chat creates a reviewable draft. Nothing is published automatically.',btn(manual?'Use chat instead':'Use manual form',manual?'chat:'+kind:'manual:'+kind))+`<div class="page-chat"><div class="card conversation"><h2>${manual?'Manual details':'✦ Ask Gridlock'}</h2><p class="muted">${manual?'Fill the fields and review the result.':question}</p>${manual?`<div class="formgrid">${fields.map(k=>`<div class="fieldgroup"><label>${labels[k]}</label><input class="field" data-draft="${k}" data-kind="${kind}" value="${esc(draft[k]||'')}" placeholder="${labels[k]}"></div>`).join('')}</div>`:`<div class="bubbles"><div class="bubble">${question}</div>${state.chatMode===kind?state.chat.map(m=>`<div class="bubble ${m.by==='user'?'user':''}">${esc(m.text)}</div>`).join(''):''}</div><div class="chat-entry"><input class="field" id="chatText" placeholder="Describe it in your own words"><button class="primary" data-action="sendChat:${kind}">Send</button></div><div class="row wrap" style="margin-top:12px">${hints.map(h=>`<button class="ghostlink" data-suggest="${esc(h)}">${esc(h)}</button>`).join('')}</div>`}</div><div class="stack"><div class="card"><div class="statusline"><h2>Editable draft</h2>${pill('Not published','amber')}</div><p class="muted">Review every extracted field before sharing it.</p>${fields.map(k=>`<div class="fieldgroup"><label>${labels[k]}</label><input class="field" data-draft="${k}" data-kind="${kind}" value="${esc(draft[k]||'')}" placeholder="Not provided yet"></div>`).join('')}<div class="row wrap">${btn('Review and publish','publish:'+kind,'primary accent')}${btn('Use manual form','manual:'+kind)}</div></div><div class="note">AI extraction is mocked locally. A real Gemini connection should return structured fields, cite source input, and require the same review step.</div></div></div>`;
}

// ---- Inventory: resource listing pop-up (chat on the left, structured listing on the right) ----
const PLACES = {
  'Savannah, GA': [32.0809, -81.0912], 'Pooler, GA': [32.1155, -81.2471], 'Hardeeville, SC': [32.2871, -81.0790],
  'Okatie, SC': [32.3363, -80.9387], 'Jesup, GA': [31.6074, -81.8854], 'Augusta, GA': [33.4735, -82.0105],
  'Charleston, SC': [32.7765, -79.9311]
};
const CATEGORIES = { 'Bucket trucks': 'Equipment', 'Digger derricks': 'Equipment', 'Cranes': 'Equipment', 'Excavators': 'Equipment', 'Line crew': 'Crew', 'Materials': 'Materials', 'Other': 'Equipment' };
const RADII = [10, 25, 50, 100];
const MONTHS = { jan:1, feb:2, mar:3, apr:4, may:5, jun:6, jul:7, aug:8, sep:9, oct:10, nov:11, dec:12 };
function milesBetween([lat1, lon1], [lat2, lon2]) {
  const r = d => d * Math.PI / 180, a = Math.sin(r(lat2 - lat1) / 2) ** 2 + Math.cos(r(lat1)) * Math.cos(r(lat2)) * Math.sin(r(lon2 - lon1) / 2) ** 2;
  return 3958.8 * 2 * Math.asin(Math.sqrt(a));
}
function nearbyDemand(d) {
  const at = PLACES[d.location]; if (!at) return [];
  return projects.filter(p => Number.isFinite(p.lat_center) && Number.isFinite(p.lon_center))
    .map(p => ({ p, mi: milesBetween(at, [p.lat_center, p.lon_center]) }))
    .filter(x => x.mi <= (d.radius || 25)).sort((a, b) => a.mi - b.mi);
}
const fmtDate = iso => iso ? new Date(iso + 'T00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
// Project names look like "Name: work type" or "SAV: NAME"; keep the part that identifies the line.
const shortName = n => { const [a, ...b] = n.split(':'); return a.trim().length <= 4 && b.length ? b.join(':').trim() : a.trim(); };
function resourceMissing(d) {
  return [['category', 'the type of equipment or crew'], ['quantity', 'how many'], ['start', 'the dates'], ['location', 'the pickup area'], ['rate', 'the daily rate'], ['operator', 'whether operators are included']]
    .filter(([k]) => !d[k]).map(([, label]) => label);
}
function resourceIcon(category) {
  const truck = '<path d="M8 50h52V34H40l-6-10H8z" fill="#0d3554"/><path d="M60 50h14l6-10-8-6H60z" fill="#1199a9"/><path d="M22 24 46 6l4 4-22 16" stroke="#df9c17" stroke-width="4" fill="none"/><rect x="44" y="2" width="10" height="8" rx="2" fill="#df9c17"/><circle cx="22" cy="52" r="7" fill="#113a53" stroke="#fff" stroke-width="3"/><circle cx="66" cy="52" r="7" fill="#113a53" stroke="#fff" stroke-width="3"/>';
  const crew = '<circle cx="26" cy="22" r="10" fill="#1199a9"/><circle cx="56" cy="22" r="10" fill="#df9c17"/><path d="M8 58c0-12 8-20 18-20s18 8 18 20zM38 58c0-12 8-20 18-20s18 8 18 20z" fill="#0d3554"/><path d="M15 16h22M45 16h22" stroke="#df9c17" stroke-width="4"/>';
  const crate = '<rect x="12" y="14" width="56" height="40" rx="4" fill="#0d3554"/><path d="M12 28h56M40 14v40" stroke="#1199a9" stroke-width="4"/>';
  const svg = category === 'Line crew' ? crew : category === 'Materials' ? crate : truck;
  return `<svg viewBox="0 0 82 62" aria-hidden="true">${svg}</svg>`;
}
function selectField(key, options, value, placeholder) {
  return `<select class="field" data-rdraft="${key}"><option value="">${placeholder}</option>${options.map(o => `<option ${String(o) === String(value) ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
}
function resourceModal() {
  const d = state.resourceDraft, manual = state.resourceManual, matches = nearbyDemand(d), at = PLACES[d.location];
  const radius = d.radius || 25, updated = d.updated ? `Last updated ${d.updated}` : 'Not saved yet';
  const bubbles = [{ by: 'assistant', text: 'Tell me what equipment, crew, or materials you have available. I’ll help create a listing.' }, ...state.resourceChat]
    .map(m => `<div class="bubble ${m.by === 'user' ? 'user' : ''}">${esc(m.text)}<span class="time">${m.time || ''}</span></div>`).join('');
  const chat = manual ? '' : `<section class="rm-chat">
      <h2>✦ Ask Gridlock</h2>
      <div class="row wrap rm-hints">${['Two bucket trucks near Savannah June 3–10 at $1,250/day with operators', 'Five certified lineworkers in Pooler July 1–20', 'Offer materials'].map(h => `<button class="ghostlink" data-suggest="${esc(h)}">${esc(h)}</button>`).join('')}</div>
      <div class="bubbles" id="rmBubbles">${bubbles}</div>
      <div class="chat-entry"><input class="field" id="chatText" placeholder="Describe what you can share"><button class="primary rm-send" data-action="sendChat:resource" aria-label="Send">➤</button></div>
    </section>`;
  const demand = matches.map(({ p, mi }) => `<button class="rm-match" data-action="selectProject:${p.project_id}">
      <span class="rm-bars" aria-hidden="true"><i></i><i></i><i></i></span>
      <span><strong>${esc(shortName(p.project_name))}</strong><small>${esc(p.utility)}</small><small>${mi.toFixed(1)} mi · in-service ${esc(String(p.in_service_date).slice(0, 10))}</small></span><span class="chev">›</span></button>`).join('')
    || `<div class="note">${at ? `No planned projects within ${radius} mi.` : 'Choose a pickup area to see planned projects nearby.'}</div>`;
  return `<div class="rm-backdrop" data-action="closeResource"></div>
  <div class="rm-modal ${manual ? 'manual' : ''}" role="dialog" aria-modal="true" aria-label="Resource listing">
    <button class="close-x" data-action="closeResource" aria-label="Close" title="Close">×</button>
    ${chat}
    <section class="rm-listing">
      <div class="statusline"><span class="pill amber">▮ Draft (not published)</span><span class="tiny">${updated}</span></div>
      <h1>Resource listing</h1><p class="muted">Review and edit before publishing.</p>
      <div class="rm-box">
        <div class="rm-hero"><div class="rm-img">${resourceIcon(d.category)}</div><div><input class="rm-title" data-rdraft="name" value="${esc(d.name || '')}" placeholder="Listing title"><textarea class="rm-desc" data-rdraft="description" rows="2" placeholder="Short description">${esc(d.description || '')}</textarea></div></div>
        <div class="rm-grid">
          <label>Category${selectField('category', Object.keys(CATEGORIES), d.category, 'Select category')}</label>
          <label>Quantity<input class="field" type="number" min="1" data-rdraft="quantity" value="${esc(d.quantity || '')}" placeholder="0"></label>
          <label>Availability dates<span class="rm-dates"><input class="field" type="date" data-rdraft="start" value="${esc(d.start || '')}"><span>–</span><input class="field" type="date" data-rdraft="end" value="${esc(d.end || '')}"></span></label>
          <label><span>Daily rate <em>(per unit)</em></span><span class="rm-money"><input class="field" type="number" min="0" step="50" data-rdraft="rate" value="${esc(d.rate || '')}" placeholder="0"></span></label>
          <label>Pickup area${selectField('location', Object.keys(PLACES), d.location, 'Select area')}</label>
          <label>Operator included${selectField('operator', ['Yes', 'No'], d.operator, 'Select')}</label>
          <label class="wide">Requirements / notes<textarea class="field" rows="2" data-rdraft="notes" placeholder="Clearances, minimum days, restrictions">${esc(d.notes || '')}</textarea></label>
        </div>
      </div>
      <div class="rm-lower">
        <div><div class="statusline"><h3>Location</h3><select class="field rm-radius" data-rdraft="radius">${RADII.map(r => `<option value="${r}" ${r === radius ? 'selected' : ''}>Within ${r} mi</option>`).join('')}</select></div>
          <div class="rm-map" id="rmMap" data-lat="${at ? at[0] : ''}" data-lng="${at ? at[1] : ''}" data-radius="${radius}">${at ? `<div class="rm-map-fallback"><span class="ring"></span><span class="dot"></span><b>${esc(d.location.split(',')[0])}</b></div>` : '<div class="rm-map-empty">No pickup area yet</div>'}</div>
        </div>
        <div><h3>Nearby demand ${matches.length ? `<span class="muted">(${matches.length} match${matches.length === 1 ? '' : 'es'})</span>` : ''}</h3>${demand}</div>
      </div>
      <div class="rm-actions">${btn('➤ Review and publish', 'publish:resource', 'primary')}${manual ? btn('✦ Use chat instead', 'resourceChatMode') : btn('☰ Use manual form instead', 'resourceManual')}</div>
    </section>
  </div>`;
}
function resourceFromText(text) {
  const d = state.resourceDraft, n = '(\\d+|two|three|four|five|six|seven|eight|nine|ten)';
  const words = { two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10 };
  const cat = /bucket/i.test(text) ? 'Bucket trucks' : /digger|derrick/i.test(text) ? 'Digger derricks' : /crane/i.test(text) ? 'Cranes' : /excavator/i.test(text) ? 'Excavators' : /lineworker|crew|workers?\b/i.test(text) ? 'Line crew' : /material|pole|conductor|wire|transformer/i.test(text) ? 'Materials' : '';
  if (cat) d.category = cat;
  const q = text.match(new RegExp(`\\b${n}\\s+(?:certified\\s+)?(?:bucket|truck|crane|digger|excavator|lineworker|worker|crew)`, 'i'));
  if (q) d.quantity = words[q[1].toLowerCase()] || Number(q[1]);
  const place = Object.keys(PLACES).find(k => new RegExp(k.split(',')[0], 'i').test(text));
  if (place) d.location = place;
  const dm = text.match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:\s*(?:–|-|to)\s*(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+)?(\d{1,2}))?/i);
  if (dm) {
    const iso = (m, day) => `2027-${String(MONTHS[m.toLowerCase().slice(0, 3)]).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    d.start = iso(dm[1], dm[2]); if (dm[4]) d.end = iso(dm[3] || dm[1], dm[4]);
  }
  const rate = text.match(/\$\s?([\d,]+)/); if (rate) d.rate = Number(rate[1].replace(/,/g, ''));
  if (/without operator|no operator|bare/i.test(text)) d.operator = 'No'; else if (/operator|with crew|crewed/i.test(text)) d.operator = 'Yes';
  const notes = [/clearance/i.test(text) && 'Valid utility clearance required.', /\bDOT\b/.test(text) && 'DOT compliant.', (text.match(/minimum\s+(\d+)\s+days?/i) || [])[1] && `Minimum ${text.match(/minimum\s+(\d+)\s+days?/i)[1]} days.`].filter(Boolean);
  if (notes.length) d.notes = notes.join(' ');
  if (d.category) {
    const plural = d.category.toLowerCase();
    d.name = d.category === 'Line crew' ? 'Certified line crew' : d.operator === 'Yes' ? `${d.category} with operators` : d.category;
    d.description = `${d.quantity ? (words[d.quantity] ? d.quantity : Object.keys(words).find(w => words[w] === Number(d.quantity)) || d.quantity) : 'Some'} ${d.category === 'Line crew' ? 'crew members' : plural} available${d.location ? ' near ' + d.location.split(',')[0] : ''}${d.operator === 'Yes' && d.category !== 'Line crew' ? ' with experienced operators' : ''}.`;
    d.description = d.description.charAt(0).toUpperCase() + d.description.slice(1);
  }
}
const clockTime = () => new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
function inventoryPage(){return head('Available resources','Find and offer equipment or crews near planned work.',btn('+ Describe resource','addResource','primary'))+`<div class="grid three"><div class="card"><h2>Search inventory</h2><p class="muted">Demo contractor listings</p><div class="fieldgroup"><label>Category</label><select class="field" id="resourceFilter"><option>All</option><option>Equipment</option><option>Crew</option></select></div><div class="fieldgroup"><label>Near</label><input class="field" value="Savannah, GA"></div>${btn('Apply filters','filterResource','primary accent')}<hr class="divider"><h3>My inventory</h3><p class="muted">Create a listing using chat, or open the manual form.</p>${btn('Describe what is free','addResource')}</div><div class="card"><h2>Resource listings ${demo}</h2>${state.resources.map(r=>`<div class="item"><div class="statusline"><h3>${esc(r.name)}</h3>${pill(r.type)}</div><p class="muted">${r.quantity} available · ${esc(r.date)} · ${esc(r.place)}</p><p class="muted">${esc(r.owner)} · ${r.rate?'$'+r.rate.toLocaleString()+'/day per unit':'Rate on request'}</p>${btn('Request reservation','reserve:'+r.id,'primary accent')}</div>`).join('')}</div><div class="card"><h2>Reservation requests</h2><p class="muted">Requests need owner acceptance; no payment occurs here.</p>${state.reservations.length?state.reservations.map(r=>`<div class="item"><strong>${esc(r.name)}</strong><p class="muted">${esc(r.date)} · ${esc(r.status)}</p></div>`).join(''):'<div class="note">No requests yet. Select a resource to create one.</div>'}<hr class="divider"><h3>Nearby coordination</h3><p class="muted">An overlap can prompt a conversation about a resource. Availability remains separate from proximity.</p>${btn('View overlap','opportunities')}</div></div>`;}
function reservePage(){const r=state.activeResource||state.resources[0];return head(r.name,'Illustrative listing · confirm all details with its owner.',btn('Back to inventory','inventory'))+`<div class="grid two"><div class="card stack"><h2>${esc(r.name)} ${demo}</h2><p>${esc(r.owner)} · ${esc(r.place)}</p><div class="metric">${r.quantity} available</div><p class="muted">${esc(r.date)} · ${r.rate?'$'+r.rate.toLocaleString()+'/day per unit':'Rate on request'}</p><div class="note">This listing is example data. A reservation request does not confirm availability.</div>${btn('Open conversation','messages')}</div><div class="card"><h2>Request reservation</h2><div class="fieldgroup"><label>Quantity</label><input id="reserveQty" class="field" type="number" min="1" max="${r.quantity}" value="1"></div><div class="fieldgroup"><label>Dates</label><input id="reserveDates" class="field" value="${esc(r.date)}"></div><div class="fieldgroup"><label>Project</label><select class="field" id="reserveProject">${projects.slice(0,5).map(p=>`<option>${esc(p.project_name)}</option>`).join('')}</select></div>${btn('Send request','confirmReserve','primary accent')}</div></div>`;}
function jobsPage(){return head('Staff your projects','Post worker requirements and review applicants.',btn('+ Describe job requirement','addJob','primary'))+`<div class="grid two"><div class="card"><h2>Open job postings ${demo}</h2>${state.jobs.map(j=>`<div class="item"><div class="statusline"><h3>${esc(j.name)}</h3>${pill(j.openings+' openings','amber')}</div><p class="muted">${esc(j.place)} · ${esc(j.dates)} · ${esc(j.pay)}</p><p class="tiny">${esc(j.owner)}</p>${btn('View role','job:'+j.id)}</div>`).join('')}</div><div class="card stack"><h2>Chat-led posting</h2><div class="bubble">Tell me the role, headcount, project, dates and qualifications. I will prepare a draft for your review.</div><div class="bubble user">We need five certified lineworkers in Savannah this winter.</div><div class="bubble">Which project and pay range should I include?</div>${btn('Continue in chat','addJob','primary accent')}<div class="note">Manual entry remains available from the draft screen.</div></div></div>`;}
function messagesPage(){const t=costTotals(),s=t.separate-t.coordinated;return head('Contractor messages','Discuss inventory and project coordination with another company.',btn('Call contact','call','secondary'))+`<div class="message-layout"><div class="card"><h2>Conversations</h2><div class="item"><strong>Demo Contractor B</strong><p class="muted">Bucket trucks · Jasper–Okatie ↔ McIntosh–Purrysburg</p></div><div class="item"><strong>Coastal Crane (demo)</strong><p class="muted">Crane availability near Savannah</p></div></div><div class="card message-thread"><h2>Resource discussion ${demo}</h2><div class="bubble">We have two bucket trucks available June 3–10. Can you confirm the project window?</div><div class="bubble user">We are still checking the schedule. Could we review a shared-resource scenario?</div><div class="item"><div class="statusline"><strong>Coordination scenario · for review</strong>${pill('Illustrative','amber')}</div><p>Separate $${t.separate.toLocaleString()} · coordinated $${t.coordinated.toLocaleString()}</p><div class="metric green">$${s.toLocaleString()} potential savings</div><p class="tiny">Assumptions have not been agreed by either contractor.</p>${btn('Open cost comparison','cost')}</div><div class="chat-entry"><input class="field" id="messageText" placeholder="Write a message or ask Gridlock to draft one"><button class="primary" data-action="sendMessage">Send</button></div></div><div class="card"><h2>Opportunity context</h2>${mapHtml({small:true,hover:false})}<div class="stats"><span><b>5.65 mi</b>starter distance</span><span><b>152 days</b>date gap</span></div><p class="muted">No real contractor contact was provided. Phone and messaging are interface concepts.</p>${btn('Discuss assumptions','cost','primary accent')}</div></div>`;}
function workerJobsPage(){return head('Find work on utility projects','Browse sample openings by trade, location and qualifications.',btn('My applications','applications'))+`<div class="joblayout"><div class="card"><div class="row"><input class="field" id="jobSearch" placeholder="Search trade or qualification" aria-label="Search jobs"><button class="primary" data-action="searchJobs">Search</button></div><p class="muted">${state.jobs.length} sample jobs · ${demo}</p>${state.jobs.map(j=>`<div class="item job-card ${j.id===state.selectedJob.id?'selected':''}" data-job="${j.id}"><div class="statusline"><h3>${esc(j.name)}</h3>${pill(j.openings+' openings','amber')}</div><p class="muted">${esc(j.place)} · ${esc(j.dates)} · ${esc(j.pay)}</p><div class="row wrap">${j.quals.map(q=>pill(q,'gray')).join('')}</div><div class="action">${btn('View job','job:'+j.id,'primary accent')}</div></div>`).join('')}</div>${mapHtml({jobs:true})}</div>`;}
function workerJobDetail(){const j=state.selectedJob;return head(j.name,`${j.owner} · ${j.place} · ${demo}`,btn('Back to jobs','findjobs'))+`<div class="grid two"><div class="card stack"><h2>${j.openings} openings · ${j.pay}</h2><p>${j.dates}</p><h3>Requirements</h3><div class="row wrap">${j.quals.map(q=>pill(q)).join('')}</div><p class="muted">Detailed scope, employer verification and actual worksite must be confirmed before applying.</p>${mapHtml({small:true,jobs:true,hover:false})}</div><div class="card"><h2>Apply to this role</h2><div class="fieldgroup"><label>Name</label><input class="field" id="applicantName" value="Jordan Davis"></div><div class="fieldgroup"><label>Qualifications</label><input class="field" id="applicantSkills" value="OSHA 30, CDL Class A"></div><div class="fieldgroup"><label>Availability</label><input class="field" id="applicantAvailability" value="Available for the listed dates"></div><div class="note">Demo action only. No application is sent to an employer.</div><div style="margin-top:18px">${btn('Review and apply','apply','primary accent')}</div></div></div>`;}
function applicationsPage(){return head('Your applications','Track sample status and next steps.',btn('Find jobs','findjobs'))+`<div class="card"><h2>Applications ${demo}</h2>${state.applications.length?state.applications.map(a=>`<div class="item statusline"><div><h3>${esc(a.name)}</h3><p class="muted">${esc(a.place)} · ${esc(a.date)}</p></div>${pill(a.status,'amber')}</div>`).join(''):'<div class="note">No applications yet. Open a job and try the review flow.</div>'}</div>`;}
function workerProfilePage(){return head('Worker profile','Update skills, certifications and availability.',btn('Find matching jobs','findjobs'))+`<div class="grid two"><div class="card"><h2>Jordan Davis ${demo}</h2>${[['Trade','Transmission lineworker'],['Certifications','OSHA 30, CDL Class A'],['Experience','Five years of utility construction'],['Availability','Dec 2026–Mar 2027'],['Service area','Savannah, GA · 25 miles']].map(([k,v])=>`<div class="fieldgroup"><label>${k}</label><input class="field" value="${esc(v)}"></div>`).join('')}${btn('Save demo profile','saveProfile','primary accent')}</div><div class="card"><h2>Jobs near your profile</h2>${state.jobs.map(j=>`<div class="item"><h3>${esc(j.name)}</h3><p class="muted">${esc(j.place)} · ${esc(j.pay)}</p>${btn('View job','job:'+j.id)}</div>`).join('')}</div></div>`;}
// Anchor the map preview card to the selected pin instead of a fixed spot.
function positionHovercard(){document.querySelectorAll('.stage-map .hovercard').forEach(placeHovercard)}
function placeHovercard(card){
  const id=card.dataset.anchor;
  const pin=$(window.gridlockMapLive?`.gpin[data-pid="${id}"]`:`.stage-map .pin[data-project="${id}"],.stage-map .pin[data-job="${id}"]`);
  const r=pin?.getBoundingClientRect();
  if(!r||!r.width){card.classList.remove('anchored','below');card.style.cssText='';return}
  const onScreen=r.right>0&&r.left<innerWidth&&r.bottom>0&&r.top<innerHeight;
  card.classList.add('anchored');card.style.visibility=onScreen?'':'hidden';
  const w=card.offsetWidth,h=card.offsetHeight,gap=14,cx=r.left+r.width/2;
  const below=card.dataset.place==='below'||(card.dataset.place!=='above'&&r.top-h-gap<90);
  card.classList.toggle('below',below);
  // Keep the card in the open map area between the floating panels when there is room.
  let minX=8,maxX=innerWidth-8;
  document.querySelectorAll('.sidebar,.workspace .card').forEach(el=>{
    const p=el.getBoundingClientRect();if(!p.width||p.bottom<r.top-h-gap||p.top>r.bottom+h+gap)return;
    if(p.right<=cx)minX=Math.max(minX,p.right+8);else if(p.left>=cx)maxX=Math.min(maxX,p.left-8);
  });
  if(maxX-minX<w){minX=8;maxX=innerWidth-8}
  const left=Math.max(minX,Math.min(maxX-w,cx-w/2));
  card.style.left=left+'px';card.style.top=(below?r.bottom+gap:r.top-h-gap)+'px';
  card.style.setProperty('--arrow-x',Math.max(18,Math.min(w-18,cx-left))+'px');
}
addEventListener('resize',()=>positionHovercard());
function toast(msg){state.toast=msg;render();setTimeout(()=>{state.toast='';const el=$('#toast');if(el)el.remove();},4200)}
function assistantHint(){return state.role==='worker'?'Find jobs matching my qualifications':({map:'What could these projects share?',cost:'Try a different cost scenario',feasibility:'Test another work window',inventory:'Find nearby bucket trucks',messages:'Draft a reply',jobs:'Draft a job posting'}[state.page]||'Describe what you need');}
function render(){
  const pages={map:mapPage,opportunities:opportunityPage,feasibility:feasibilityPage,cost:costPage,projects:projectsPage,projectDetail:projectDetailPage,inventory:inventoryPage,reserve:reservePage,jobs:jobsPage,messages:messagesPage,findjobs:workerJobsPage,jobDetail:workerJobDetail,applications:applicationsPage,workerprofile:workerProfilePage};
  const content=state.page==='addProject'?chatPage('project'):state.page==='addResource'?chatPage('resource'):state.page==='addJob'?chatPage('job'):state.page.startsWith('manual:')?chatPage(state.page.split(':')[1],true):(pages[state.page]||mapPage)();
  const mapFocus = state.page==='map' || state.page==='opportunities' || state.page==='findjobs';
  $('#app').innerHTML=`<a href="#main" class="skip">Skip to content</a><div class="stage-map ${mapFocus?'map-focus':''}">${mapHtml({hover:mapFocus,jobs:state.role==='worker'})}</div><div class="shell">${nav()}<div class="main">${topbar()}<main class="workspace page-${state.page}" id="main">${content}</main></div></div><div class="chatbar"><span class="spark">✦</span><input id="globalChat" placeholder="Ask Gridlock: ${assistantHint()}" aria-label="Ask Gridlock"><button class="primary" data-action="globalChat">➜</button></div>${state.resourceModal&&state.page==='inventory'?resourceModal():''}${state.toast?`<div id="toast" role="status" style="position:fixed;top:85px;right:25px;z-index:30;background:#113a53;color:white;padding:14px 44px 14px 18px;border-radius:13px;box-shadow:0 8px 30px #2345">${esc(state.toast)}<button class="close-x light" data-action="closeToast" aria-label="Close" title="Close">×</button></div>`:''}`;
  window.syncGoogleMap?.();
  requestAnimationFrame(positionHovercard);
  if(state.resourceModal){const b=$('#rmBubbles');if(b)b.scrollTop=b.scrollHeight;window.renderMiniMap?.($('#rmMap'))}
}
function draftFromText(kind,text){
  const d=kind==='resource'?state.resourceDraft:kind==='job'?state.jobDraft:state.draft;
  if(kind==='resource'){
    d.name=/bucket truck/i.test(text)?'Bucket trucks with operators':/crane/i.test(text)?'Crane':/lineworker/i.test(text)?'Certified lineworkers':d.name||text.slice(0,75);
    d.quantity=(text.match(/\b(\d+)\s+(?:bucket|truck|crane|lineworker|worker|crew)/i)||[])[1]||d.quantity||'';
    d.location=/savannah/i.test(text)?'Savannah, GA':d.location||'';
    d.dates=(text.match(/(?:June|July|August|September|Jun|Jul|Aug|Sep)\s+\d+(?:\s*[–-]\s*\d+)?/i)||[])[0]||d.dates||'';
    d.rate=(text.match(/\$[\d,]+/)||[])[0]||d.rate||'';
  }else if(kind==='job'){
    d.role=/lineworker/i.test(text)?'Transmission lineworker':/operator/i.test(text)?'Bucket truck operator':d.role||text.slice(0,60);
    d.openings=(text.match(/\b(\d+)\s+(?:certified\s+)?(?:lineworker|worker|operator|electrician)/i)||[])[1]||d.openings||'';
    d.project=d.project||'';d.dates=(text.match(/(?:June|July|December|winter)[^,.]{0,20}/i)||[])[0]||d.dates||'';
    d.requirements=/certified/i.test(text)?'Relevant certification required':d.requirements||'';
  }else{
    d.name=/corridor upgrade/i.test(text)?'Corridor upgrade':/substation upgrade/i.test(text)?'Substation upgrade':d.name||text.slice(0,70);
    d.location=/hardeeville/i.test(text)?'Near Hardeeville, SC':/savannah/i.test(text)?'Near Savannah, GA':d.location||'';
    d.start=d.start||'';d.end=d.end||'';
    d.closure=/lane closure/i.test(text)?'Potential lane closure · verify road and hours':d.closure||'';
  }
}
function handleAction(act){
  if(act==='addResource'||act==='manual:resource'||act==='chat:resource'){state.page='inventory';state.resourceModal=true;state.resourceManual=act==='manual:resource';render();setTimeout(()=>$('#chatText')?.focus());return}
  if(act==='closeResource'){state.resourceModal=false;render();return}
  if(act==='resourceManual'){state.resourceManual=true;render();return}
  if(act==='resourceChatMode'){state.resourceManual=false;render();return}
  if(act==='sendChat:resource'){
    const text=$('#chatText')?.value.trim();if(!text)return;
    state.resourceChat.push({by:'user',text,time:clockTime()});resourceFromText(text);state.resourceDraft.updated=clockTime();
    const missing=resourceMissing(state.resourceDraft);
    state.resourceChat.push({by:'assistant',time:clockTime(),text:missing.length?`I updated the listing. To make it accurate and complete, can you share ${missing.join(', ')}?`:'The listing is complete based on your information. Please review every field before publishing. Anything else to add, like special notes or travel radius?'});
    render();setTimeout(()=>$('#chatText')?.focus());return;
  }
  if(act.startsWith('selectProject:')){state.selectedProject=byId[act.split(':')[1]];state.page='projectDetail';render();return}
  if(act.startsWith('reserve:')){state.activeResource=state.resources.find(r=>r.id===act.split(':')[1]);state.page='reserve';render();return}
  if(act.startsWith('job:')){state.selectedJob=state.jobs.find(j=>j.id===act.split(':')[1]);state.page='jobDetail';render();return}
  if(act.startsWith('manual:')){state.page=act;render();return}
  if(act.startsWith('chat:')){state.page={project:'addProject',resource:'addResource',job:'addJob'}[act.split(':')[1]];render();return}
  if(act.startsWith('sendChat:')){
    const kind=act.split(':')[1],text=$('#chatText')?.value.trim();if(!text)return;
    if(state.chatMode!==kind){state.chat=[];state.chatMode=kind}state.chat.push({by:'user',text});draftFromText(kind,text);
    state.chat.push({by:'assistant',text:kind==='project'?'I prepared a draft. Please confirm the exact location, construction dates, closure and source.':kind==='resource'?'I prepared a resource draft. Please confirm quantity, dates, rate and owner.':'I prepared a job draft. Please confirm the linked project, qualifications and pay.'});render();return;
  }
  if(act.startsWith('publish:')){
    const kind=act.split(':')[1],d=kind==='project'?state.draft:kind==='resource'?state.resourceDraft:state.jobDraft;
    if(!Object.values(d).some(Boolean)){toast('Describe the item or fill its fields first.');return}
    if(kind==='project'){toast('Demo project draft reviewed. No utility filing was changed.');state.page='projects'}
    else if(kind==='resource'){const miss=resourceMissing(d);if(miss.length){toast('Add '+miss.join(', ')+' before publishing.');return}state.resources.unshift({id:'NEW'+Date.now(),name:d.name||d.category,quantity:Number(d.quantity)||1,date:d.end?`${fmtDate(d.start)} – ${fmtDate(d.end)}`:fmtDate(d.start),place:d.location,rate:Number(d.rate)||0,type:CATEGORIES[d.category]||'Equipment',owner:'Your company (demo)'});state.resourceDraft={};state.resourceChat=[];state.resourceModal=false;state.page='inventory';toast('Demo resource listing added locally.')}
    else{state.jobs.unshift({id:'NEW'+Date.now(),name:d.role||'Untitled opening',openings:Number(d.openings)||1,place:'Location to confirm',pay:'Rate to confirm',dates:d.dates||'Dates to confirm',quals:d.requirements?[d.requirements]:[],owner:'Your company (demo)'});state.page='jobs';toast('Demo job posting added locally.')}
    render();return;
  }
  if(act==='confirmReserve'){const r=state.activeResource||state.resources[0],q=Math.max(1,Number($('#reserveQty')?.value)||1);if(q>r.quantity){toast('Requested quantity exceeds the sample listing.');return}state.reservations.unshift({name:r.name,date:$('#reserveDates')?.value||r.date,status:`Pending · ${q} requested`});state.page='inventory';toast('Demo reservation request saved locally.');return}
  if(act==='apply'){const j=state.selectedJob;state.applications.unshift({name:j.name,place:j.place,date:new Date().toLocaleDateString(),status:'Submitted (demo)'});state.page='applications';toast('Demo application saved locally. Nothing was sent to an employer.');return}
  if(act==='globalChat'){const text=$('#globalChat')?.value.trim();if(!text)return; if(/resource|truck|crane|crew/i.test(text)){state.page='inventory';toast('Showing demo resources.')}else if(/cost|sav/i.test(text)){state.page='cost';toast('Opening the editable cost scenario.')}else if(state.role==='worker'&&/job|work|certification/i.test(text)){state.page='findjobs';toast('Showing sample job listings.')}else if(/project|draft|add/i.test(text)){state.page='addProject';state.chatMode='project';state.chat=[{by:'user',text}];draftFromText('project',text);render();toast('Review the project draft before publishing.')}else toast(state.role==='worker'?'Try asking about jobs, trades, or certifications.':'Try asking about projects, cost, or inventory.');return}
  if(act==='analyze'){toast('Scenario refreshed. Traffic values remain illustrative until a data source is connected.');return}
  if(act==='call'){toast('Demo contact only. No phone number is connected.');return}
  if(act==='sendMessage'){const text=$('#messageText')?.value.trim();if(text)toast('Demo message drafted locally; no message was sent.');return}
  if(act==='saveProfile'){toast('Demo profile saved for this session.');return}
  if(act==='filterResource'||act==='searchJobs'){toast('Filter UI is a prototype; all demo records remain visible.');return}
  if(act==='closeHover'){state.hoverClosed=true;render();return}
  if(act==='closeOpps'){state.oppsClosed=true;render();return}
  if(act==='openOpps'){state.oppsClosed=false;render();return}
  if(act==='closePair'){state.pairClosed=true;render();return}
  if(act==='closeToast'){state.toast='';render();return}
  if(act==='jobDetail'){state.page='jobDetail';render();return}
  state.page=act;render();
}
document.addEventListener('click',e=>{
  const compact=e.target.closest('.stage-map .hovercard');if(compact&&document.body.classList.contains('cards-compact')){window.expandMapCards?.();return}
  const role=e.target.closest('[data-role]');if(role){state.role=role.dataset.role;state.page=state.role==='worker'?'findjobs':'map';render();return}
  const page=e.target.closest('[data-page]');if(page){state.page=page.dataset.page;render();return}
  const over=e.target.closest('[data-overlap]');if(over){state.pairClosed=state.hoverClosed=false;state.pairFocus=true;state.selectedOverlap=overlaps.find(o=>o.overlap_id===over.dataset.overlap);state.hoverProject=state.selectedProject=byId[state.selectedOverlap.project_id_a];render();return}
  const project=e.target.closest('[data-project]');if(project){state.hoverClosed=false;state.pairFocus=false;state.hoverProject=byId[project.dataset.project];state.selectedProject=state.hoverProject;render();return}
  const job=e.target.closest('[data-job]');if(job){state.hoverClosed=false;state.selectedJob=state.jobs.find(j=>j.id===job.dataset.job);render();return}
  const suggest=e.target.closest('[data-suggest]');if(suggest){$('#chatText').value=suggest.dataset.suggest;$('#chatText').focus();return}
  const action=e.target.closest('[data-action]');if(action)handleAction(action.dataset.action);
});
document.addEventListener('change',e=>{
  const rd=e.target.dataset.rdraft;if(rd){const d=state.resourceDraft;d[rd]=rd==='radius'?Number(e.target.value):e.target.value;d.updated=clockTime();if(['category','location','radius','operator'].includes(rd))render();else{const t=document.querySelector('.rm-listing .tiny');if(t)t.textContent='Last updated '+d.updated}return}
  const c=e.target.dataset.cost;if(c){state.cost[c]=Math.max(0,Number(e.target.value)||0);render();return}
  const p=e.target.dataset.proposed;if(p){state.proposed[p]=e.target.value;return}
  const cl=e.target.dataset.closure;if(cl){state.closure[cl]=e.target.value;return}
  const d=e.target.dataset.draft;if(d){const kind=e.target.dataset.kind,target=kind==='project'?state.draft:kind==='resource'?state.resourceDraft:state.jobDraft;target[d]=e.target.value;const copies=document.querySelectorAll(`[data-draft="${d}"][data-kind="${kind}"]`);copies.forEach(x=>{if(x!==e.target)x.value=e.target.value})}
});
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.id==='globalChat'){e.preventDefault();handleAction('globalChat')}if(e.key==='Escape'&&state.resourceModal){handleAction('closeResource');return}if(e.key==='Enter'&&e.target.id==='chatText'){e.preventDefault();handleAction('sendChat:'+(state.resourceModal||state.page==='addResource'?'resource':state.page==='addJob'?'job':'project'))}});
render();
