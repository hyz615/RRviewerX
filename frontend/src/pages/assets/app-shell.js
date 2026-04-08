(function () {
  const NAV_ITEMS = [
    { id: 'workspace', href: 'workspace.html', label: 'nav_home' },
    { id: 'upload', href: 'upload.html', label: 'nav_upload' },
    { id: 'review', href: 'review.html', label: 'nav_review' },
    { id: 'chat', href: 'chat.html', label: 'nav_chat' },
    { id: 'history', href: 'history.html', label: 'nav_history' },
  ];

  const SHELL_KEYS = [
    'rr_sources_v2',
    'rr_draft_text_v2',
    'rr_current_review_v2',
    'rr_subject_context_v1',
    'rr_subject_sessions_v1',
    'rr_draft',
    'review_id',
    'review',
    'review_text',
  ];

  const shellState = {
    ai: null,
    quota: null,
    trial: null,
  };

  function t(key) {
    return window.__i18n__ ? window.__i18n__.t(key) : key;
  }

  function getToken() {
    try {
      const token = localStorage.getItem('token');
      if (token) {
        return token;
      }
    } catch (_) {}

    const match = document.cookie.match(/(?:^|; )rr_token=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function isLoggedIn() {
    return Boolean(getToken());
  }

  function authHeaders(base) {
    const headers = { ...(base || {}) };
    const token = getToken();
    if (token) {
      headers.Authorization = 'Bearer ' + token;
    }
    return headers;
  }

  function logout() {
    try {
      localStorage.removeItem('token');
    } catch (_) {}

    try {
      document.cookie = 'rr_token=; path=/; max-age=0; samesite=lax';
    } catch (_) {}

    try {
      SHELL_KEYS.forEach(function (key) {
        sessionStorage.removeItem(key);
      });
      Object.keys(sessionStorage).forEach(function (key) {
        if (key.indexOf('rr_chat_v2_') === 0) {
          sessionStorage.removeItem(key);
        }
      });
    } catch (_) {}
  }

  async function fetchJSON(path, options, extra) {
    const requestOptions = { ...(options || {}) };
    const config = { ...(extra || {}) };
    const response = await window.apiFetch(path, { credentials: 'include', ...requestOptions }, config);
    const raw = await response.text().catch(function () {
      return '';
    });

    let data = null;
    if (raw) {
      try {
        data = JSON.parse(raw);
      } catch (_) {
        data = config.allowText ? raw : { text: raw };
      }
    }

    const errorMessage = data && typeof data === 'object' && !Array.isArray(data)
      ? (data.error || data.detail || data.message)
      : '';

    if (!response.ok || (data && typeof data === 'object' && !Array.isArray(data) && data.ok === false)) {
      throw new Error(errorMessage || response.statusText || 'Request failed');
    }

    return data;
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatRelativeDate(value) {
    if (!value) {
      return '—';
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return '—';
    }

    const locale = (document.documentElement.lang || '').toLowerCase().indexOf('en') === 0 ? 'en-US' : 'zh-CN';
    return new Intl.DateTimeFormat(locale, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  }

  function setTheme(theme) {
    const next = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem('rr_theme', next);
    } catch (_) {}
  }

  function getTheme() {
    return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  }

  function updateThemeButton() {
    const button = document.getElementById('btn-dark');
    if (!button) {
      return;
    }
    button.textContent = getTheme() === 'dark' ? '☀️' : '🌙';
  }

  function updateLanguageButtons() {
    const zh = document.getElementById('lang-top-zh');
    const en = document.getElementById('lang-top-en');
    const lang = (document.documentElement.lang || '').toLowerCase();
    const isEn = lang.indexOf('en') === 0;

    if (zh) {
      zh.classList.toggle('active', !isEn);
    }
    if (en) {
      en.classList.toggle('active', isEn);
    }
  }

  function setLanguage(lang) {
    if (!window.__i18n__) {
      return;
    }
    window.__i18n__.setLang(lang);
    window.__i18n__.applyI18n(document);
    updateLanguageButtons();
    updateShellStatus();
    document.dispatchEvent(new CustomEvent('rr:langchange', { detail: { lang: lang } }));
  }

  function bindScrollBehavior() {
    const topbar = document.getElementById('app-topbar');
    if (!topbar) {
      return;
    }

    let lastY = window.scrollY || window.pageYOffset;
    const onScroll = function () {
      const current = Math.max(0, window.scrollY || window.pageYOffset);
      topbar.classList.toggle('topbar--elevated', current > 4);
      const delta = current - lastY;

      if (current < 32) {
        topbar.classList.remove('topbar--hidden');
        lastY = current;
        return;
      }

      if (delta > 6 && current > 84) {
        topbar.classList.add('topbar--hidden');
      } else if (delta < -6) {
        topbar.classList.remove('topbar--hidden');
      }
      lastY = current;
    };

    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  function renderShell(pageId) {
    const top = document.getElementById('app-shell-top');
    const bottom = document.getElementById('app-shell-bottom');

    if (top) {
      top.innerHTML = [
        '<nav class="topbar shell-topbar" id="app-topbar" role="navigation" aria-label="Primary navigation">',
        '  <div class="page-wrap shell-topbar__row">',
        '    <a href="workspace.html" class="shell-brand">',
        '      <img src="assets/logo.png" alt="RRviewer" class="shell-brand-logo" />',
        '      <div class="shell-brand__text">',
        '        <span class="shell-brand__name" data-i18n="app_name">RRviewer</span>',
        '        <span class="shell-brand__tag" data-i18n="brand_tag">RUR1 INNOVATION & Skyru AI</span>',
        '      </div>',
        '    </a>',
        '    <div class="shell-status" aria-live="polite">',
        '      <span id="ai-dot" class="status-dot warn"></span>',
        '      <span id="ai-text">AI</span>',
        '      <span class="shell-status__divider"></span>',
        '      <span class="shell-status__usage">',
        '        <span id="usage-label" data-i18n="monthly_usage">本月用量</span>',
        '        <strong id="usage-val">—</strong>',
        '      </span>',
        '      <span id="vip-badge-top" class="shell-vip-badge hidden"></span>',
        '    </div>',
        '    <div class="shell-utility">',
        '      <a href="support.html" class="shell-inline-link" data-i18n="menu_support">工单</a>',
        '      <button id="btn-dark" class="shell-icon-btn" type="button" title="Theme" aria-label="Toggle theme">🌙</button>',
        '      <div class="shell-lang" role="group" aria-label="Language">',
        '        <button id="lang-top-zh" type="button">中文</button>',
        '        <button id="lang-top-en" type="button">EN</button>',
        '      </div>',
        '      <a id="link-login" href="index.html?login=1" class="shell-inline-link" data-i18n="login_register">登录/注册</a>',
        '      <a id="link-logout" href="#" class="shell-inline-link hidden" data-i18n="logout">退出</a>',
        '    </div>',
        '  </div>',
        '</nav>',
        '<div class="topbar-spacer"></div>',
      ].join('');
    }

    if (bottom) {
      bottom.innerHTML = '<footer class="app-footer">© RUR1 INNOVATION & Skyru AI</footer>';
    }
  }

  // Map pageId -> CSS banner/badge subject key
  function subjectCssKey(subjectCode) {
    const map = {
      math: 'math', physics: 'physics', chemistry: 'chemistry',
      biology: 'biology', chinese: 'chinese', english: 'english',
      history: 'history', geography: 'geography', politics: 'politics',
      computer_science: 'cs', economics: 'economics',
    };
    return map[subjectCode] || 'other';
  }

  function renderCourseHeader(pageId) {
    const container = document.getElementById('course-header');
    if (!container) {
      return;
    }

    if (!isLoggedIn()) {
      container.innerHTML = '';
      return;
    }

    const context = window.RRState ? window.RRState.getSubjectContext() : null;
    const INNER_TABS = [
      { id: 'upload',  href: 'upload.html',  labelKey: 'course_tab_materials' },
      { id: 'review',  href: 'review.html',  labelKey: 'course_tab_generate' },
      { id: 'chat',    href: 'chat.html',    labelKey: 'course_tab_chat' },
      { id: 'history', href: 'history.html', labelKey: 'course_tab_history' },
    ];

    if (!context || !context.subjectCode) {
      container.innerHTML = [
        '<div class="no-course-banner">',
        '  <div class="no-course-banner__icon">📚</div>',
        '  <div class="no-course-banner__text">',
        '    <div class="no-course-banner__title" data-i18n="no_course_selected">' + t('no_course_selected') + '</div>',
        '    <div class="no-course-banner__sub" data-i18n="please_select_course_first">' + t('please_select_course_first') + '</div>',
        '  </div>',
        '  <a href="workspace.html" class="soft-btn" style="font-size:0.8rem;" data-i18n="go_to_courses">' + t('go_to_courses') + '</a>',
        '</div>',
      ].join('');
      return;
    }

    const cssKey = subjectCssKey(context.subjectCode);
    const subjectLabel = window.RRState
      ? t(window.RRState.getSubjectLabelKey(context.subjectCode))
      : context.subjectCode;
    const courseName = context.courseName || subjectLabel;

    const tabs = INNER_TABS.map(function (tab) {
      const active = tab.id === pageId ? ' course-tab--active' : '';
      return '<a href="' + tab.href + '" class="course-tab' + active + '">' + t(tab.labelKey) + '</a>';
    }).join('');

    container.innerHTML = [
      '<div class="course-header">',
      '  <div class="course-header__inner">',
      '    <div class="course-header__context">',
      '      <a href="workspace.html" class="course-back-btn">' + t('back_to_courses') + '</a>',
      '      <span class="course-context-divider"></span>',
      '      <span class="course-badge course-badge--' + cssKey + '">' + escapeHtml(subjectLabel) + '</span>',
      '      <span class="course-header__name" title="' + escapeHtml(courseName) + '">' + escapeHtml(courseName) + '</span>',
      '    </div>',
      '    <div class="course-context-divider"></div>',
      '    <nav class="course-tabs" aria-label="Course navigation">',
      '      ' + tabs,
      '    </nav>',
      '  </div>',
      '</div>',
    ].join('');
  }

  function updateShellStatus() {
    const aiDot = document.getElementById('ai-dot');
    const aiText = document.getElementById('ai-text');
    const usageLabel = document.getElementById('usage-label');
    const usageValue = document.getElementById('usage-val');
    const vipBadge = document.getElementById('vip-badge-top');
    const loginLink = document.getElementById('link-login');
    const logoutLink = document.getElementById('link-logout');

    if (shellState.ai && aiDot && aiText) {
      const provider = String(shellState.ai.provider || 'mock').toLowerCase();
      const providerLabel = provider === 'openai'
        ? t('ai_provider_openai')
        : provider === 'deepseek'
          ? t('ai_provider_deepseek')
          : t('ai_provider_mock');

      if (shellState.ai.ready && provider !== 'mock') {
        aiDot.className = 'status-dot ok';
        aiText.textContent = t('ai_status_connected') + ' · ' + providerLabel;
      } else if (provider === 'mock') {
        aiDot.className = 'status-dot warn';
        aiText.textContent = t('ai_status_mock');
      } else {
        aiDot.className = 'status-dot err';
        aiText.textContent = t('ai_status_missing');
      }
    }

    if (usageLabel && usageValue && vipBadge) {
      usageLabel.textContent = t('shell_mode_label');
      usageValue.textContent = isLoggedIn() ? t('shell_mode_member') : t('shell_mode_guest');
      vipBadge.classList.add('hidden');
      vipBadge.textContent = '';
    }

    if (loginLink && logoutLink) {
      if (isLoggedIn()) {
        loginLink.classList.add('hidden');
        logoutLink.classList.remove('hidden');
      } else {
        loginLink.classList.remove('hidden');
        logoutLink.classList.add('hidden');
      }
    }
  }

  async function refreshShellStatus() {
    try {
      shellState.ai = await fetchJSON('/status/ai');
    } catch (_) {
      shellState.ai = null;
    }

    try {
      shellState.quota = await fetchJSON('/status/quota', isLoggedIn() ? { headers: authHeaders() } : undefined);
    } catch (_) {
      shellState.quota = null;
    }

    shellState.trial = null;

    updateShellStatus();
    return {
      loggedIn: isLoggedIn(),
      ai: shellState.ai,
      quota: shellState.quota,
      trial: shellState.trial,
    };
  }

  function bindShellInteractions() {
    const themeButton = document.getElementById('btn-dark');
    const zhButton = document.getElementById('lang-top-zh');
    const enButton = document.getElementById('lang-top-en');
    const logoutLink = document.getElementById('link-logout');

    if (themeButton) {
      updateThemeButton();
      themeButton.addEventListener('click', function () {
        setTheme(getTheme() === 'dark' ? 'light' : 'dark');
        updateThemeButton();
      });
    }

    if (zhButton) {
      zhButton.addEventListener('click', function () {
        setLanguage('zh');
      });
    }

    if (enButton) {
      enButton.addEventListener('click', function () {
        setLanguage('en');
      });
    }

    if (logoutLink) {
      logoutLink.addEventListener('click', function (event) {
        event.preventDefault();
        logout();
        location.reload();
      });
    }

    updateLanguageButtons();
    bindScrollBehavior();
  }

  async function initPage(pageId) {
    renderShell(pageId);
    if (window.__i18n__) {
      window.__i18n__.applyI18n(document);
    }
    // Render course header for inner pages (not workspace)
    const innerPages = ['upload', 'review', 'chat', 'history'];
    if (innerPages.indexOf(pageId) !== -1) {
      renderCourseHeader(pageId);
    }
    bindShellInteractions();
    updateThemeButton();
    updateLanguageButtons();
    // Re-render on language change
    window.addEventListener('rr:langchange', function () {
      if (innerPages.indexOf(pageId) !== -1) {
        renderCourseHeader(pageId);
      }
    });
    return refreshShellStatus();
  }

  function getMarkedParser() {
    if (!window.marked) {
      return null;
    }
    if (typeof window.marked.parse === 'function') {
      return window.marked.parse.bind(window.marked);
    }
    if (typeof window.marked === 'function') {
      return window.marked;
    }
    return null;
  }

  function renderMarkdown(target, text) {
    if (!target) {
      return;
    }

    const value = String(text || '');
    if (!value) {
      target.innerHTML = '';
      return;
    }

    const parse = getMarkedParser();
    if (!parse || !window.DOMPurify) {
      target.textContent = value;
      return;
    }

    let html = value;
    try {
      html = parse(value, { breaks: true, gfm: true });
    } catch (_) {
      html = escapeHtml(value);
    }

    target.innerHTML = window.DOMPurify.sanitize(html);

    if (window.hljs) {
      target.querySelectorAll('pre code').forEach(function (block) {
        window.hljs.highlightElement(block);
      });
    }

    if (window.renderMathInElement) {
      try {
        window.renderMathInElement(target, {
          delimiters: [
            { left: '$$', right: '$$', display: true },
            { left: '$', right: '$', display: false },
          ],
          throwOnError: false,
        });
      } catch (_) {}
    }
  }

  function downloadText(filename, content) {
    const blob = new Blob([String(content || '')], { type: 'text/plain;charset=utf-8' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function getPrintHeadMarkup() {
    return Array.from(document.querySelectorAll('link[rel="stylesheet"], style')).map(function (node) {
      return node.outerHTML;
    }).join('\n');
  }

  function waitForPrintWindow(popup, callback) {
    let done = false;
    const finish = function () {
      if (done) {
        return;
      }
      done = true;
      callback();
    };

    const pending = [];
    const images = Array.from(popup.document.images || []);
    images.forEach(function (image) {
      if (image.complete) {
        return;
      }
      pending.push(new Promise(function (resolve) {
        image.addEventListener('load', resolve, { once: true });
        image.addEventListener('error', resolve, { once: true });
      }));
    });

    if (popup.document.fonts && popup.document.fonts.ready) {
      pending.push(popup.document.fonts.ready.catch(function () {}));
    }

    Promise.all(pending).finally(function () {
      popup.setTimeout(finish, 80);
    });

    popup.setTimeout(finish, 1500);
  }

  function printElement(title, element) {
    if (!element) {
      return false;
    }

    const popup = window.open('', '_blank');
    if (!popup) {
      return false;
    }

    const headMarkup = getPrintHeadMarkup();
    const bodyClass = escapeHtml(document.body ? document.body.className || '' : '');
    const lang = escapeHtml(document.documentElement.lang || 'zh-cn');
    const baseHref = escapeHtml(document.baseURI || window.location.href);
    let queued = false;

    const queuePrint = function () {
      if (queued) {
        return;
      }
      queued = true;
      waitForPrintWindow(popup, function () {
        popup.focus();
        popup.print();
      });
    };

    popup.addEventListener('afterprint', function () {
      popup.close();
    }, { once: true });

    popup.document.open();
    popup.document.write([
      '<!doctype html>',
      '<html lang="' + lang + '">',
      '<head>',
      '  <meta charset="utf-8" />',
      '  <base href="' + baseHref + '" />',
      '  <title>' + escapeHtml(title || 'RRviewer') + '</title>',
      headMarkup,
      '  <style>',
      '    @page{size:auto;margin:14mm;}',
      '    html,body,body.page-surface{background:#fff !important;color:#0f172a !important;}',
      '    body{margin:0;font-family:Segoe UI,Arial,sans-serif;line-height:1.6;-webkit-print-color-adjust:exact;print-color-adjust:exact;}',
      '    .print-sheet{padding:0;}',
      '    .result-frame{min-height:0 !important;padding:0 !important;border:none !important;background:none !important;overflow:visible !important;}',
      '    .prose{max-width:none !important;}',
      '    .topbar,.topbar-spacer,.course-header,.app-footer,.flow-dock{display:none !important;}',
      '    pre{white-space:pre-wrap !important;word-break:break-word !important;background:#f8fafc !important;padding:1rem !important;border-radius:12px !important;}',
      '    code{font-family:Consolas,Monaco,monospace;}',
      '    table{width:100%;border-collapse:collapse;}',
      '    th,td{border:1px solid #cbd5e1;padding:.45rem .6rem;text-align:left;vertical-align:top;}',
      '    img,svg{max-width:100% !important;height:auto !important;}',
      '    a{color:inherit !important;text-decoration:none !important;}',
      '  </style>',
      '</head>',
      '<body class="' + bodyClass + '">',
      '<main class="print-sheet">',
      element.innerHTML,
      '</main>',
      '</body>',
      '</html>',
    ].join(''));
    popup.document.close();

    if (popup.document.readyState === 'complete') {
      queuePrint();
    } else {
      popup.addEventListener('load', queuePrint, { once: true });
      popup.setTimeout(queuePrint, 1500);
    }

    return true;
  }

  function handleStreamChunk(chunk, handlers) {
    if (!chunk.trim()) {
      return;
    }

    let eventName = 'message';
    const lines = [];

    chunk.split(/\r?\n/).forEach(function (line) {
      if (line.indexOf('event:') === 0) {
        eventName = line.slice(6).trim();
      } else if (line.indexOf('data:') === 0) {
        lines.push(line.slice(5).trimStart());
      }
    });

    const handler = handlers[eventName] || handlers.message;
    if (handler) {
      handler(lines.join('\n'));
    }
  }

  function streamSSE(path, body, handlers) {
    const controller = new AbortController();
    const promise = (async function () {
      const response = await fetch(window.API_BASE + path, {
        method: 'POST',
        credentials: 'include',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(body || {}),
        signal: controller.signal,
      });

      if (!response.ok) {
        const message = await response.text().catch(function () {
          return response.statusText || 'Stream failed';
        });
        throw new Error(message || response.statusText || 'Stream failed');
      }

      if (!response.body) {
        throw new Error('Streaming is not supported in this browser');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const result = await reader.read();
        if (result.done) {
          break;
        }
        buffer += decoder.decode(result.value, { stream: true });

        while (buffer.indexOf('\n\n') !== -1) {
          const boundary = buffer.indexOf('\n\n');
          const chunk = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          handleStreamChunk(chunk, handlers || {});
        }
      }

      if (buffer.trim()) {
        handleStreamChunk(buffer, handlers || {});
      }
    })();

    return {
      cancel: function () {
        controller.abort();
      },
      done: promise,
    };
  }

  window.RRApp = {
    authHeaders: authHeaders,
    downloadText: downloadText,
    escapeHtml: escapeHtml,
    fetchJSON: fetchJSON,
    formatRelativeDate: formatRelativeDate,
    getShellState: function () {
      return { ...shellState };
    },
    getTheme: getTheme,
    getToken: getToken,
    initPage: initPage,
    isLoggedIn: isLoggedIn,
    logout: logout,
    printElement: printElement,
    refreshShellStatus: refreshShellStatus,
    renderCourseHeader: renderCourseHeader,
    renderMarkdown: renderMarkdown,
    setLanguage: setLanguage,
    streamSSE: streamSSE,
    t: t,
  };
})();