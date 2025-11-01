(function(){
  const css = `.rr-toast{position:fixed;right:16px;top:16px;z-index:9999;display:flex;flex-direction:column;gap:8px}
  .rr-toast-item{min-width:220px;max-width:360px;padding:10px 12px;border-radius:10px;color:#0f172a;background:#fff;box-shadow:0 10px 25px rgba(2,6,23,.08);border:1px solid rgba(2,6,23,.06);animation:toastIn .2s ease-out}
  .rr-toast-item.info{border-left:4px solid #2563eb}
  .rr-toast-item.success{border-left:4px solid #059669}
  .rr-toast-item.error{border-left:4px solid #ef4444}
  @keyframes toastIn{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}`;
  const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);
  const wrap = document.createElement('div'); wrap.className = 'rr-toast'; document.body.appendChild(wrap);
  function showToast(type, msg, timeout=2800){
    const el = document.createElement('div'); el.className = `rr-toast-item ${type||'info'}`; el.textContent = msg;
    wrap.appendChild(el); const t = setTimeout(()=>{ el.remove(); }, timeout);
    el.addEventListener('click', ()=>{ clearTimeout(t); el.remove(); });
  }
  window.showToast = showToast;
})();
