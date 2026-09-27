// Google Maps background layer. Loads only when config.js provides a key;
// otherwise the illustrative image in styles.css stays in place.
(function () {
  const config = window.GRIDLOCK_CONFIG || {};
  const key = (config.googleMapsApiKey || '').trim();
  if (!key) return;

  let map, AdvancedMarker, markers = [], roadLines = [], roadsKey = '', infoWin = null, zoomedTo = null, focusedPair = null, focusedWorkerJob = null, cardZoom = null, cardKey = '';
  // Zooming out two levels past where the preview cards opened shrinks them to name-only labels.
  const COMPACT_AFTER = 2;
  const updateCompact = () => document.body.classList.toggle('cards-compact', cardZoom != null && map.getZoom() <= cardZoom - COMPACT_AFTER);
  window.expandMapCards = () => { cardZoom = map.getZoom(); updateCompact(); positionHovercard(); };

  window.gm_authFailure = () => {
    document.body.classList.remove('has-gmap');
    window.gridlockMapLive = false;
    toast('Google Maps rejected the API key. Showing the illustrative map instead.');
  };

  window.initGridlockMap = async () => {
    const { Map } = await google.maps.importLibrary('maps');
    ({ AdvancedMarkerElement: AdvancedMarker } = await google.maps.importLibrary('marker'));
    map = new Map(document.getElementById('gmap'), {
      center: { lat: 32.6, lng: -81.4 },
      zoom: 8,
      mapId: config.googleMapsMapId || 'DEMO_MAP_ID',
      disableDefaultUI: true,
      zoomControl: true,
      zoomControlOptions: { position: google.maps.ControlPosition.RIGHT_CENTER },
      gestureHandling: 'greedy'
    });
    window.gridlockMap = map;
    const bounds = new google.maps.LatLngBounds();
    projects.filter(hasCoords).forEach(p => bounds.extend({ lat: p.lat_center, lng: p.lon_center }));
    if (!bounds.isEmpty()) map.fitBounds(bounds, { top: 120, left: 220, right: 60, bottom: 120 });

    map.addListener('bounds_changed', () => positionHovercard());
    map.addListener('idle', () => positionHovercard());
    map.addListener('zoom_changed', () => { updateCompact(); positionHovercard(); });
    document.body.classList.add('has-gmap');
    window.gridlockMapLive = true;
    window.dispatchEvent(new Event('gridlock-map-ready'));
    render();
  };

  // Called from render() so markers follow role and selection changes.
  // If Google's marker code fails (e.g. an expired or over-quota key), fall back to the schematic map
  // instead of breaking the whole page.
  window.syncGoogleMap = () => {
    if (!map) return;
    try { syncMarkers(); } catch (e) {
      console.warn('Google Maps failed; showing the schematic map instead.', e);
      map = null; window.gridlockMap = null;
      window.gridlockMapLive = false;
      document.body.classList.remove('has-gmap');
      if (!window.gmapFailedNotice) { window.gmapFailedNotice = true; setTimeout(() => toast('Google Maps is not working (check the API key). Showing the schematic map instead.'), 0); }
    }
  };
  function syncMarkers() {
    markers.forEach(m => (m.map = null));
    const worker = state.role === 'worker';
    const items = worker
      ? state.jobs.filter(hasCoords).map(j => ({
          id: j.id, title: j.name, lat: j.lat, lng: j.lon,
          cls: j.id === state.selectedJob?.id ? 'desc selected' : 'gpc',
          onClick: () => openJob(j.id)
        }))
      : projects.filter(hasCoords).filter(projectVisible).map(p => ({
          id: p.project_id, title: p.project_name, lat: p.lat_center, lng: p.lon_center,
          cls: `${pinClass(p)} ${selectedPinIds().includes(p.project_id) ? 'selected' : ''}`, z: p.mine ? 1000 : undefined,
          onClick: () => { selectSite(p.project_id); render(); }
        }));
    markers = items.map(it => {
      const el = document.createElement('div');
      el.className = `gpin ${it.cls}`;
      el.dataset.pid = it.id;
      const marker = new AdvancedMarker({ map, position: { lat: it.lat, lng: it.lng }, content: el, title: it.title, gmpClickable: true, ...(it.z != null ? { zIndex: it.z } : {}) });
      marker.addEventListener('gmp-click', it.onClick);
      return marker;
    });
    const key = [...document.querySelectorAll('.stage-map .hovercard')].map(c => c.dataset.anchor).join();
    if (key !== cardKey) { cardKey = key; cardZoom = key ? map.getZoom() : null; updateCompact(); }
    if (!worker && state.page === 'map' && state.zoomTo && state.zoomTo.n !== zoomedTo) focusProject();
    drawCongestion(worker);
    if (!worker && state.pairFocus && state.selectedOverlap && state.selectedOverlap.overlap_id !== focusedPair) focusPair();
    if (!state.pairFocus) focusedPair = null;
    if (!worker || state.page !== 'findjobs') focusedWorkerJob = null;
    // Marker elements attach asynchronously; position the card once the selected one is laid out.
    let tries = 0;
    (function waitForPin() {
      const pin = document.querySelector('.gpin.selected');
      if (pin && pin.getBoundingClientRect().width) positionHovercard();
      else if (tries++ < 60) requestAnimationFrame(waitForPin);
    })();
  }

  // Screen area not covered by the sidebar, floating cards, top bar and chat bar.
  function openArea() {
    const edge = sel => document.querySelector(sel)?.getBoundingClientRect();
    let left = edge('.sidebar')?.right || 0, right = innerWidth;
    document.querySelectorAll('.workspace .card').forEach(el => {
      const r = el.getBoundingClientRect(); if (!r.width) return;
      if (r.left + r.width / 2 < innerWidth / 2) left = Math.max(left, r.right); else right = Math.min(right, r.left);
    });
    return { left, right, top: edge('.topbar')?.bottom || 0, bottom: edge('.chatbar')?.top || innerHeight };
  }
  // Zoom to your project (its whole line), centered in the open part of the map.
  function focusProject() {
    zoomedTo = state.zoomTo.n;
    const p = byId[state.zoomTo.id]; if (!p) return;
    const pts = (p.endpoints || []).filter(e => Number.isFinite(e.lat) && Number.isFinite(e.lon)).map(e => ({ lat: e.lat, lng: e.lon }));
    if (!pts.length && hasXY(p)) pts.push({ lat: p.lat_center, lng: p.lon_center });
    if (!pts.length) return;
    const a = openArea(), bounds = new google.maps.LatLngBounds();
    // A small box around the project so a single site or short line still gets a street-level view.
    pts.forEach(q => { bounds.extend({ lat: q.lat + 0.02, lng: q.lng + 0.02 }); bounds.extend({ lat: q.lat - 0.02, lng: q.lng - 0.02 }); });
    map.fitBounds(bounds, { left: a.left + 40, right: innerWidth - a.right + 40, top: a.top + 160, bottom: innerHeight - a.bottom + 40 });
    google.maps.event.addListenerOnce(map, 'idle', () => { if (map.getZoom() > 13) map.setZoom(13); positionHovercard(); });
  }

  // Predicted congestion (Traffic & timing only): colored road lines around the project opened there, with a popup per road.
  const LEVEL_COLOR = { heavy: '#d93025', moderate: '#f29900', light: '#f4c20d' };
  function drawCongestion(worker) {
    const id = !worker && state.page === 'feasibility' && state.trafficProject;
    const c = id && (state.congestion || {})[id];
    const key = c && c.roads ? id + ':' + c.roads.length + ':' + (c.summary || '').length : '';
    if (key === roadsKey) return;
    roadsKey = key;
    roadLines.forEach(l => (l.setMap ? l.setMap(null) : (l.map = null)));
    roadLines = [];
    if (infoWin) infoWin.close();
    if (!key) return;
    const p = byId[id];
    // The project itself: its line from substation to substation (dashed), and a label at each end.
    const projColor = p?.mine ? '#7c3aed' : p?.utility?.includes('Dominion') ? '#0f98a8' : '#df9c17';
    const proj = c.project || {};
    if ((proj.line || []).length >= 2) {
      roadLines.push(new google.maps.Polyline({ map, path: proj.line.map(([lat, lng]) => ({ lat, lng })), strokeOpacity: 0, zIndex: 30,
        icons: [{ icon: { path: 'M 0,-1 0,1', strokeOpacity: 1, strokeColor: projColor, strokeWeight: 4, scale: 3 }, offset: '0', repeat: '14px' }] }));
    }
    (proj.sites || []).forEach(s => {
      const el = document.createElement('div');
      el.className = 'site-label';
      el.innerHTML = `<span class="site-dot" style="background:${projColor}"></span>${esc(s.name)}`;
      roadLines.push(new AdvancedMarker({ map, position: { lat: s.lat, lng: s.lon }, content: el, zIndex: 900 }));
    });
    const popup = (r, at) => {
      infoWin = infoWin || new google.maps.InfoWindow({ maxWidth: 260 });
      infoWin.setContent(`<div class="congestion-pop"><b>Predicted congestion · ${r.level}</b><p>${esc(r.popup)}</p></div>`);
      infoWin.setPosition(at);
      infoWin.open({ map });
    };
    const order = { light: 0, moderate: 1, heavy: 2 };
    const pts = [];
    [...c.roads].sort((a, b) => order[a.level] - order[b.level]).forEach(r => {
      (r.lines || []).forEach(part => {
        const path = part.map(([lat, lng]) => ({ lat, lng }));
        pts.push(...path);
        // Quiet (light) roads are drawn thin and faint so the congested ones stand out.
        const quiet = r.level === 'light';
        const line = new google.maps.Polyline({ map, path, strokeColor: LEVEL_COLOR[r.level], strokeOpacity: quiet ? 0.55 : 0.9,
          strokeWeight: quiet ? 3 : r.role === 'crossed' ? 8 : 6, zIndex: 10 + order[r.level], clickable: true });
        line.addListener('click', e => popup(r, e.latLng));
        roadLines.push(line);
      });
    });
    // A dot where the project crosses each road, colored by congestion.
    (c.crossings || []).forEach(x => {
      const el = document.createElement('div');
      el.className = `xing-dot ${x.level}`;
      el.title = `${x.road_label} · ${x.where || ''}`;
      const road = c.roads.find(r => r.role === 'crossed' && r.road_label === x.road_label);
      const m = new AdvancedMarker({ map, position: { lat: x.point.lat, lng: x.point.lon }, content: el, zIndex: 800, gmpClickable: true });
      if (road) m.addListener('gmp-click', () => popup(road, { lat: x.point.lat, lng: x.point.lon }));
      roadLines.push(m);
    });
    // Popups open when a road is clicked; the Congestion card already lists every road.
    // Make sure the colored roads are in view too.
    if (pts.length) {
      const b = new google.maps.LatLngBounds();
      pts.forEach(q => b.extend(q));
      (proj.line || []).forEach(([lat, lng]) => b.extend({ lat, lng }));
      (p?.endpoints || []).forEach(e => Number.isFinite(e.lat) && b.extend({ lat: e.lat, lng: e.lon }));
      const a = openArea();
      map.fitBounds(b, { left: a.left + 40, right: innerWidth - a.right + 40, top: a.top + 60, bottom: innerHeight - a.bottom + 40 });
    }
  }

  // Zoom to the selected pair, leaving room for the two preview cards and the floating panels.
  function focusPair() {
    focusedPair = state.selectedOverlap.overlap_id;
    const pts = pairProjects().filter(hasXY).map(p => ({ lat: p.lat_center, lng: p.lon_center }));
    if (!pts.length) return;
    const edge = sel => document.querySelector(sel)?.getBoundingClientRect();
    let left = edge('.sidebar')?.right || 0, right = innerWidth;
    document.querySelectorAll('.workspace .card').forEach(el => {
      const r = el.getBoundingClientRect(); if (!r.width) return;
      if (r.left + r.width / 2 < innerWidth / 2) left = Math.max(left, r.right); else right = Math.min(right, r.left);
    });
    const top = edge('.topbar')?.bottom || 0, bottom = edge('.chatbar')?.top || innerHeight;
    let cardH = Math.max(150, ...[...document.querySelectorAll('.stage-map .hovercard')].map(c => c.offsetHeight)) + 30;
    cardH = Math.min(cardH, Math.max(40, (bottom - top - 60) / 2));
    const padding = { left: left + 40, right: innerWidth - right + 40, top: top + cardH, bottom: innerHeight - bottom + cardH };
    if (pts.length === 1) { map.panTo(pts[0]); map.setZoom(11); return; }
    const bounds = new google.maps.LatLngBounds(); pts.forEach(p => bounds.extend(p));
    map.fitBounds(bounds, padding);
    google.maps.event.addListenerOnce(map, 'idle', () => {
      if (map.getZoom() > 13) map.setZoom(13);
      cardZoom = map.getZoom(); updateCompact(); positionHovercard();
    });
  }

  function focusWorkerJob() {
    const job = state.selectedJob;
    const pin = document.querySelector(`.gpin[data-pid="${job.id}"]`);
    if (!pin) { if ((focusWorkerJob.tries = (focusWorkerJob.tries || 0) + 1) < 120) requestAnimationFrame(focusWorkerJob); return; }
    focusWorkerJob.tries = 0;
    const list = document.querySelector('.page-findjobs .joblayout > .card')?.getBoundingClientRect();
    const openLeft = Math.max((list?.right || 216) + 24, 240);
    const targetX = Math.min(innerWidth - 72, openLeft + 120);
    const alignPin = () => {
      const pinRect = pin.getBoundingClientRect();
      const dx = targetX - (pinRect.left + pinRect.width / 2);
      focusedWorkerJob = job.id;
      if (Math.abs(dx) > 24) map.panBy(-dx, 0);
      requestAnimationFrame(positionHovercard);
    };
    if (map.getZoom() < 12) {
      google.maps.event.addListenerOnce(map, 'idle', alignPin);
      map.setZoom(12);
    } else alignPin();
  }

  function hasCoords(o) {
    return Number.isFinite(o.lat_center ?? o.lat) && Number.isFinite(o.lon_center ?? o.lon);
  }

  const s = document.createElement('script');
  s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&loading=async&callback=initGridlockMap`;
  s.async = true;
  s.onerror = () => toast('Could not load Google Maps. Showing the illustrative map instead.');
  document.head.appendChild(s);
})();

// Small map inside the resource listing pop-up: pickup area plus search radius.
window.renderMiniMap = async el => {
  if (!el || !window.gridlockMapLive || !el.dataset.lat) return;
  const center = { lat: Number(el.dataset.lat), lng: Number(el.dataset.lng) };
  const radiusM = Number(el.dataset.radius) * 1609.34;
  const { Map, Circle } = await google.maps.importLibrary('maps');
  const { AdvancedMarkerElement } = await google.maps.importLibrary('marker');
  el.innerHTML = '';
  const mini = new Map(el, { center, zoom: 9, mapId: (window.GRIDLOCK_CONFIG || {}).googleMapsMapId || 'DEMO_MAP_ID', disableDefaultUI: true, gestureHandling: 'cooperative' });
  const circle = new Circle({ map: mini, center, radius: radiusM, strokeColor: '#1199a9', strokeWeight: 1.5, fillColor: '#1199a9', fillOpacity: 0.12 });
  mini.fitBounds(circle.getBounds(), 8);
  new AdvancedMarkerElement({ map: mini, position: center, content: Object.assign(document.createElement('div'), { className: 'gpin desc' }) });
};
