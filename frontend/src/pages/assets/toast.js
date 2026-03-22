(function(){
  const css = `.rr-toast{position:fixed;right:16px;top:16px;z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none}
  .rr-toast-item{min-width:220px;max-width:360px;padding:12px 14px;border-radius:12px;color:#0f172a;background:#fff;box-shadow:0 10px 30px rgba(2,6,23,.12);border:1px solid rgba(2,6,23,.06);animation:toastSlideIn .3s cubic-bezier(.2,.8,.2,1);pointer-events:auto;cursor:pointer;font-size:.875rem;line-height:1.35;transition:opacity .2s,transform .2s}
  .rr-toast-item.info{border-left:4px solid #2563eb}
  .rr-toast-item.success{border-left:4px solid #059669}
  .rr-toast-item.error{border-left:4px solid #ef4444}
  .rr-toast-item.removing{opacity:0;transform:translateX(20px)}
  :root[data-theme="dark"] .rr-toast-item{background:#1e293b;color:#e5e7eb;border-color:rgba(148,163,184,.15);box-shadow:0 10px 30px rgba(0,0,0,.35)}
  :root[data-theme="dark"] .rr-toast-item.info{border-left-color:#60a5fa}
  :root[data-theme="dark"] .rr-toast-item.success{border-left-color:#34d399}
  :root[data-theme="dark"] .rr-toast-item.error{border-left-color:#f87171}
  @keyframes toastSlideIn{from{opacity:0;transform:translateX(30px)}to{opacity:1;transform:translateX(0)}}
  @media(max-width:480px){.rr-toast{right:8px;left:8px;top:8px}.rr-toast-item{min-width:auto;max-width:none}}`;
  const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);
  const wrap = document.createElement('div'); wrap.className = 'rr-toast'; wrap.setAttribute('role','status'); wrap.setAttribute('aria-live','polite'); document.body.appendChild(wrap);
  function showToast(type, msg, timeout){
    if (!timeout) timeout = (type === 'error') ? 5000 : 2800;
    const el = document.createElement('div'); el.className = `rr-toast-item ${type||'info'}`; el.textContent = msg;
    el.setAttribute('role', type === 'error' ? 'alert' : 'status');
    wrap.appendChild(el);
    const remove = () => { el.classList.add('removing'); setTimeout(() => el.remove(), 200); };
    const t = setTimeout(remove, timeout);
    el.addEventListener('click', () => { clearTimeout(t); remove(); });
  }
  window.showToast = showToast;
})();
