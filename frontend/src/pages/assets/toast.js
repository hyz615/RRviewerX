(function(){
  const css = `.rr-toast{position:fixed;right:16px;top:16px;z-index:9999;display:flex;flex-direction:column;gap:10px;pointer-events:none}
  .rr-toast-item{min-width:220px;max-width:360px;padding:12px 14px;border-radius:12px;color:#0f172a;background:#fff;box-shadow:0 10px 30px rgba(2,6,23,.12);border:1px solid rgba(2,6,23,.06);animation:toastSlideIn .3s cubic-bezier(.2,.8,.2,1);pointer-events:auto;cursor:pointer;font-size:.875rem;line-height:1.35;transition:opacity .2s,transform .2s}
  .rr-toast-item.info{border-left:4px solid #2563eb}
  .rr-toast-item.success{border-left:4px solid #059669}
  .rr-toast-item.error{border-left:4px solid #ef4444}
  .rr-toast-item.rr-toast-card{display:grid;grid-template-columns:auto 1fr;gap:12px;align-items:flex-start;min-width:280px;max-width:420px;padding:14px 16px;border-radius:18px}
  .rr-toast-item__icon{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:999px;font-size:1rem;font-weight:700;flex:none}
  .rr-toast-item.info .rr-toast-item__icon{color:#1d4ed8;background:rgba(37,99,235,.12)}
  .rr-toast-item.success .rr-toast-item__icon{color:#047857;background:rgba(5,150,105,.12)}
  .rr-toast-item.error .rr-toast-item__icon{color:#b91c1c;background:rgba(239,68,68,.12)}
  .rr-toast-item__body{min-width:0;display:flex;flex-direction:column;gap:3px}
  .rr-toast-item__title{font-size:.95rem;font-weight:700;line-height:1.3}
  .rr-toast-item__message{font-size:.875rem;font-weight:600;line-height:1.4;overflow-wrap:anywhere}
  .rr-toast-item__detail{font-size:.78rem;line-height:1.45;color:#475569;overflow-wrap:anywhere}
  .rr-toast-item.removing{opacity:0;transform:translateX(20px)}
  :root[data-theme="dark"] .rr-toast-item{background:#1e293b;color:#e5e7eb;border-color:rgba(148,163,184,.15);box-shadow:0 10px 30px rgba(0,0,0,.35)}
  :root[data-theme="dark"] .rr-toast-item.info{border-left-color:#60a5fa}
  :root[data-theme="dark"] .rr-toast-item.success{border-left-color:#34d399}
  :root[data-theme="dark"] .rr-toast-item.error{border-left-color:#f87171}
  :root[data-theme="dark"] .rr-toast-item.info .rr-toast-item__icon{color:#93c5fd;background:rgba(96,165,250,.18)}
  :root[data-theme="dark"] .rr-toast-item.success .rr-toast-item__icon{color:#6ee7b7;background:rgba(52,211,153,.18)}
  :root[data-theme="dark"] .rr-toast-item.error .rr-toast-item__icon{color:#fca5a5;background:rgba(248,113,113,.18)}
  :root[data-theme="dark"] .rr-toast-item__detail{color:#94a3b8}
  @keyframes toastSlideIn{from{opacity:0;transform:translateX(30px)}to{opacity:1;transform:translateX(0)}}
  @media(max-width:480px){.rr-toast{right:8px;left:8px;top:8px}.rr-toast-item{min-width:auto;max-width:none}.rr-toast-item.rr-toast-card{min-width:auto;max-width:none;padding:13px 14px}}`;
  const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);
  const wrap = document.createElement('div'); wrap.className = 'rr-toast'; wrap.setAttribute('role','status'); wrap.setAttribute('aria-live','polite'); document.body.appendChild(wrap);

  function normalizeToastContent(content) {
    if (content && typeof content === 'object' && !Array.isArray(content)) {
      return {
        title: String(content.title || '').trim(),
        message: String(content.message || '').trim(),
        detail: String(content.detail || '').trim(),
        timeout: Number(content.timeout || 0),
      };
    }
    return {
      title: '',
      message: String(content || '').trim(),
      detail: '',
      timeout: 0,
    };
  }

  function getToastIcon(type) {
    if (type === 'error') return '!';
    if (type === 'success') return '✓';
    return 'i';
  }

  function buildToastContent(el, type, content) {
    const isCard = Boolean(content.title || content.detail);
    if (!isCard) {
      el.textContent = content.message;
      return;
    }

    el.classList.add('rr-toast-card');

    const icon = document.createElement('span');
    icon.className = 'rr-toast-item__icon';
    icon.textContent = getToastIcon(type);

    const body = document.createElement('div');
    body.className = 'rr-toast-item__body';

    if (content.title) {
      const title = document.createElement('div');
      title.className = 'rr-toast-item__title';
      title.textContent = content.title;
      body.appendChild(title);
    }

    if (content.message) {
      const message = document.createElement('div');
      message.className = 'rr-toast-item__message';
      message.textContent = content.message;
      body.appendChild(message);
    }

    if (content.detail) {
      const detail = document.createElement('div');
      detail.className = 'rr-toast-item__detail';
      detail.textContent = content.detail;
      body.appendChild(detail);
    }

    el.appendChild(icon);
    el.appendChild(body);
  }

  function showToast(type, msg, timeout){
    const content = normalizeToastContent(msg);
    if (!content.title && !content.message && !content.detail) {
      return;
    }
    if (!timeout) timeout = content.timeout || ((type === 'error') ? 5000 : (content.title || content.detail ? 4200 : 2800));
    const el = document.createElement('div'); el.className = `rr-toast-item ${type||'info'}`;
    buildToastContent(el, type || 'info', content);
    el.setAttribute('role', type === 'error' ? 'alert' : 'status');
    wrap.appendChild(el);
    const remove = () => { el.classList.add('removing'); setTimeout(() => el.remove(), 200); };
    const t = setTimeout(remove, timeout);
    el.addEventListener('click', () => { clearTimeout(t); remove(); });
  }
  window.showToast = showToast;
})();
