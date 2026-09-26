// Google Maps background layer. Loads only when config.js provides a key;
// otherwise the illustrative image in styles.css stays in place.
(function () {
  const config = window.GRIDLOCK_CONFIG || {};
  const key = (config.googleMapsApiKey || '').trim();
  if (!key) return;

  let map, AdvancedMarker, markers = [], focusedPair = null, cardZoom = null, cardKey = '';
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
    render();
  };

  // Called from render() so markers follow role and selection changes.
  window.syncGoogleMap = () => {
    if (!map) return;
    markers.forEach(m => (m.map = null));
    const worker = state.role === 'worker';
    const items = worker
      ? state.jobs.filter(hasCoords).map(j => ({
          id: j.id, title: j.name, lat: j.lat, lng: j.lon,
          cls: j.id === state.selectedJob.id ? 'desc selected' : 'gpc',
          onClick: () => { state.hoverClosed = false; state.selectedJob = j; render(); }
        }))
      : projects.filter(hasCoords).map(p => ({
          id: p.project_id, title: p.project_name, lat: p.lat_center, lng: p.lon_center,
          cls: `${p.utility.includes('Dominion') ? 'desc' : 'gpc'} ${selectedPinIds().includes(p.project_id) ? 'selected' : ''}`,
          onClick: () => { state.hoverClosed = false; state.pairFocus = false; state.hoverProject = state.selectedProject = p; render(); }
        }));
    markers = items.map(it => {
      const el = document.createElement('div');
      el.className = `gpin ${it.cls}`;
      el.dataset.pid = it.id;
      const marker = new AdvancedMarker({ map, position: { lat: it.lat, lng: it.lng }, content: el, title: it.title, gmpClickable: true });
      marker.addEventListener('gmp-click', it.onClick);
      return marker;
    });
    const key = [...document.querySelectorAll('.stage-map .hovercard')].map(c => c.dataset.anchor).join();
    if (key !== cardKey) { cardKey = key; cardZoom = key ? map.getZoom() : null; updateCompact(); }
    if (!worker && state.pairFocus && state.selectedOverlap.overlap_id !== focusedPair) focusPair();
    if (!state.pairFocus) focusedPair = null;
    // Marker elements attach asynchronously; position the card once the selected one is laid out.
    let tries = 0;
    (function waitForPin() {
      const pin = document.querySelector('.gpin.selected');
      if (pin && pin.getBoundingClientRect().width) positionHovercard();
      else if (tries++ < 60) requestAnimationFrame(waitForPin);
    })();
  };

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
