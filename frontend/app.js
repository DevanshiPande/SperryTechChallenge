// Filled from the backend by backend.js (arrays and byId are updated in place).
const projects = [];
const overlaps = [];
const byId = {};
const state = {
  role: 'contractor', page: 'addProject', selectedOverlap: null, selectedProject: null, selectedJob: null, loaded: false, loadError: '',
  hoverProject: null, hoverClosed: true, pairClosed: true, pairFocus: false, oppRadius: 25, chat: [], chatMode: null, draft: {}, resourceDraft: {}, resourceModal: false, invFind: true, invSelected: null, invQuery: '', invCat: 'All', invFrom: '', invTo: '', resourceManual: false, resourceChat: [], jobDraft: {}, projectUpload: null,
  companyProjects: [], resources: [], jobs: [], myJobs: [], savedJobs: [], reservations: [], applications: [], userOverlaps: [], companies: [], convs: [], thread: [], feas: null, agent: null,
  cost: { mobilization: 3000, truckRate: 1300, separateDays: 20, coordinatedDays: 12, yard: 5000 },
  toast: ''
};
const $ = q => document.querySelector(q);
const esc = s => String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const btn = (label, action, cls = 'secondary') => `<button class="${cls}" data-action="${action}">${label}</button>`;
const pill = (label, cls = '') => `<span class="pill ${cls}">${esc(label)}</span>`;
const demo = '';
function nav() {
  const items = state.role === 'contractor' ? [
    ['addProject','⇪','Upload Contract'],['map','◫','Explore Map'],['feasibility','△','Traffic & Timing'],['cost','▥','Cost Comparison'],['inventory','♧','Inventory'],['jobs','♙','Staffing']
  ] : [['findjobs','⌕','Find Jobs'],['saved','♡','Saved'],['applications','▤','Applications'],['workerprofile','♙','Profile']];
  return `<aside class="sidebar"><div class="brand"><img class="brand-mark" src="assets/contractmap-mark.png" alt=""><span class="brand-name">Contract<i>Map</i></span></div>${items.map(([id,icon,name]) => `<button class="nav ${state.page === id ? 'active' : ''}" data-page="${id}"><span class="icon">${icon}</span>${name}</button>`).join('')}</aside>`;
}
function topbar() {
  return `<header class="topbar"><div class="top-search"><input id="topSearch" placeholder="Search projects, resources, or jobs" aria-label="Search"></div><div class="segmented" role="group" aria-label="Role"><button class="switch ${state.role==='contractor'?'active':''}" data-role="contractor">Contractor</button><button class="switch ${state.role==='worker'?'active':''}" data-role="worker">Worker</button></div></header>`;
}
const head = (title, subtitle, action = '') => `<div class="heading"><div><h1>${title}</h1>${subtitle?`<p class="sub">${subtitle}</p>`:''}</div>${action}</div>`;
function projectLine(p) { return `${esc(p.project_name)} <span class="tiny">${esc(p.utility)}</span>`; }
function mapHtml({small=false, hover=true, pair=true, jobs=false}={}) {
  const valid = projects.filter(p => Number.isFinite(p.lat_center) && Number.isFinite(p.lon_center) && projectVisible(p));
  const x = lon => 8 + (lon + 82.3) / 1.65 * 84;
  const y = lat => 91 - (lat - 31.8) / 2.15 * 82;
  const clampPct = v => Math.max(4,Math.min(96,v));
  const markers = jobs ? state.jobs.filter(j=>Number.isFinite(j.lat)&&Number.isFinite(j.lon)).map(j => `<button title="${esc(j.name)}" class="pin ${state.selectedJob?.id===j.id?'desc selected':'gpc'}" style="left:${clampPct(x(j.lon))}%;top:${clampPct(y(j.lat))}%" data-job="${j.id}"></button>`).join('') : valid.map(p => `<button title="${esc(p.project_name)}" class="pin ${pinClass(p)} ${selectedPinIds().includes(p.project_id)?'selected':''}" style="left:${clampPct(x(p.lon_center))}%;top:${clampPct(y(p.lat_center))}%" data-project="${p.project_id}"></button>`).join('');
  const hv = state.hoverProject || state.selectedProject;
  // The color legend only belongs on the main map pages (Explore map, and Find jobs for workers).
  const showLegend = !small && (state.page === 'map' || state.page === 'findjobs');
  const closeX='<button class="close-x" data-action="closeHover" aria-label="Close" title="Close">×</button>';
  const projectCard=(p,place='')=>{const w=p.construction_window||{},wl=w.source==='predicted'?'predicted':w.source==='estimated'?'estimated':'';return `<div class="hovercard" data-anchor="${p.project_id}" data-place="${place}">${closeX}<div class="row wrap">${pill(p.mine?'Your project':p.utility.includes('Dominion')?'Dominion Energy SC':p.utility.includes('Georgia')?'Georgia Power':p.utility,p.mine?'purple':p.utility.includes('Dominion')?'':'amber')}</div><h3>${esc(p.project_name)}</h3><p>${w.start?`Construction ${esc(fmtDate(w.start))} – ${esc(fmtDate(w.end))}${wl?` (${wl} start)`:''}`:`In-service: ${esc(String(p.in_service_date).slice(0,10))}`} · ${esc(p.state||'')}${p.budget_usd?` · budget ${p.budget_source&&String(p.budget_source).startsWith('predicted')?'≈ ':''}$${Number(p.budget_usd).toLocaleString()}`:''}</p>${btn('View full project','selectProject:'+p.project_id,'primary')}</div>`};
  let hcard='';
  if(hover&&!state.hoverClosed){
    if(jobs){const j=state.selectedJob;if(j)hcard=`<div class="hovercard" data-anchor="${j.id}">${closeX}<div class="row wrap">${pill('Job preview','amber')}</div><h3>${esc(j.name)}</h3><p>${j.openings} openings · ${esc(j.place)} · ${esc(j.pay)}</p>${btn('View job details','jobDetail','primary')}</div>`}
    else if(state.pairFocus){
      // One card per project in the selected pair: the northern one above its pin, the southern one below.
      const pair=pairProjects().filter(hasXY).sort((x,y)=>y.lat_center-x.lat_center);
      hcard=pair.map((p,i)=>projectCard(p,pair.length>1?(i?'below':'above'):'')).join('');
    }
    else if(hv)hcard=projectCard(hv);
  }
  return `<div class="map ${small?'mini-map':''}"><svg viewBox="0 0 1000 700" preserveAspectRatio="none" aria-hidden="true"><rect width="1000" height="700" fill="#e4f1e9"/><path d="M450 0 C510 170 410 300 510 440 S500 630 580 700" stroke="#98c9dc" stroke-width="55" fill="none"/><path d="M450 0 C510 170 410 300 510 440 S500 630 580 700" stroke="#bbdfea" stroke-width="33" fill="none"/><g stroke="#fff" stroke-width="7" opacity=".85"><path d="M0 85L1000 190M0 275L1000 330M0 530L1000 480M120 0L260 700M770 0L630 700M960 0L830 700"/></g><path d="M210 60L460 640" stroke="#d3a95a" stroke-width="6" fill="none"/><text x="130" y="68" fill="#667f86" font-size="20">GEORGIA</text><text x="685" y="68" fill="#667f86" font-size="20">SOUTH CAROLINA</text><text x="416" y="445" fill="#237d9c" font-size="18" transform="rotate(-76 416 445)">SAVANNAH RIVER</text><text x="175" y="540" fill="#315a6d" font-size="25">Savannah</text><text x="610" y="264" fill="#315a6d" font-size="19">Okatie</text></svg>${markers}${showLegend?`<div class="map-label">${jobs?'Job locations':window.gridlockMapLive?'Project locations · Google Maps':'Project locations · schematic map'}</div><div class="map-legend">${!jobs&&state.myFocus&&(state.congestion||{})[state.myFocus]?.roads?`<b>Predicted congestion</b><br><span class="lg-line heavy"></span>Heavy<br><span class="lg-line moderate"></span>Moderate<br><span class="lg-line light"></span>Light (quiet road)<br><span class="lg-dash"></span>The project's line<br><span class="xing-dot heavy lg"></span>Where it crosses a road<hr>`:''}<span class="dot desc"></span>${jobs?'Selected job':'Dominion Energy SC'}<br><span class="dot gpc"></span>${jobs?'Other jobs':'Georgia Power'}${!jobs&&state.companyProjects.length?'<br><span class="dot mine"></span>Your projects':''}<br>Click a pin for details</div>`:''}${!small&&state.page==='feasibility'?trafficLegend():''}${hcard}</div>`;
}
// Small key for the Traffic & timing map (bottom left).
function trafficLegend(){
  return `<div class="map-legend traffic-legend" aria-label="Map legend"><b>Predicted congestion</b><span><i class="lg-line heavy"></i>Heavy</span><span><i class="lg-line moderate"></i>Moderate</span><span><i class="lg-line light"></i>Light</span><span><i class="lg-dash"></i>Project line</span><span><i class="xing-dot heavy lg"></i>Road crossing</span><hr><span><i class="dot desc"></i>Dominion Energy SC</span><span><i class="dot gpc"></i>Georgia Power</span>${state.companyProjects.length?'<span><i class="dot mine"></i>Your projects</span>':''}<small>${state.trafficProject?'Click a road or dot for details':'Click a site to see its traffic'}</small></div>`;
}
const hasXY=p=>Number.isFinite(p?.lat_center)&&Number.isFinite(p?.lon_center);
const pairProjects=()=>state.selectedOverlap?[byId[state.selectedOverlap.project_id_a],byId[state.selectedOverlap.project_id_b]].filter(Boolean):[];
const selectedPinIds=()=>state.pairFocus?pairProjects().map(p=>p.project_id):state.selectedProject?[state.selectedProject.project_id]:[];
const pairName=o=>o.label||`${byId[o.project_id_a]?.short_name||shortName(byId[o.project_id_a]?.project_name||'')} ↔ ${byId[o.project_id_b]?.short_name||shortName(byId[o.project_id_b]?.project_name||'')}`;
const utilLabel=p=>p?.mine?'Your project':p?.utility?.includes('Dominion')?'Dominion Energy SC':p?.utility?.includes('Georgia')?'Georgia Power':(p?.utility||'');
const POTENTIAL={high:['High potential','green'],medium:['Medium potential','amber'],low:['Low potential','gray']};
// n = position in the (possibly filtered) list; the overall rank is shown when they differ.
function opportunityButton(o, n) {
  const selected = state.selectedOverlap?.overlap_id === o.overlap_id, s=o.cost_estimate||{}, pos=n??o.rank;
  return `<button class="opportunity ${selected?'selected':''}" data-overlap="${o.overlap_id}"><strong>#${pos||''} ${esc(pairName(o))}${o.rank&&pos!==o.rank?` <span class="tiny">(overall #${o.rank})</span>`:''}</strong><span class="muted">${esc(utilLabel(byId[o.project_id_a]))} ↔ ${esc(utilLabel(byId[o.project_id_b]))} · score ${o.score??'–'}/100</span><div class="stats"><span><b>${o.distance_mi} mi</b>apart, edge to edge</span><span><b>$${Number(s.total_estimated_savings_usd||0).toLocaleString()}</b>likely savings</span></div>${o.within_sperry_rule===false?'<p class="tiny">Found by edge distance (centers are over 25 mi apart)</p>':''}</button>`;
}
function pairPanel() {
  if(state.pairClosed && state.page==='map') return '<div></div>';
  const o=state.selectedOverlap; if(!o) return '<div></div>';
  const ce=o.cost_estimate||{}, [pl,pc]=POTENTIAL[o.potential]||['Potential','coral'];
  return `<div class="card stack closable pair-panel"><button class="close-x" data-action="closePair" aria-label="Close" title="Close">×</button><div class="pair-kicker">${pill(pl+' coordination',pc)}</div><h2>${esc(pairName(o))}</h2><div class="pair-score"><div><span class="tiny">Coordination score</span><strong>${o.score??'–'}<small>/100</small></strong></div></div><div class="metric-grid"><div><strong>${o.distance_mi} mi</strong><div class="tiny">apart at the closest points · ${o.center_distance_mi} mi center to center</div></div><div><strong>${o.window_overlap_months||0} mo</strong><div class="tiny">construction overlap</div></div></div>${o.tier_explanation?`<div class="note">${esc(o.tier_explanation)}.</div>`:''}<div class="card" style="background:#fff5f2"><div class="muted">Estimated savings from coordinating</div><div class="metric green">$${Number(ce.total_estimated_savings_usd||0).toLocaleString()}</div></div><div class="row wrap">${btn('See cost breakdown','cost','primary')}</div></div>`;
}
// ---- Your project on the map (after saving a contract, or from My projects) ----
// Focus a project on the map: its ranked partners (left), project summary (right). Congestion lives on Traffic & timing.
// Works for any project; `zoom` is for arriving from elsewhere (after saving, My projects), not for pin clicks.
function focusMyProject(id,{zoom=true}={}){
  const p=byId[id];if(!p)return;
  const top=projectOverlaps(id)[0];
  Object.assign(state,{page:'map',myFocus:id,pairFocus:false,pairClosed:true,hoverClosed:false,oppsClosed:false,hoverProject:p,selectedProject:p});
  if(top)state.selectedOverlap=top; // Cost comparison follows the focused project's best pair
  if(zoom)state.zoomTo={id,n:Date.now()};
  window.loadSuggestions?.(id);
}
const LEVEL_PILL={heavy:['Heavy','coral'],moderate:['Moderate','amber'],light:['Light','green']};
// Predicted congestion on the roads around your project (from GET /projects/{id}/congestion).
function congestionBlock(id){
  const c=(state.congestion||{})[id];
  if(!c)return `<div class="note">Predicting traffic congestion around this project…</div>`;
  if(c.error)return `<div class="warning">${esc(c.error)}</div>`;
  const roads=c.roads.filter(r=>r.role!=='crossroad'||r.level!=='light').slice(0,6);
  return `<div class="congestion-block"><h3>Predicted congestion</h3><p class="congestion-summary">${esc(c.summary)}</p>${roads.length?`<ul class="congestion-roads">${roads.map(r=>`<li>${pill(LEVEL_PILL[r.level][0],LEVEL_PILL[r.level][1])}<span><b>${esc(r.road_label)}</b><small>${r.role==='crossroad'?'crossroad of '+esc(r.meets):r.role==='access'?'road to the site':'the line crosses it'+(r.where?' · '+esc(r.where):'')}${r.backed_up_hours&&r.level!=='light'?' · '+esc(r.backed_up_hours):''}</small></span></li>`).join('')}</ul>`:''}<p class="tiny">${c.summary_source==='gemini'?'Summary written by Gemini from the traffic model; ':''}${esc(c.basis)}</p></div>`;
}
// Pin clicks: on Traffic & timing, stay on the page and show that site's popup and timing; elsewhere, focus it on Explore map.
function selectSite(id){
  if(state.page!=='feasibility')return focusMyProject(id,{zoom:false});
  const p=byId[id];if(!p)return;
  Object.assign(state,{trafficProject:id,hoverProject:p,selectedProject:p,hoverClosed:false,pairFocus:false});
  window.loadCongestion?.(id);
}
const focusName=p=>p.mine?'your project':(p.short_name||shortName(p.project_name));
function myOppList(p){
  const list=projectOverlaps(p.project_id);
  const rows=list.map((o,i)=>{const q=partnerOf(o,p.project_id),ce=o.cost_estimate||{},sel=state.pairFocus&&state.selectedOverlap?.overlap_id===o.overlap_id;return `<button class="opportunity ${sel?'selected':''}" data-overlap="${o.overlap_id}"><strong>#${i+1} ${esc(q?.short_name||shortName(q?.project_name||''))}</strong><span class="muted">${esc(utilLabel(q))} · score ${o.score??'–'}/100</span><div class="stats"><span><b>${o.distance_mi} mi</b>apart, edge to edge</span><span><b>$${Number(ce.total_estimated_savings_usd||0).toLocaleString()}</b>likely savings</span></div></button>`}).join('');
  return `<div class="card closable"><button class="close-x" data-action="clearMyFocus" aria-label="Show all pairs" title="Show all pairs">×</button><h2>Coordination for ${esc(focusName(p))}</h2><p class="muted">${list.length} planned project${list.length===1?'':'s'} within 25 miles · highest priority first</p>${rows||'<div class="note">No other planned projects within 25 miles.</div>'}<button class="ghostlink" data-action="clearMyFocus">Show all Dominion ↔ Georgia Power pairs</button></div>`;
}
function myProjectPanel(p){
  const w=p.construction_window||{},top=projectOverlaps(p.project_id)[0];
  return `<div class="card stack closable my-panel"><button class="close-x" data-action="clearMyFocus" aria-label="Close" title="Close">×</button><div>${p.mine?pill('Your project','purple'):pill(utilLabel(p),p.utility.includes('Dominion')?'':'amber')}</div><h2>${esc(p.project_name)}</h2><div class="metric-grid"><div><strong>${w.start?esc(fmtDate(w.start)):'–'}</strong><div class="tiny">start${w.source==='predicted'?' (predicted)':''}</div></div><div><strong>${w.end?esc(fmtDate(w.end)):'–'}</strong><div class="tiny">end</div></div></div><dl class="panel-facts"><div><dt>Voltage</dt><dd>${p.voltage_kv?p.voltage_kv+' kV':'Not provided'}</dd></div><div><dt>Contractor</dt><dd>${esc(p.utility_name||(p.company_id?companyName(p.company_id):utilLabel(p))||'Not provided')}</dd></div><div><dt>Location</dt><dd>${esc(p.location||'Not provided')}</dd></div></dl>${top?`<div class="card" style="background:#f6f1ff"><div class="muted">Top coordination partner</div><strong>${esc(partnerOf(top,p.project_id)?.short_name||'')}</strong><div class="metric green">$${Number(top.cost_estimate?.total_estimated_savings_usd||0).toLocaleString()}</div><div class="tiny">likely savings · ${top.distance_mi} mi apart</div></div>`:''}<div class="row wrap">${btn('Traffic & congestion','traffic:'+p.project_id,'primary')}</div></div>`;
}
const OPP_RADII=[0,5,10,15,25,50]; // 0 = any distance
// Radius = distance between the two projects of a pair, measured edge to edge (closest points).
const oppInRange=o=>!state.oppRadius||Number(o.distance_mi)<=state.oppRadius;
// Projects shown on the map: with a radius set, only those in a pair within range.
// Pin color: your company's projects are purple; public plans by utility.
const pinClass=p=>p.mine?'mine':p.utility.includes('Dominion')?'desc':'gpc';
function projectVisible(p){
  if(p.mine||!state.oppRadius)return true; // your own projects always show
  if(state.myFocus&&projectOverlaps(state.myFocus).some(o=>o.project_id_a===p.project_id||o.project_id_b===p.project_id))return true;
  return overlaps.some(o=>oppInRange(o)&&(o.project_id_a===p.project_id||o.project_id_b===p.project_id));
}
function mapPage() {
  const shown=overlaps.filter(oppInRange),mine=state.myFocus&&byId[state.myFocus];
  if(mine)return `<div class="grid three">${state.oppsClosed?`<div><button class="reopen-chip" data-action="openOpps">≡ Coordination for your project</button></div>`:myOppList(mine)}${mapHtml()}${state.pairFocus&&!state.pairClosed?pairPanel():myProjectPanel(mine)}</div>`;
  const list=state.oppsClosed
    ? `<div><button class="reopen-chip" data-action="openOpps">≡ Coordination opportunities <span>${shown.length}</span></button></div>`
    : `<div class="card closable"><button class="close-x" data-action="closeOpps" aria-label="Close" title="Close">×</button><h2>Coordination opportunities</h2><div class="opp-filter"><label for="oppRadius">Projects within</label><select id="oppRadius" class="field">${OPP_RADII.map(r=>`<option value="${r}" ${r===state.oppRadius?'selected':''}>${r?r+' mi of each other':'any distance'}</option>`).join('')}</select></div><p class="muted">${shown.length} of ${overlaps.length} Dominion ↔ Georgia Power pairs${state.oppRadius?` within ${state.oppRadius} mi, edge to edge`:''} · highest priority first</p>${shown.map((o,i)=>opportunityButton(o,i+1)).join('')||`<div class="note">No pairs within ${state.oppRadius} mi. Try a larger radius.</div>`}</div>`;
  return `<div class="grid three">${list}${mapHtml()}${pairPanel()}</div>`;
}
function feasibilityPage(){return `<div class="traffic-page"><div class="traffic-side">${timingCard(trafficTiming())}</div></div>`;}
// Suggested time to work: the site selected on this page's map, else a contract being uploaded, else the last saved contract.
function trafficTiming(){
  const p=byId[state.trafficProject],c=p&&(state.congestion||{})[p.project_id];
  if(p&&!c)return {parsed:true,timingLoading:true};
  if(c?.error)return {parsed:true,timingError:c.error};
  if(c?.best_time)return {parsed:true,timing:c.best_time,name:p.project_name,draft:{project_name:p.project_name}};
  return state.projectUpload||state.savedTiming;
}
const COST_PARTS=[['mobilization','Shared mobilization',''],['logistics','Logistics','Shorter trips between the two sites'],['shared_land','Shared right-of-way','Land both lines can use'],['traffic_delay','Traffic delay avoided','One combined road closure instead of two']];
function costPage(){
  const o=state.selectedOverlap;if(!o)return '<div class="note">Select a coordination opportunity on the map first.</div>';
  const ce=o.cost_estimate||{},comp=ce.components||{},a=byId[o.project_id_a],b=byId[o.project_id_b];
  const pairs=overlaps.map(x=>`<option value="${x.overlap_id}" ${x.overlap_id===o.overlap_id?'selected':''}>#${x.rank||''} ${esc(pairName(x))}</option>`).join('');
  const usd=n=>'$'+Math.round(Number(n)||0).toLocaleString();
  const applies=COST_PARTS.filter(([k])=>comp[k]?.applies),skipped=COST_PARTS.filter(([k])=>!comp[k]?.applies);
  const maxHigh=Math.max(1,...applies.map(([k])=>Number(comp[k].high)||0));
  // One row per component: the bar spans low to high on a shared scale; the marker is the likely value.
  const rows=applies.map(([k,l,d])=>{const c=comp[k],pct=v=>Math.max(0,Math.min(100,(Number(v)||0)/maxHigh*100));return `<div class="cost-line"><div class="cost-line-label"><b>${l}</b><span class="tiny">${[d,c.requires_schedule_shift&&'needs a schedule shift'].filter(Boolean).join(' · ')}</span></div><div class="cost-line-bar" title="Low ${usd(c.low)} · likely ${usd(c.point)} · high ${usd(c.high)}"><span class="range" style="left:${pct(c.low)}%;width:${Math.max(1,pct(c.high)-pct(c.low))}%"></span><span class="point" style="left:${pct(c.point)}%"></span></div><div class="cost-line-value"><b>${usd(c.point)}</b><span class="tiny">${usd(c.low)} – ${usd(c.high)}</span></div></div>`}).join('')||'<div class="note">No savings components apply to this pair.</div>';
  const src=s=>typeof s==='string'?esc(s):`${esc(s.label||s.name||s.title||'Source')}${s.url?` — <a href="${esc(s.url)}" target="_blank" rel="noopener">link</a>`:''}`;
  return `<div class="cost-page">
    <div class="card cost-summary">
      <h2>How much could these projects save by working together?</h2>
      <label class="cost-pick"><span class="cost-pick-label">Choose a project pair</span><select id="costPair" class="field">${pairs}</select></label>
      <div class="cost-pair"><div><span class="cost-pair-util">${esc(utilLabel(a))}</span><span>${esc(a?.project_name)}</span></div><span class="cost-pair-link">↔<small>${o.distance_mi} mi apart${o.window_overlap_months?` · ${o.window_overlap_months} mo of overlapping work`:''}</small></span><div><span class="cost-pair-util">${esc(utilLabel(b))}</span><span>${esc(b?.project_name)}</span></div></div>
      <div class="cost-tiles"><div><span class="cost-tile-label">Estimated savings (all components)</span><strong class="green">${usd(ce.total_estimated_savings_usd)}</strong></div><div><span class="cost-tile-label">Possible range</span><strong>${usd(ce.range_usd?.[0])} – ${usd(ce.range_usd?.[1])}</strong></div><div><span class="cost-tile-label">Priority score</span><strong>${o.score??'–'}<small>/100</small></strong></div></div></div>
    <div class="card"><h2>Where the savings come from</h2><p class="tiny">Each row is one source of savings; the total above is their sum.</p>${rows}${applies.length>1?`<div class="cost-line cost-total"><div class="cost-line-label"><b>Total</b><span class="tiny">sum of the rows above</span></div><div></div><div class="cost-line-value"><b>${usd(ce.total_estimated_savings_usd)}</b><span class="tiny">${usd(ce.range_usd?.[0])} – ${usd(ce.range_usd?.[1])}</span></div></div>`:''}${skipped.length?`<p class="tiny">Not applicable for this pair: ${skipped.map(([,l])=>l.toLowerCase()).join(', ')}.</p>`:''}${ce.reference_budget_usd?`<p class="tiny">Based on a reference budget of ${usd(ce.reference_budget_usd)} (${esc(ce.reference_budget_source||'')}).</p>`:''}<p class="tiny">Planning estimates. Confirm rates, schedules and scope with the other company before relying on them.</p></div>
    <div class="cost-notes"><details class="card"><summary><b>Assumptions</b></summary><ul class="tiny">${(ce.assumptions||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details><details class="card"><summary><b>Sources</b> <span class="tiny">(${(ce.sources||[]).length})</span></summary><ul class="tiny">${(ce.sources||[]).map(s=>`<li>${src(s)}</li>`).join('')}</ul></details></div>
  </div>`;}
// ---- Project page ("View full project"): everything about one project; your own projects can be switched here ----
function projectDetailPage(){
  const p=state.selectedProject;
  if(!p)return `<div class="card project-page"><h2>Project</h2><p class="muted">Select a site on the map first.</p>${btn('Back to map','map','primary')}</div>`;
  const w=p.construction_window||{},money=n=>'$'+Number(n).toLocaleString();
  const facts=[
    ['Contractor',p.utility_name||(p.company_id?companyName(p.company_id):utilLabel(p))],
    ['Work type',p.work_type_label&&p.work_type_label!==p.description&&p.work_type_label!=='User project'?p.work_type_label:''],
    ['Voltage',p.voltage_kv&&p.voltage_kv+' kV'],
    ['Location',p.location],
    ['Counties',(p.counties||[]).join(', ')],
    ['State',p.state],
    ['Construction',w.start?`${fmtDate(w.start)} – ${fmtDate(w.end)}${w.source==='predicted'?' (start predicted)':''}`:''],
    ['In service',p.in_service_date&&fmtDate(p.in_service_date)],
    ['Budget',p.budget_usd&&`${String(p.budget_source||'').startsWith('predicted')?'≈ ':''}${money(p.budget_usd)}`],
    ['Roads affected',(p.roads_affected||[]).map(r=>r.name||r.ref||r).join(', ')],
    ['Lane closures',p.lane_closures],
    ['Work hours',p.work_hours],
    ['Status',p.status]
  ].filter(([,v])=>v!==undefined&&v!==null&&v!=='');
  const own=state.companyProjects;
  const picker=p.mine&&own.length>1?`<label class="project-pick"><span class="tiny">Switch project</span><select id="projectPick" class="field">${own.map(q=>`<option value="${q.project_id}" ${q.project_id===p.project_id?'selected':''}>${esc(q.project_name)}</option>`).join('')}</select></label>`:'';
  const badge=p.mine?pill('Your project','purple'):pill(utilLabel(p),String(p.utility||'').includes('Dominion')?'':'amber');
  return `<div class="card project-page"><div>${badge}</div><h2>${esc(p.project_name)}</h2>${picker}<dl class="panel-facts">${facts.map(([k,v])=>`<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>${p.description?`<p class="muted">${esc(p.description)}</p>`:''}<div class="row wrap">${btn('Show on map','showOnMap:'+p.project_id,'primary')}${btn('Traffic & timing','traffic:'+p.project_id,'secondary')}</div></div>`;}
function chatPage(kind,manual=false){
  const resource=kind==='resource', job=kind==='job';
  const title=resource?'Describe an available resource':job?'Describe a job requirement':'Describe a new project';
  const draft=resource?state.resourceDraft:job?state.jobDraft:state.draft;
  const question=resource?'Tell me what equipment or crew you can share, how many, when, and where.':job?'What role, headcount, project, dates, and qualifications do you need?':'Tell me the planned work, location, dates, and any affected roads.';
  const hints=resource?['Two bucket trucks near Savannah June 3–10 at $1,250 each','Five lineworkers free next month']:job?['We need five certified lineworkers near Savannah in December','Post two bucket truck operator openings']:['A corridor upgrade near Hardeeville June to December 2027','A substation upgrade near Savannah next year'];
  const fields=resource?['name','quantity','location','dates','rate']:job?['role','openings','project','dates','requirements']:['name','location','start','end','closure'];
  const labels={name:'Name',quantity:'Quantity',location:'Location',dates:'Dates',rate:'Daily rate',role:'Role',openings:'Openings',project:'Linked project',requirements:'Requirements',start:'Start date',end:'End date',closure:'Road closure'};
  return head(title,manual?'Manual entry is an alternative. You can return to chat anytime.':'Chat creates a reviewable draft. Nothing is published automatically.',btn(manual?'Use chat instead':'Use manual form',manual?'chat:'+kind:'manual:'+kind))+`<div class="page-chat"><div class="card conversation"><h2>${manual?'Manual details':'✦ Ask ContractMap'}</h2><p class="muted">${manual?'Fill the fields and review the result.':question}</p>${manual?`<div class="formgrid">${fields.map(k=>`<div class="fieldgroup"><label>${labels[k]}</label><input class="field" data-draft="${k}" data-kind="${kind}" value="${esc(draft[k]||'')}" placeholder="${labels[k]}"></div>`).join('')}</div>`:`<div class="bubbles"><div class="bubble">${question}</div>${state.chatMode===kind?state.chat.map(m=>`<div class="bubble ${m.by==='user'?'user':''}">${esc(m.text)}</div>`).join(''):''}</div><div class="chat-entry"><input class="field" id="chatText" placeholder="Describe it in your own words"><button class="primary" data-action="sendChat:${kind}">Send</button></div><div class="row wrap" style="margin-top:12px">${hints.map(h=>`<button class="ghostlink" data-suggest="${esc(h)}">${esc(h)}</button>`).join('')}</div>`}</div><div class="stack"><div class="card"><div class="statusline"><h2>Editable draft</h2>${pill('Not published','amber')}</div><p class="muted">Review every extracted field before sharing it.</p>${fields.map(k=>`<div class="fieldgroup"><label>${labels[k]}</label><input class="field" data-draft="${k}" data-kind="${kind}" value="${esc(draft[k]||'')}" placeholder="Not provided yet"></div>`).join('')}<div class="row wrap">${btn('Review and publish','publish:'+kind,'primary accent')}${btn('Use manual form','manual:'+kind)}</div></div><div class="note">AI extraction is mocked locally. A real Gemini connection should return structured fields, cite source input, and require the same review step.</div></div></div>`;
}

function projectUploadPage(){
  const upload=state.projectUpload, d=upload?.draft||{};
  const field=(key,label)=>`<label class="fieldgroup${key==='description'||key==='roads'?' grow':''}"><span>${label}</span>${key==='description'||key==='roads'?`<textarea class="field" rows="2" data-project-draft="${key}" placeholder="Not found in document">${esc(d[key]||'')}</textarea>`:`<input class="field" data-project-draft="${key}" value="${esc(d[key]||'')}" placeholder="Not found in document" type="${key.includes('date')?'date':'text'}">${!d[key]&&mlPredictions(upload)[key]?`<small class="ml-hint">Predicted: ${esc(fmtDate(mlPredictions(upload)[key].value))} (${esc(mlPredictions(upload)[key].range)})</small>`:''}`}</label>`;
  const fields=[['project_name','Project name'],[['utility','Company / utility'],['location','Location']],[['start_date','Start date'],['end_date','End date']],['description','Scope of work'],['roads','Affected roads'],['contact','Contract contact']];
  return `<div class="project-upload-layout"><div class="upload-col"><div class="card upload-card"><div class="upload-icon">PDF</div><h2>Upload contract details</h2><p class="muted">Choose a project contract or scope PDF. ContractMap AI reads it and prepares the project details for your review.</p><label class="upload-drop"><input id="projectPdf" type="file" accept="application/pdf"><strong>${upload?.name?esc(upload.name):'Choose a PDF contract'}</strong><span>${upload?.status||'PDF files only · maximum 15 MB'}</span></label>${upload?.error?`<div class="warning">${esc(upload.error)}</div>`:''}${upload?.note?`<div class="note">${esc(upload.note)}</div>`:''}</div>${mlBox(upload)}</div><div class="card project-draft"><div class="statusline"><div><h2>Project details</h2><p class="muted">${upload?'Review the extracted information below.':'Your extracted details will appear here.'}</p></div>${upload?.parsed?pill('Needs review','amber'):''}</div>${fields.map(f=>Array.isArray(f[0])?`<div class="date-pair">${f.map(g=>field(...g)).join('')}</div>`:field(...f)).join('')}${upload?.saveError?`<div class="warning">Could not save: ${esc(upload.saveError)}</div>`:''}<div class="row wrap">${upload?.saving?'<button class="primary accent" disabled>Saving… finding coordination partners</button>':btn('Save my project','publish:project','primary accent')}${upload&&!upload.saving?btn('Clear upload','clearProjectUpload'):''}</div></div></div>`;
}
// Values the contract left out, predicted by the ML models (from the match result; nothing is saved yet).
function mlPredictions(upload){
  const pr=upload?.match?.project;if(!pr)return {};
  const w=pr.construction_window||{},pd=w.prediction||{},out={};
  if(w.source==='predicted'){const f=pd.field||'start';out[f==='end'?'end_date':'start_date']={value:w[f],text:`${f==='end'?'End':'Start'} date ${fmtDate(w[f])}`,range:f==='end'?`likely ${fmtDate(pd.end_low)} – ${fmtDate(pd.end_high)}`:`${pd.low}–${pd.high} months before the end`,why:`${pd.months} months of work predicted from ${pd.trained_on}; typical error ${pd.typical_error_months} months.`};}
  if(String(pr.budget_source||'').startsWith('predicted'))out.budget={value:pr.budget_usd,text:`Budget $${Number(pr.budget_usd).toLocaleString()}`,range:`likely $${Number(pr.budget_range_usd[0]).toLocaleString()} – $${Number(pr.budget_range_usd[1]).toLocaleString()}`,why:pr.budget_note||''};
  return out;
}
function mlBox(upload){
  const ps=Object.values(mlPredictions(upload));
  if(!ps.length)return '';
  return `<div class="card ml-card"><div class="statusline"><h2>Predicted by the ContractMap model</h2>${pill('Predicted','purple')}</div><p class="tiny">The contract leaves these out, so ContractMap's models estimated them. Type a value in the form to replace a prediction.</p>${ps.map(x=>`<div class="ml-row"><b>${esc(x.text)}</b><span>${esc(x.range)}</span><small>${esc(x.why)}</small></div>`).join('')}</div>`;
}
// Suggested time to work, shown as soon as the contract is read (from POST /contracts/{id}/match; nothing is saved).
function timingCard(upload){
  if(!upload?.parsed)return `<div class="card timing-card muted-card"><h2>Suggested time to work</h2><p class="muted">Select a project site on the map to see when to do the work, based on traffic on the roads it crosses and other construction nearby.</p></div>`;
  const t=upload.timing;
  if(upload.timingLoading)return `<div class="card timing-card"><h2>Suggested time to work</h2><p class="muted">Checking road traffic and nearby construction…</p></div>`;
  if(upload.timingError)return `<div class="card timing-card"><h2>Suggested time to work</h2><div class="note">${esc(upload.timingError)}</div>${btn('Update suggestion','refreshTiming','secondary')}</div>`;
  if(!t)return '';
  const chips=[t.best_hours?.label&&`<div><span class="tiny">Best hours</span><strong>${esc(t.best_hours.label)}</strong></div>`,(t.best_months||[]).length&&`<div><span class="tiny">Best months</span><strong>${esc(t.best_months.join(', '))}</strong></div>`].filter(Boolean).join('');
  const m=upload.summary;
  return `<div class="card timing-card"><div class="statusline"><h2>Suggested time to work</h2>${upload.stale?pill('Details changed','amber'):pill('From traffic data','green')}</div>${upload.name?`<p class="tiny">For ${esc(upload.draft?.project_name||upload.name)}</p>`:''}<p class="timing-headline">${esc(t.headline||'')}</p>${chips?`<div class="timing-chips">${chips}</div>`:''}${(t.reasons||[]).length?`<details open><summary class="tiny">Why</summary><ul class="timing-reasons">${t.reasons.map(r=>`<li>${esc(r)}</li>`).join('')}</ul></details>`:''}${m?`<p class="tiny">${m.matches_count} coordination match${m.matches_count===1?'':'es'} within 25 miles${m.best_savings_usd?` · best likely savings $${Number(m.best_savings_usd).toLocaleString()}`:''}.</p>`:''}${upload.stale?btn('Update suggestion','refreshTiming','secondary'):''}<p class="tiny">${esc(t.basis||'')}</p></div>`;
}

function projectFromPdfText(text, fileName){
  const clean=text.replace(/\s+/g,' ').trim();
  const datePattern='(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\\s+\\d{1,2}(?:,?\\s+\\d{4})?';
  const dates=[...clean.matchAll(new RegExp(datePattern,'gi'))].map(m=>m[0]);
  const isoDate=value=>{const parsed=new Date(value);return Number.isNaN(parsed.getTime())?'':parsed.toISOString().slice(0,10)};
  const valueAfter=label=>{const match=clean.match(new RegExp(label+'\\s*[:\\-]\\s*([^.;]{2,100})','i'));return match?match[1].trim():''};
  const location=valueAfter('(?:project )?location|worksite|service area')||((clean.match(/(?:near|in) ([A-Z][A-Za-z]+(?:,? [A-Z]{2})?)/)||[])[1]||'');
  const name=valueAfter('project name|project title|contract name')||fileName.replace(/\.pdf$/i,'').replace(/[_-]+/g,' ');
  const utility=valueAfter('owner|utility|customer|company')||'';
  const scope=valueAfter('scope of work|scope|description')||'';
  const roads=valueAfter('affected roads?|roadways?|work area')||'';
  const contact=valueAfter('contact|project manager')||'';
  const paragraphs=clean.split(/(?<=[.!?])\s+/);
  return {project_name:name,utility,location,start_date:isoDate(dates[0]),end_date:isoDate(dates[1]||dates[0]),description:scope||paragraphs.find(p=>/construct|rebuild|upgrade|install|replace/i.test(p))||'',roads,contact,source:'contract-upload',fileName};
}

async function parseProjectPdf(file){
  if(!window.pdfjsLib) throw new Error('The PDF parser could not load. Check your internet connection and try again.');
  if(file.size>15*1024*1024) throw new Error('This PDF is larger than 15 MB.');
  const buffer=await file.arrayBuffer();
  const pdf=await window.pdfjsLib.getDocument({data:buffer}).promise;
  const pages=[];
  for(let pageNumber=1;pageNumber<=pdf.numPages;pageNumber++){
    const page=await pdf.getPage(pageNumber), content=await page.getTextContent();
    pages.push(content.items.map(item=>item.str).join(' '));
  }
  const text=pages.join('\n').trim();
  if(!text) throw new Error('This PDF has no selectable text. A scanned PDF needs OCR before it can be parsed.');
  return projectFromPdfText(text,file.name);
}

// ---- Inventory: resource listing pop-up (chat on the left, structured listing on the right) ----
const PLACES = {
  'Savannah, GA': [32.0809, -81.0912], 'Pooler, GA': [32.1155, -81.2471], 'Hardeeville, SC': [32.2871, -81.0790],
  'Okatie, SC': [32.3363, -80.9387], 'Jesup, GA': [31.6074, -81.8854], 'Augusta, GA': [33.4735, -82.0105],
  'Charleston, SC': [32.7765, -79.9311]
};
const CATEGORIES = { 'Bucket trucks': 'Equipment', 'Digger derricks': 'Equipment', 'Cranes': 'Equipment', 'Excavators': 'Equipment', 'Trenchers': 'Equipment', 'Line crew': 'Crew', 'Materials': 'Materials', 'Other': 'Equipment' };
// Photos per category; categories without one fall back to the drawn icon.
const CATEGORY_PHOTOS = { 'Bucket trucks': 'assets/inventory/bucket-truck.jpg', 'Cranes': 'assets/inventory/crane.jpg', 'Digger derricks': 'assets/inventory/digger-derrick.jpg', 'Excavators': 'assets/inventory/excavator.jpg', 'Trenchers': 'assets/inventory/trencher.jpg', 'Line crew': 'assets/inventory/line-crew.jpg', 'Materials': 'assets/inventory/materials.jpg' };
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
  if (CATEGORY_PHOTOS[category]) return `<img src="${CATEGORY_PHOTOS[category]}" alt="${esc(category)}">`;
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
      <h2>✦ Ask ContractMap</h2>
      <div class="row wrap rm-hints">${['Two bucket trucks near Savannah June 3–10 at $1,250/day with operators', 'Five certified lineworkers in Pooler July 1–20', 'Offer materials'].map(h => `<button class="ghostlink" data-suggest="${esc(h)}">${esc(h)}</button>`).join('')}</div>
      <div class="bubbles" id="rmBubbles">${bubbles}</div>
      <div class="chat-entry"><input class="field" id="chatText" placeholder="Describe what you can share"><button class="primary rm-send" data-action="sendChat:resource" aria-label="Send">➤</button></div>
    </section>`;
  const demand = matches.map(({ p, mi }) => `<button class="rm-match" data-action="selectProject:${p.project_id}">
      <span class="rm-bars" aria-hidden="true"><i></i><i></i><i></i></span>
      <span><strong>${esc(shortName(p.project_name))}</strong><small>${esc(p.utility)}</small><small>${mi.toFixed(1)} mi · in-service ${esc(String(p.in_service_date).slice(0, 10))}</small></span><span class="chev">›</span></button>`).join('')
    || `<div class="note">${at ? `No planned projects within ${radius} mi.` : 'Choose a pickup area to see planned projects nearby.'}</div>`;
  return `<div class="rm-modal ${manual ? 'manual' : ''}" role="dialog" aria-modal="true" aria-label="Resource listing">
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
      <div class="rm-actions">${btn('➤ Review and publish', 'publish:resource', 'primary')}</div>
    </section>
  </div>`;
}
function resourceFromText(text) {
  const d = state.resourceDraft, n = '(\\d+|an?|one|two|three|four|five|six|seven|eight|nine|ten)';
  const words = { a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10 };
  const cat = /bucket/i.test(text) ? 'Bucket trucks' : /digger|derrick/i.test(text) ? 'Digger derricks' : /crane/i.test(text) ? 'Cranes' : /excavator/i.test(text) ? 'Excavators' : /trench/i.test(text) ? 'Trenchers' : /lineworker|crew|workers?\b/i.test(text) ? 'Line crew' : /material|pole|conductor|wire|transformer/i.test(text) ? 'Materials' : '';
  if (cat) d.category = cat;
  const q = text.match(new RegExp(`\\b${n}\\s+(?:certified\\s+)?(?:bucket|truck|crane|digger|excavator|trencher|lineworker|worker|crew)`, 'i'));
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
    const qty = Number(d.quantity), countWord = Object.keys(words).find(w => w.length > 2 && words[w] === qty) || d.quantity || 'Some';
    const noun = d.category === 'Line crew' ? (qty === 1 ? 'crew member' : 'crew members') : qty === 1 && d.category !== 'Materials' ? plural.replace(/s$/, '') : plural;
    d.description = `${countWord} ${noun} available${d.location ? ' near ' + d.location.split(',')[0] : ''}${d.operator === 'Yes' && d.category !== 'Line crew' ? ' with experienced operator' + (qty === 1 ? '' : 's') : ''}.`;
    d.description = d.description.charAt(0).toUpperCase() + d.description.slice(1);
  }
}
const clockTime = () => new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
function inventoryPage(){
  const tab=(label,action,on)=>`<button class="inv-tab ${on?'active':''}" data-action="${action}" aria-pressed="${on}">${label}</button>`;
  return `<div class="inv-head-row"><div class="inv-tabs">${tab('Add inventory','invAdd',state.resourceModal)}${tab('Find inventory','invFind',state.invFind)}</div></div>`+(state.resourceModal?resourceModal():state.invFind?findSheet():'');
}
// Bottom sheet: vertical list of listings on the left, details and order form for the selected one on the right.
function findSheet(){
  const types=['All',...new Set(state.resources.map(r=>r.type))];
  const sel=state.resources.find(r=>r.id===state.invSelected)||state.resources[0];
  if(sel)state.invSelected=sel.id;
  const rate=r=>r.rate?'$'+r.rate.toLocaleString()+'/day':'Rate on request';
  const rows=state.resources.map(r=>`<button class="inv-row ${r.id===sel?.id?'active':''}" data-action="invSelect:${r.id}" data-type="${esc(r.type)}" data-start="${r.start||''}" data-end="${r.end||''}" data-text="${esc([r.name,r.place,r.owner,r.type].join(' ').toLowerCase())}">
      <span class="inv-thumb">${resourceIcon(r.category)}</span><span class="inv-row-body"><span class="inv-row-top"><strong>${esc(r.name)}</strong>${pill(r.type)}</span>
      <small>${r.quantity} available · ${esc(r.date)}</small><small>⌖ ${esc(r.place)} · ${rate(r)}</small><span class="inv-partial" hidden>Partly covers your dates</span></span></button>`).join('');
  const mine=state.reservations.filter(x=>x.id===sel?.id);
  const reqList=mine.length?`<div class="inv-mine"><h3>${sel.mine?'Requests for your listing':'Your requests for this listing'}</h3>${mine.map(x=>`<div class="item"><strong>${esc(x.status)}</strong><p class="muted">${esc(x.date)}${x.project?' · '+esc(x.project):''}${x.incoming?' · from '+esc(x.requester):''}</p>${x.incoming&&x.raw.status==='pending'?`<div class="row wrap">${btn('Accept','rsv:'+x.rid+':accepted','primary')}${btn('Decline','rsv:'+x.rid+':declined')}</div>`:!x.incoming&&x.raw.status==='pending'?btn('Cancel request','rsv:'+x.rid+':cancelled'):''}</div>`).join('')}</div>`:'';
  const orderForm=sel?.mine?`<div class="note">This is your company's listing. Other contractors can find and request it.</div>`:`<form class="inv-order" onsubmit="return false"><h3>Place an order</h3>
        <div class="inv-order-grid"><label>Quantity<input id="orderQty" class="field" type="number" min="1" max="${sel?.quantity}" value="1"></label>
        <label>Dates<input id="orderDates" class="field" readonly value="${esc(state.invFrom&&state.invTo?`${fmtDate(state.invFrom)} – ${fmtDate(state.invTo)}`:sel?.date)}" title="Set From / To on the left to request specific dates"></label>
        <label class="wide">For project<select id="orderProject" class="field"><option value="">No specific project</option>${[...state.companyProjects,...projects.filter(p=>!p.mine)].map(p=>`<option value="${p.project_id}">${esc(p.mine?'Your project: ':'')}${esc(p.project_name)}</option>`).join('')}</select></label></div>
        ${btn('Place order','placeOrder','primary')}
        <p class="tiny">Sends a request to the owner. No payment is taken here.</p></form>`;
  const detail=sel?`<div class="inv-detail-head"><div>${pill(sel.type)}<h2>${esc(sel.name)}</h2><p class="muted">${esc(sel.mine?'Your company':sel.owner)}</p></div><div class="inv-price">${rate(sel)}<small>per unit</small></div></div>
      <div class="inv-facts"><div><span>Available</span><strong>${sel.quantity}</strong></div><div><span>Dates</span><strong>${esc(sel.date)}</strong></div><div><span>Pickup</span><strong>${esc(sel.place)}</strong></div></div>
      ${sel.notes?`<p class="muted">${esc(sel.notes.replace(/Category: [^.]+\.\s*/,''))}</p>`:''}
      ${orderForm}${reqList}`
    :'<div class="note">No listings yet.</div>';
  return `<div class="inv-sheet" role="dialog" aria-label="Find inventory"><button class="close-x" data-action="closeFind" aria-label="Close" title="Close">×</button>
    <div class="inv-split">
      <section class="inv-list"><div class="inv-find-head"><h2>Find inventory ${demo}</h2><span class="tiny" id="invCount"></span></div>
        ${suggestFold()}
        <div class="inv-filters"><input id="invSearch" class="field" placeholder="Search equipment, crews, places, owners" value="${esc(state.invQuery)}">
        <select id="invCat" class="field" aria-label="Category">${types.map(t=>`<option ${t===state.invCat?'selected':''}>${esc(t)}</option>`).join('')}</select></div>
        <div class="inv-dates"><label>From<input id="invFrom" class="field" type="date" value="${state.invFrom}"></label><label>To<input id="invTo" class="field" type="date" value="${state.invTo}" min="${state.invFrom}"></label><button class="ghostlink" data-action="invClearDates" ${state.invFrom||state.invTo?'':'hidden'}>Clear dates</button></div>
        <div class="inv-rows">${rows}<div class="note inv-empty" hidden>No listings match. Try another search or category.</div></div></section>
      <section class="inv-detail">${detail}</section></div></div>`;
}
// Listings that fit your projects: coordination partners first, then nearby and available during your dates.
function suggestBody(){
  const s=state.suggested,fp=s?.project_id&&byId[s.project_id];
  const title=fp?'Suggested for '+esc(focusName(fp)):'Suggested for you';
  if(!s)return '<div class="note">Loading suggestions…</div>';
  if(!s.needs?.length)return `<div class="note">${esc(s.note||'No project selected.')}</div>`;
  // 1. what the project needs, and how much of it is covered
  const needs=s.needs.map(n=>`<li class="${n.missing?'miss':'ok'}"><span class="need-mark">${n.missing?n.missing+' short':'✓'}</span><span><b>${n.quantity} ${n.unit==='people'?'people · '+esc(n.label.toLowerCase()):esc(n.quantity===1?n.label.toLowerCase().replace(/s$/,''):n.label.toLowerCase())}${n.tons?` (${n.tons}-ton)`:''}</b><small>${n.covered_by.length?'from '+esc(n.covered_by.join(', ')):'no listing found yet'}</small></span></li>`).join('');
  const src=s.needs[0].source==='contract'?'From the project contract':'Typical for this kind of work (the project has no equipment list)';
  // 2. your own inventory, 3. other companies' listings that fill the rest
  const own=(s.own||[]).map(o=>`<div class="own-line">✓ ${esc(o.text)}</div>`).join('');
  const cards=(s.suggestions||[]).map(x=>{const r=state.resources.find(y=>y.id===x.resource_id);return `<button class="suggest-card ${x.resource_id===state.invSelected?'active':''} ${x.covers?'':'extra'}" data-action="invSelect:${x.resource_id}"><span class="suggest-top"><span class="inv-thumb">${resourceIcon(r?.category)}</span><span><strong>${esc(x.resource_name)}</strong><small>${esc(x.company_name||'')} · ${x.distance_mi} mi away</small></span></span><span class="row wrap">${x.covers?pill('Covers '+x.covers+(x.category==='line_crew'?' people':''),'green'):pill('Not needed now','gray')}${x.partner?pill('Coordination partner','purple'):''}${x.haul_saved_usd?pill('≈ $'+x.haul_saved_usd.toLocaleString()+' less trucking','gray'):''}</span><ul>${x.reasons.slice(0,3).map(t=>`<li>${esc(t)}</li>`).join('')}</ul></button>`}).join('')||'<div class="note">No other company lists anything this project needs, within reach and during its dates.</div>';
  return `<div class="suggest-rows"><div class="needs-box"><h3>What it needs</h3><p class="tiny">${src}.</p><ul class="needs-list">${needs}</ul>${s.missing?.length?`<p class="tiny"><b>Still missing:</b> ${esc(s.missing.join(', '))}. Post a request or ask a coordination partner.</p>`:'<p class="tiny"><b>Every need is covered.</b></p>'}</div>
    ${own?`<div class="own-box">${own}</div>`:''}${cards}<p class="tiny">${esc(s.basis||'')}</p></div>`;
}
// Suggestions folded above the listings (opens on click): what the selected project needs and who can supply it.
function suggestFold(){
  const s=state.suggested,fp=s?.project_id&&byId[s.project_id],covers=(s?.suggestions||[]).filter(x=>x.covers).length,short=(s?.missing||[]).length;
  const count=s?.needs?.length?` <span class="tiny">(${covers} listing${covers===1?'':'s'} fit${short?' · '+short+' need'+(short===1?'':'s')+' still missing':''})</span>`:'';
  return `<details class="inv-suggest-fold" ${state.suggestOpen?'open':''} ontoggle="state.suggestOpen=this.open"><summary><b>${fp?'Suggested for '+esc(focusName(fp)):'Suggested for you'}</b>${count}</summary>${suggestBody()}</details>`;
}
function applyInvFilter(){
  const q=state.invQuery.trim().toLowerCase(),cat=state.invCat,from=state.invFrom,to=state.invTo,rows=[...document.querySelectorAll('.inv-row')];
  let shown=0;
  rows.forEach(c=>{
    const {start,end}=c.dataset,dated=!!(start&&end);
    // Overlap test on ISO dates: available until at least `from`, and starting no later than `to`.
    const inWindow=(!from&&!to)||(dated&&(!from||end>=from)&&(!to||start<=to));
    const ok=(cat==='All'||c.dataset.type===cat)&&(!q||c.dataset.text.includes(q))&&inWindow;
    c.hidden=!ok;if(ok)shown++;
    const partial=c.querySelector('.inv-partial');if(partial)partial.hidden=!(ok&&from&&to&&dated&&(start>from||end<to));
  });
  const count=$('#invCount');if(count)count.textContent=`${shown} of ${rows.length} listings`;
  const empty=$('.inv-empty');if(empty)empty.hidden=shown>0;
  // Keep the details pane in step with the filter: move the selection to the first visible listing.
  const detail=$('.inv-detail');if(detail)detail.classList.toggle('none',!shown);
  const active=$('.inv-row.active'),first=rows.find(c=>!c.hidden);
  if(active?.hidden&&first){
    const focused=document.activeElement?.id,caret=document.activeElement?.selectionStart;
    state.invSelected=first.dataset.action.split(':')[1];render();
    if(focused){const el=document.getElementById(focused);el?.focus();if(caret!=null)try{el.setSelectionRange(caret,caret)}catch{}}
  }
}
function jobsPage(){return `<div class="grid two"><div class="card"><div class="statusline"><h2>Your job postings</h2>${btn('+ Post a job','addJob','primary')}</div>${state.myJobs.length?'':'<div class="note">No postings yet. Post a job to start receiving applicants.</div>'}${state.myJobs.map(j=>`<div class="item"><div class="statusline"><h3>${esc(j.name)}</h3>${pill(j.openings+(j.openings===1?' opening':' openings'),'amber')}</div><p class="muted">${esc(j.place)} · ${esc(j.dates)} · ${esc(j.pay)}</p><p class="tiny">${esc(j.owner)}</p>${btn('View role','job:'+j.id)}</div>`).join('')}</div><div class="card stack"><h2>Chat-led posting</h2><div class="bubble">Tell me the role, headcount, project, dates and qualifications. I will prepare a draft for your review.</div><div class="bubble user">We need five certified lineworkers in Savannah this winter.</div><div class="bubble">Which project and pay range should I include?</div>${btn('Continue in chat','addJob','primary accent')}<div class="note">Manual entry remains available from the draft screen.</div></div></div>`;}
// Photo shown on the left of a job posting, matched by role name.
const JOB_PHOTOS={'Transmission lineworker':'assets/jobs/transmission-lineworker.jpg','Substation electrician':'assets/jobs/substation-electrician.jpg','Bucket truck operator':'assets/jobs/bucket-truck-operator.jpg'};
function jobCard(j){const saved=state.savedJobs.includes(j.id),photo=JOB_PHOTOS[j.name]||Object.entries(JOB_PHOTOS).find(([k])=>new RegExp(k.split(' ')[0],'i').test(j.name))?.[1];return `<div class="item job-card ${photo?'has-photo':''} ${j.id===state.selectedJob?.id?'selected':''}" data-job="${j.id}">${photo?`<img class="job-photo" src="${photo}" alt="${esc(j.name)}">`:''}<div class="job-body"><div class="statusline"><h3>${esc(j.name)}</h3><div class="row wrap">${pill(j.openings+(j.openings===1?' opening':' openings'),'amber')}<button class="save-heart ${saved?'saved':''}" data-save-job="${j.id}" aria-label="${saved?'Remove from saved jobs':'Save job'}" title="${saved?'Remove from saved jobs':'Save job'}">${saved?'♥':'♡'}</button></div></div><p class="muted">${esc(j.place)} · ${esc(j.dates)} · ${esc(j.pay)}</p><div class="row wrap">${j.quals.map(q=>pill(q,'gray')).join('')}</div><div class="action">${btn('View job','job:'+j.id,'primary accent')}</div></div></div>`;}
function openJob(id){const j=state.jobs.find(x=>x.id===id);if(!j)return;Object.assign(state,{selectedJob:j,page:'jobDetail',jobApplied:null,applyError:''});render();}
function workerJobsPage(){return `<div class="joblayout"><div class="card"><div class="row"><input class="field" id="jobSearch" placeholder="Search trade or qualification" aria-label="Search jobs"><button class="primary" data-action="searchJobs">Search</button></div><p class="muted">${state.jobs.length} open job${state.jobs.length===1?'':'s'}${state.jobQuery?` matching “${esc(state.jobQuery)}”`:''}</p>${state.jobs.map(jobCard).join('')||'<div class="note">No jobs match. Try another search.</div>'}</div>${mapHtml({jobs:true})}</div>`;}
function savedJobsPage(){const jobs=state.jobs.filter(j=>state.savedJobs.includes(j.id));return `<div class="card saved-jobs"><h2>Saved postings</h2>${jobs.length?jobs.map(jobCard).join(''):'<div class="note">No saved jobs yet. Select the heart on a job posting to save it here.</div>'}</div>`;}
// Job page: the role on the left, the application on the right; after submitting, a confirmation replaces the form.
function workerJobDetail(){
  const j=state.selectedJob;if(!j)return workerJobsPage();
  const me=state.me||{},already=state.applications.some(a=>a.name===j.name),done=state.jobApplied===j.id;
  const info=`<div class="card job-info stack"><div class="row wrap">${pill(j.openings+(j.openings===1?' opening':' openings'),'amber')}${pill(j.pay,'gray')}</div><h2>${esc(j.name)}</h2><p class="muted">${esc(j.owner)} · ${esc(j.place)}</p><dl class="panel-facts"><div><dt>Dates</dt><dd>${esc(j.dates)}</dd></div><div><dt>Location</dt><dd>${esc(j.place)}</dd></div><div><dt>Pay</dt><dd>${esc(j.pay)}</dd></div></dl><h3>Requirements</h3><div class="row wrap">${j.quals.map(q=>pill(q)).join('')||'<span class="muted">None listed</span>'}</div><p class="tiny">Confirm the exact worksite and schedule with the employer.</p></div>`;
  // Contractors only review the posting; the application form is for workers.
  if(state.role!=='worker')return `<div class="job-page contractor-view">${info.replace(/<\/div>$/,`<div class="row wrap">${btn('Back to staffing','jobs')}</div></div>`)}</div>`;
  const form=done
    ?`<div class="card apply-card apply-done"><div class="apply-check">✓</div><h2>Application submitted successfully</h2><p class="muted">${esc(j.owner)} has received your application for <b>${esc(j.name)}</b>. You can follow its status under Applications.</p><div class="row wrap">${btn('View my applications','applications','primary accent')}${btn('Back to jobs','findjobs')}</div></div>`
    :`<form class="card apply-card" onsubmit="return false"><h2>Apply to this role</h2><p class="muted">Your details are sent to ${esc(j.owner)}.</p>
      <label class="fieldgroup"><span>Full name</span><input class="field" id="applicantName" required value="${esc(String(me.name||'').replace(/\s*\(demo\)/,''))}"></label>
      <label class="fieldgroup"><span>Qualifications and certifications</span><input class="field" id="applicantSkills" value="${esc((me.certifications||[]).join(', '))}" placeholder="e.g. OSHA 10, CDL Class A"></label>
      <label class="fieldgroup"><span>Availability</span><input class="field" id="applicantAvailability" value="${esc(me.availability||'')}" placeholder="e.g. Available from June 2027"></label>
      ${state.applyError?`<div class="warning">${esc(state.applyError)}</div>`:''}${already?'<div class="note">You have already applied to this role; submitting again sends an update.</div>':''}
      <div class="row wrap">${state.applying?'<button class="primary accent" disabled>Submitting…</button>':btn('Submit application','apply','primary accent')}${btn('Back to jobs','findjobs')}</div></form>`;
  return `<div class="job-page">${info}${form}</div>`;
}
function applicationsPage(){return `<div class="card"><h2>Applications</h2>${state.applications.length?state.applications.map(a=>`<div class="item statusline"><div><h3>${esc(a.name)}</h3><p class="muted">${esc(a.place)} · ${esc(a.date)}</p></div>${pill(a.status,'amber')}</div>`).join(''):'<div class="note">No applications yet. Open a job and try the review flow.</div>'}</div>`;}
function workerProfilePage(){const me=state.me||{},sa=me.service_area||{};return `<div class="card"><h2>${esc(me.name||'Worker profile')}</h2>${[['Trade','pfTrade',me.trade],['Certifications (comma separated)','pfCerts',(me.certifications||[]).join(', ')],['Experience','pfExp',me.experience],['Availability','pfAvail',me.availability]].map(([k,id,v])=>`<div class="fieldgroup"><label>${k}</label><input class="field" id="${id}" value="${esc(v||'')}"></div>`).join('')}<div class="fieldgroup"><label>Service area</label><input class="field" value="${esc(sa.label?`${sa.label} · ${sa.radius_mi||''} miles`:'')}" readonly></div>${btn('Save profile','saveProfile','primary accent')}</div>`;}
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
  if(state.role==='worker'&&state.page==='findjobs'){
    const list=document.querySelector('.page-findjobs .joblayout > .card')?.getBoundingClientRect();
    const minX=Math.max((list?.right||216)+24,240), maxX=innerWidth-16;
    const topbar=document.querySelector('.topbar')?.getBoundingClientRect(), chatbar=document.querySelector('.chatbar')?.getBoundingClientRect();
    const top=Math.max((topbar?.bottom||80)+16,Math.min(innerHeight-h-16,r.top-h-gap));
    card.classList.add('anchored');card.classList.remove('below');card.style.left=Math.max(minX,Math.min(maxX-w,minX))+'px';card.style.top=top+'px';card.style.setProperty('--arrow-x',Math.max(18,Math.min(w-18,cx-parseFloat(card.style.left)))+'px');return;
  }
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
function assistantHint(){return state.role==='worker'?'Find jobs matching my qualifications':({map:'What could these projects share?',cost:'Try a different cost scenario',feasibility:'Test another work window',inventory:'Find nearby bucket trucks',jobs:'Draft a job posting'}[state.page]||'Describe what you need');}
function render(){
  if(!state.loaded){$('#app').innerHTML=`<div style="position:fixed;inset:0;display:grid;place-items:center;background:#f4f8f9;z-index:50"><div class="card stack" style="max-width:420px;text-align:center"><h2>ContractMap</h2>${state.loadError?`<div class="warning">${esc(state.loadError)}</div>${btn('Try again','retryLoad','primary')}`:'<p class="muted">Loading projects and coordination opportunities…</p>'}</div></div>`;return}
  const pages={map:mapPage,feasibility:feasibilityPage,cost:costPage,projectDetail:projectDetailPage,inventory:inventoryPage,jobs:jobsPage,findjobs:workerJobsPage,saved:savedJobsPage,jobDetail:workerJobDetail,applications:applicationsPage,workerprofile:workerProfilePage};
  const content=state.page==='addProject'?projectUploadPage():state.page==='addResource'?chatPage('resource'):state.page==='addJob'?chatPage('job'):state.page.startsWith('manual:')?chatPage(state.page.split(':')[1],true):(pages[state.page]||mapPage)();
  const mapFocus=state.page==='map'||state.page==='findjobs';
  $('#app').innerHTML=`<a href="#main" class="skip">Skip to content</a><div class="stage-map ${mapFocus?'map-focus':''} ${state.page==='map'&&(!state.pairClosed||state.myFocus)?'pair-open':''}">${mapHtml({hover:(mapFocus&&state.role!=='worker')||state.page==='feasibility',jobs:state.role==='worker'})}</div><div class="shell">${nav()}<div class="main">${topbar()}<main class="workspace page-${state.page}" id="main">${content}</main></div></div><div class="chatbar"><span class="spark">✦</span><input id="globalChat" placeholder="Ask ContractMap: ${assistantHint()}" aria-label="Ask ContractMap"><button class="primary" data-action="globalChat">➜</button></div>${window.agentPanel?agentPanel():''}${state.toast?`<div id="toast" role="status" style="position:fixed;top:85px;right:25px;z-index:30;background:#113a53;color:white;padding:14px 44px 14px 18px;border-radius:13px;box-shadow:0 8px 30px #2345">${esc(state.toast)}<button class="close-x light" data-action="closeToast" aria-label="Close" title="Close">×</button></div>`:''}`;
  window.syncGoogleMap?.();
  requestAnimationFrame(positionHovercard);
  if(state.invFind)applyInvFilter();
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
  if(window.apiAction&&apiAction(act))return;
  if(act==='addResource'||act==='manual:resource'||act==='chat:resource'){state.page='inventory';state.resourceModal=true;state.invFind=false;state.resourceManual=act==='manual:resource';render();setTimeout(()=>$('#chatText')?.focus());return}
  if(act==='closeResource'){state.resourceModal=false;render();return}
  if(act==='invAdd'){state.resourceModal=!state.resourceModal;state.invFind=false;render();if(state.resourceModal)setTimeout(()=>$('#chatText')?.focus());return}
  if(act==='invFind'){state.invFind=!state.invFind;state.resourceModal=false;render();return}
  if(act==='invClearDates'){state.invFrom=state.invTo='';render();return}
  if(act==='closeFind'){state.invFind=false;render();return}
  if(act==='sendChat:resource'){
    const text=$('#chatText')?.value.trim();if(!text)return;
    state.resourceChat.push({by:'user',text,time:clockTime()});resourceFromText(text);state.resourceDraft.updated=clockTime();
    const missing=resourceMissing(state.resourceDraft);
    state.resourceChat.push({by:'assistant',time:clockTime(),text:missing.length?`I updated the listing. To make it accurate and complete, can you share ${missing.join(', ')}?`:'The listing is complete based on your information. Please review every field before publishing. Anything else to add, like special notes or travel radius?'});
    render();setTimeout(()=>$('#chatText')?.focus());return;
  }
  if(act.startsWith('traffic:')){state.page='feasibility';selectSite(act.split(':')[1]);render();return}
  if(act.startsWith('projectDetail:')){state.selectedProject=byId[act.split(':')[1]]||state.selectedProject;state.page='projectDetail';render();return}
  if(act==='clearMyFocus'){state.myFocus=null;state.pairFocus=false;state.pairClosed=true;render();window.loadSuggestions?.(null);return}
  if(act.startsWith('showOnMap:')){focusMyProject(act.split(':')[1]);render();return}
  if(act==='backToMine'){focusMyProject(state.myFocus,{zoom:false});render();return}
  if(act.startsWith('selectProject:')){
    const id=act.split(':')[1];
    state.selectedProject=state.companyProjects.find(p=>p.project_id===id)||byId[id];
    state.page='projectDetail';
    render();
    return;
  }
  if(act.startsWith('invSelect:')){
    state.invSelected=act.split(':')[1];
    render();
    return;
  }
  if(act.startsWith('reserve:')){
    state.invSelected=act.split(':')[1];
    state.invFind=true;
    state.resourceModal=false;
    state.page='inventory';
    render();
    return;
  }
  if(act.startsWith('job:')){openJob(act.split(':')[1]);return}
  if(act.startsWith('manual:')){state.page=act;render();return}
  if(act.startsWith('chat:')){state.page={project:'addProject',resource:'addResource',job:'addJob'}[act.split(':')[1]];render();return}
  if(act.startsWith('sendChat:')){
    const kind=act.split(':')[1],text=$('#chatText')?.value.trim();if(!text)return;
    if(state.chatMode!==kind){state.chat=[];state.chatMode=kind}state.chat.push({by:'user',text});draftFromText(kind,text);
    state.chat.push({by:'assistant',text:kind==='project'?'I prepared a draft. Please confirm the exact location, construction dates, closure and source.':kind==='resource'?'I prepared a resource draft. Please confirm quantity, dates, rate and owner.':'I prepared a job draft. Please confirm the linked project, qualifications and pay.'});render();return;
  }
  if(act.startsWith('publish:')){
    const kind=act.split(':')[1],d=kind==='project'?(state.projectUpload?.draft||{}):kind==='resource'?state.resourceDraft:state.jobDraft;
    if(!Object.values(d).some(Boolean)){toast('Describe the item or fill its fields first.');return}
    if(kind==='project'){const project={...state.projectUpload.draft,project_id:'UPLOAD_'+Date.now(),project_name:state.projectUpload.draft.project_name||state.projectUpload.name.replace(/\.pdf$/i,''),source:'contract-upload'};state.companyProjects.unshift(project);state.selectedProject=project;state.projectUpload=null;state.page='projectDetail';toast('Contract details added to your company projects.');}
    else if(kind==='resource'){const miss=resourceMissing(d);if(miss.length){toast('Add '+miss.join(', ')+' before publishing.');return}state.resources.unshift({id:'NEW'+Date.now(),category:d.category,name:d.name||d.category,quantity:Number(d.quantity)||1,date:d.end?`${fmtDate(d.start)} – ${fmtDate(d.end)}`:fmtDate(d.start),start:d.start,end:d.end||d.start,place:d.location,rate:Number(d.rate)||0,type:CATEGORIES[d.category]||'Equipment',owner:'Your company (demo)'});state.resourceDraft={};state.resourceChat=[];state.resourceModal=false;state.invFind=true;state.page='inventory';toast('Demo resource listing added locally.')}
    else{state.jobs.unshift({id:'NEW'+Date.now(),name:d.role||'Untitled opening',openings:Number(d.openings)||1,place:'Location to confirm',pay:'Rate to confirm',dates:d.dates||'Dates to confirm',quals:d.requirements?[d.requirements]:[],owner:'Your company (demo)'});state.page='jobs';toast('Demo job posting added locally.')}
    render();return;
  }
  if(act==='placeOrder'){
    const r=state.resources.find(x=>x.id===state.invSelected);if(!r)return;
    const q=Math.max(1,Number($('#orderQty')?.value)||1);
    if(q>r.quantity){toast(`Only ${r.quantity} available in this listing.`);return}
    state.reservations.unshift({id:r.id,name:r.name,date:$('#orderDates')?.value||r.date,project:$('#orderProject')?.value||'',status:`Pending · ${q} requested`});
    toast('Demo order request saved locally. The owner still needs to accept it.');return;
  }
  if(act==='apply'){const j=state.selectedJob;state.applications.unshift({name:j.name,place:j.place,date:new Date().toLocaleDateString(),status:'Submitted (demo)'});state.page='applications';toast('Demo application saved locally. Nothing was sent to an employer.');return}
  if(act.startsWith('toggleSaveJob:')){const id=act.split(':')[1],index=state.savedJobs.indexOf(id);if(index===-1){state.savedJobs.push(id);toast('Job saved.')}else{state.savedJobs.splice(index,1);toast('Job removed from saved.')}render();return}
  if(act==='globalChat'){const text=$('#globalChat')?.value.trim();if(!text)return; if(/resource|truck|crane|crew/i.test(text)){state.page='inventory';toast('Showing demo resources.')}else if(/cost|sav/i.test(text)){state.page='cost';toast('Opening the editable cost scenario.')}else if(state.role==='worker'&&/job|work|certification/i.test(text)){state.page='findjobs';toast('Showing sample job listings.')}else if(/project|draft|add/i.test(text)){state.page='addProject';state.chatMode='project';state.chat=[{by:'user',text}];draftFromText('project',text);render();toast('Review the project draft before publishing.')}else toast(state.role==='worker'?'Try asking about jobs, trades, or certifications.':'Try asking about projects, cost, or inventory.');return}
  if(act==='saveProfile'){toast('Demo profile saved for this session.');return}
  if(act==='clearProjectUpload'){state.projectUpload=null;render();return}
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
  const role=e.target.closest('[data-role]');if(role){state.role=role.dataset.role;state.page=state.role==='worker'?'findjobs':'addProject';state.agent=null;render();window.onRoleChange?.();return}
  const page=e.target.closest('[data-page]');if(page){state.page=page.dataset.page;render();return}
  const over=e.target.closest('[data-overlap]');if(over){const o=[...overlaps,...(state.userOverlaps||[])].find(x=>x.overlap_id===over.dataset.overlap);if(!o)return;state.pairClosed=state.hoverClosed=false;state.pairFocus=true;state.selectedOverlap=o;state.hoverProject=state.selectedProject=byId[o.project_id_a];if(state.page!=='map')state.page='map';render();return}
  const project=e.target.closest('[data-project]');if(project){const p=byId[project.dataset.project];if(p){selectSite(p.project_id);render();return}state.hoverClosed=false;state.pairFocus=false;state.hoverProject=p;state.selectedProject=p;render();return}
  const saved=e.target.closest('[data-save-job]');if(saved){handleAction('toggleSaveJob:'+saved.dataset.saveJob);return}
  const job=e.target.closest('[data-job]');if(job){openJob(job.dataset.job);return}
  const suggest=e.target.closest('[data-suggest]');if(suggest){$('#chatText').value=suggest.dataset.suggest;$('#chatText').focus();return}
  const action=e.target.closest('[data-action]');if(action)handleAction(action.dataset.action);
});
document.addEventListener('input',e=>{if(e.target.id==='invSearch'){state.invQuery=e.target.value;applyInvFilter()}});
document.addEventListener('change',e=>{
  if(e.target.id==='projectPdf'){
    const file=e.target.files?.[0];if(!file)return;
    analyzeContract(file);
    return;
  }
  if(e.target.id==='projectPick'){state.selectedProject=byId[e.target.value]||state.selectedProject;render();return}
  if(e.target.id==='costPair'){state.selectedOverlap=overlaps.find(o=>o.overlap_id===e.target.value)||state.selectedOverlap;render();return}
  if(e.target.id==='oppRadius'){
    state.oppRadius=Number(e.target.value);
    // Close cards for a pair or project that the new radius filters out.
    if(state.pairFocus&&!oppInRange(state.selectedOverlap)){state.pairFocus=false;state.hoverClosed=true;state.pairClosed=true}
    else if(!state.pairFocus&&!projectVisible(state.selectedProject))state.hoverClosed=true;
    render();return;
  }
  if(e.target.id==='invCat'){state.invCat=e.target.value;applyInvFilter();return}
  if(e.target.id==='invFrom'||e.target.id==='invTo'){state[e.target.id]=e.target.value;if(state.invFrom&&state.invTo&&state.invTo<state.invFrom)state.invTo=state.invFrom;render();return}
  const rd=e.target.dataset.rdraft;if(rd){const d=state.resourceDraft;d[rd]=rd==='radius'?Number(e.target.value):e.target.value;d.updated=clockTime();if(['category','location','radius','operator'].includes(rd))render();else{const t=document.querySelector('.rm-listing .tiny');if(t)t.textContent='Last updated '+d.updated}return}
  const c=e.target.dataset.cost;if(c){state.cost[c]=Math.max(0,Number(e.target.value)||0);render();return}
  const d=e.target.dataset.draft;if(d){const kind=e.target.dataset.kind,target=kind==='project'?state.draft:kind==='resource'?state.resourceDraft:state.jobDraft;target[d]=e.target.value;const copies=document.querySelectorAll(`[data-draft="${d}"][data-kind="${kind}"]`);copies.forEach(x=>{if(x!==e.target)x.value=e.target.value})}
  const projectDraft=e.target.dataset.projectDraft;if(projectDraft&&state.projectUpload){state.projectUpload.draft[projectDraft]=e.target.value;if(state.projectUpload.contractId&&!state.projectUpload.stale){state.projectUpload.stale=true;render()}}
});
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.id==='globalChat'){e.preventDefault();handleAction('globalChat')}if(e.key==='Escape'&&state.resourceModal){handleAction('closeResource');return}if(e.key==='Escape'&&state.invFind&&state.page==='inventory'){handleAction('closeFind');return}if(e.key==='Enter'&&e.target.id==='chatText'){e.preventDefault();handleAction('sendChat:'+(state.resourceModal||state.page==='addResource'?'resource':state.page==='addJob'?'job':'project'))}});
