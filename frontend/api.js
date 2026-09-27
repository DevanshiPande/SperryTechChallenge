// Gridlock backend client. Every call sends the current identity headers (X-Company-Id / X-Worker-Id)
// and throws an Error with .code, .status and the backend's message on failure.
window.GridlockAPI = (() => {
  const cfg = window.GRIDLOCK_CONFIG || {};
  const BASE = String(cfg.apiUrl || 'http://localhost:8000').replace(/\/+$/, '');
  const identity = { companyId: null, workerId: null };

  async function request(method, path, body, { timeoutMs = 90000 } = {}) {
    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (identity.companyId) headers['X-Company-Id'] = identity.companyId;
    if (identity.workerId) headers['X-Worker-Id'] = identity.workerId;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    let res;
    try {
      res = await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: ctrl.signal });
    } catch (e) {
      const err = new Error(e.name === 'AbortError' ? 'The server took too long to answer.' : `Cannot reach the ContractMap backend at ${BASE}. Is it running?`);
      err.code = 'NETWORK'; err.status = 0; throw err;
    } finally { clearTimeout(timer); }
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = null; }
    if (!res.ok) {
      const e = (data && data.error) || {};
      const err = new Error(e.message || `Request failed (${res.status})`);
      err.code = e.code || 'HTTP_' + res.status; err.status = res.status; throw err;
    }
    return data;
  }

  const qs = params => {
    const p = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== '');
    return p.length ? '?' + p.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&') : '';
  };

  return {
    base: BASE,
    identity,
    setIdentity({ companyId = null, workerId = null }) { identity.companyId = companyId; identity.workerId = workerId; },
    get: (path, params) => request('GET', path + qs(params)),
    post: (path, body, opts) => request('POST', path, body === undefined ? {} : body, opts),
    patch: (path, body) => request('PATCH', path, body || {}),
    del: path => request('DELETE', path),
    exportUrl: () => BASE + '/export/overlaps.xlsx',
  };
})();
