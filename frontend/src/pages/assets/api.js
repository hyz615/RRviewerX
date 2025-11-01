(function(){
  function computeBase(){
    if (window.RR_API) return window.RR_API;
    const host = location.hostname || '';
    const isLocalhost = (host === 'localhost' || host === '127.0.0.1');
    const isIPv4 = /^\d{1,3}(?:\.\d{1,3}){3}$/.test(host);
    const isIPv6 = host.includes(':'); // rough check; browsers provide IPv6 without brackets in hostname
    // For localhost or any IP, talk to backend on :8000 directly
    if (isLocalhost || isIPv4 || isIPv6){
      const h = isIPv6 ? `[${host}]` : host;
      return `${location.protocol}//${h}:8000`;
    }
  // For real domains, force default port (no :8000) to hit reverse-proxy on 443/80
  // Using protocol + hostname avoids inheriting any non-default port from current page
  return `${location.protocol}//${location.hostname}`;
  }
  const BASE = computeBase();
  async function apiFetch(path, opts={}, {timeout=45000}={}){
    const ctrl = new AbortController();
    const id = setTimeout(()=>ctrl.abort(), timeout);
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
