(function(){
  function computeBase(){
    if (window.RR_API) return window.RR_API;
    const host = location.hostname || '';
    const isLocalhost = (host === 'localhost' || host === '127.0.0.1');
    // localhost/127.0.0.1 → talk to backend on :8000 directly (dev mode)
    if (isLocalhost){
      return `${location.protocol}//${host}:8000`;
    }
    // For everything else (IPs, domains), assume reverse-proxy on same origin
    return `${location.protocol}//${location.host}`;
  }
  const BASE = computeBase();
  async function apiFetch(path, opts={}, {timeout=45000}={}){
    const ctrl = new AbortController();
    const id = timeout > 0 ? setTimeout(()=>ctrl.abort('Request timed out'), timeout) : 0;
    try{
      const res = await fetch(BASE + path, { credentials: 'include', ...opts, signal: ctrl.signal });
      return res;
    } finally {
      clearTimeout(id);
    }
  }
  window.API_BASE = BASE;
  window.apiFetch = apiFetch;
})();
