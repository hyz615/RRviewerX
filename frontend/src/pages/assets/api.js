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
  function _isAbortLike(e){
    if (!e) return false;
    if (e.name === 'AbortError') return true;
    var m = String(e.message || '').toLowerCase();
    return m.indexOf('abort') !== -1 || m.indexOf('signal') !== -1;
  }
  function _abortError(msg){
    var err = new Error(msg);
    err.name = 'AbortError';
    return err;
  }
  window._isAbortLike = _isAbortLike;
  async function apiFetch(path, opts={}, {timeout=45000}={}){
    const ctrl = new AbortController();
    let timedOut = false;
    const id = timeout > 0 ? setTimeout(function(){ timedOut = true; ctrl.abort(); }, timeout) : 0;
    try{
      const res = await fetch(BASE + path, { credentials: 'include', ...opts, signal: ctrl.signal });
      return res;
    } catch(e) {
      if (timedOut) throw _abortError('Request timed out');
      if (_isAbortLike(e)) throw _abortError('Request aborted');
      throw e;
    } finally {
      clearTimeout(id);
    }
  }
  window.API_BASE = BASE;
  window.apiFetch = apiFetch;
})();
