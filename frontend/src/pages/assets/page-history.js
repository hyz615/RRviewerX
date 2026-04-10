document.addEventListener('DOMContentLoaded', async function () {
  await window.RRApp.initPage('history');

  const loginNote = document.getElementById('history-login-note');
  const list = document.getElementById('history-list');
  const empty = document.getElementById('history-empty');
  const search = document.getElementById('history-search');
  const status = document.getElementById('history-status');
  const favoritesButton = document.getElementById('btn-history-favorites');
  const refreshButton = document.getElementById('btn-history-refresh');
  const examTypeSelect = document.getElementById('history-exam-type');
  const examNameInput = document.getElementById('history-exam-name');

  const filters = {
    favoritesOnly: false,
    query: '',
    examType: '',
    examName: '',
  };

  let searchTimer = 0;

  function t(key) {
    return window.RRApp.t(key);
  }

  function escapeHtml(value) {
    return window.RRApp.escapeHtml(value);
  }

  function interpolate(key, params) {
    let value = t(key);
    Object.keys(params || {}).forEach(function (name) {
      value = value.replace('{' + name + '}', String(params[name]));
    });
    return value;
  }

  function populateSelect(select, options, selectedValue) {
    const current = String(selectedValue || '');
    select.innerHTML = options.map(function (option) {
      return '<option value="' + escapeHtml(option.value) + '">' + escapeHtml(t(option.labelKey)) + '</option>';
    }).join('');
    select.value = current;
  }

  function formatSubjectContext(context) {
    const parts = [];
    if (context && context.subjectCode) {
      parts.push(t(window.RRState.getSubjectLabelKey(context.subjectCode)));
    }
    if (context && context.courseName) {
      parts.push(context.courseName);
    }
    return parts.join(' · ');
  }

  function formatExamContext(examType, examName) {
    const parts = [];
    if (examName) {
      parts.push(examName);
    }
    if (examType) {
      parts.push(t(window.RRState.getExamLabelKey(examType)));
    }
    return parts.join(' · ');
  }

  function renderExamControls() {
    populateSelect(examTypeSelect, window.RRState.getExamOptions(), filters.examType);
    examNameInput.value = filters.examName || '';
  }

  function kindLabel(kind) {
    if (kind === 'qa') {
      return t('format_qa');
    }
    if (kind === 'flashcards') {
      return t('format_flashcards');
    }
    return t('format_review_pro');
  }

  function formatGenerationMode(mode) {
    if (mode === 'textbook') {
      return t('review_generation_mode_textbook');
    }
    if (mode === 'combined') {
      return t('review_generation_mode_combined');
    }
    return t('review_generation_mode_materials');
  }

  function updateFavoriteButton() {
    favoritesButton.classList.toggle('is-active', filters.favoritesOnly);
    favoritesButton.title = filters.favoritesOnly ? t('unfavorite') : t('favorite');
  }

  function renderChapterChips(labels) {
    const items = Array.isArray(labels) ? labels.filter(Boolean) : [];
    if (!items.length) {
      return '';
    }
    const visible = items.slice(0, 4);
    const chips = visible.map(function (label) {
      return '<span class="source-chip"><span>' + escapeHtml(label) + '</span></span>';
    });
    if (items.length > visible.length) {
      chips.push('<span class="source-chip"><span>' + escapeHtml(interpolate('history_chapter_scope_more', { n: items.length - visible.length })) + '</span></span>');
    }
    return '<div class="chip-list history-card__chips">' + chips.join('') + '</div>';
  }

  function renderItems(items) {
    if (!items.length) {
      list.innerHTML = '';
      empty.classList.remove('hidden');
      empty.textContent = t('history_empty');
      return;
    }

    empty.classList.add('hidden');
    list.innerHTML = items.map(function (item) {
      const contextLabel = formatSubjectContext({
        subjectCode: item.subject_code,
        courseName: item.course_name,
      });
      const examLabel = formatExamContext(item.exam_type, item.exam_name);
      const title = item.exam_name || item.course_name || item.source_name || kindLabel(item.kind);
      return [
        '<article class="history-card" data-id="' + escapeHtml(item.id) + '">',
        '  <div class="history-card__meta">',
        '    <span class="source-badge">' + escapeHtml(kindLabel(item.kind)) + '</span>',
        '    <span>' + escapeHtml(window.RRApp.formatRelativeDate(item.created_at)) + '</span>',
        contextLabel ? '    <span>' + escapeHtml(contextLabel) + '</span>' : '',
        examLabel ? '    <span>' + escapeHtml(examLabel) + '</span>' : '',
        item.generation_mode ? '    <span>' + escapeHtml(formatGenerationMode(item.generation_mode)) + '</span>' : '',
        item.textbook_name ? '    <span>' + escapeHtml(t('course_textbook_badge') + ': ' + item.textbook_name) + '</span>' : '',
        item.is_favorite ? '    <span>★</span>' : '',
        '  </div>',
        '  <div class="history-card__title">' + escapeHtml(title) + '</div>',
        '  <div class="history-card__preview">' + escapeHtml(item.preview || '') + '</div>',
        renderChapterChips(item.selected_chapter_labels),
        '  <div class="toolbar-row" style="margin-top:0.85rem;">',
        '    <button type="button" class="soft-btn" data-action="restore" data-id="' + escapeHtml(item.id) + '">' + escapeHtml(t('history_restore_review')) + '</button>',
        '    <button type="button" class="ghost-btn" data-action="chat" data-id="' + escapeHtml(item.id) + '">' + escapeHtml(t('history_open_chat')) + '</button>',
        '    <button type="button" class="ghost-btn" data-action="favorite" data-id="' + escapeHtml(item.id) + '">' + escapeHtml(t(item.is_favorite ? 'unfavorite' : 'favorite')) + '</button>',
        '    <button type="button" class="danger-btn" data-action="delete" data-id="' + escapeHtml(item.id) + '">' + escapeHtml(t('common_delete')) + '</button>',
        '  </div>',
        '</article>',
      ].join('');
    }).join('');
  }

  async function loadHistory() {
    updateFavoriteButton();

    if (!window.RRApp.isLoggedIn()) {
      loginNote.classList.remove('hidden');
      list.innerHTML = '';
      empty.classList.add('hidden');
      status.textContent = t('history_need_login_long');
      return;
    }

    loginNote.classList.add('hidden');
    status.textContent = t('common_loading');

    const params = new URLSearchParams({ limit: '50' });
    const context = window.RRState.getSubjectContext();
    if (filters.query) {
      params.set('q', filters.query);
    }
    if (filters.favoritesOnly) {
      params.set('fav', 'true');
    }
    if (context.subjectCode) {
      params.set('subject_code', context.subjectCode);
    }
    if (context.courseName) {
      params.set('course_name', context.courseName);
    }
    if (filters.examType) {
      params.set('exam_type', filters.examType);
    }
    if (filters.examName) {
      params.set('exam_name', filters.examName);
    }

    try {
      const data = await window.RRApp.fetchJSON('/history?' + params.toString(), {
        headers: window.RRApp.authHeaders(),
      });
      const items = data && data.items ? data.items : [];
      renderItems(items);
      status.textContent = items.length ? '' : t('history_empty');
    } catch (error) {
      list.innerHTML = '';
      empty.classList.remove('hidden');
      empty.textContent = error.message || t('support_load_failed');
      status.textContent = error.message || t('support_load_failed');
    }
  }

  async function restoreHistoryItem(id, target) {
    const data = await window.RRApp.fetchJSON('/history/' + encodeURIComponent(id), {
      headers: window.RRApp.authHeaders(),
    });
    window.RRState.setSubjectContext({
      subjectCode: data.subject_code,
      courseName: data.course_name,
    });
    window.RRState.setCurrentReview({
      id: String(data.id),
      text: data.text || '',
      format: data.kind || 'review_sheet_pro',
      createdAt: data.created_at,
      sourceLabels: data.source_name ? [data.source_name] : [],
      sourceIds: data.source_id ? [String(data.source_id)] : [],
      subjectCode: data.subject_code,
      courseName: data.course_name,
      examType: data.exam_type,
      examName: data.exam_name,
      selectedChapterIds: data.selected_chapter_ids || [],
      selectedChapterLabels: data.selected_chapter_labels || [],
      generationMode: data.generation_mode || 'materials',
      textbookFileId: data.textbook_file_id || '',
      textbookName: data.textbook_name || '',
    });
    window.showToast('success', t('restored'));
    location.href = target;
  }

  async function onListAction(event) {
    const button = event.target.closest('[data-action]');
    if (!button) {
      return;
    }

    const action = button.getAttribute('data-action');
    const id = button.getAttribute('data-id');
    if (!action || !id) {
      return;
    }

    try {
      if (action === 'restore') {
        await restoreHistoryItem(id, 'review.html');
        return;
      }
      if (action === 'chat') {
        await restoreHistoryItem(id, 'chat.html');
        return;
      }
      if (action === 'favorite') {
        await window.RRApp.fetchJSON('/history/' + encodeURIComponent(id) + '/favorite', {
          method: 'POST',
          headers: window.RRApp.authHeaders(),
        });
        await loadHistory();
        return;
      }
      if (action === 'delete') {
        if (!window.confirm(t('confirm_delete_history'))) {
          return;
        }
        await window.RRApp.fetchJSON('/history/' + encodeURIComponent(id), {
          method: 'DELETE',
          headers: window.RRApp.authHeaders(),
        });
        window.showToast('success', t('deleted'));
        await loadHistory();
      }
    } catch (error) {
      window.showToast('error', error.message || t('operation_failed'));
    }
  }

  updateFavoriteButton();
  renderExamControls();
  loadHistory();

  search.addEventListener('input', function () {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(function () {
      filters.query = search.value.trim();
      loadHistory();
    }, 220);
  });
  favoritesButton.addEventListener('click', function () {
    filters.favoritesOnly = !filters.favoritesOnly;
    loadHistory();
  });
  examTypeSelect.addEventListener('change', function () {
    filters.examType = examTypeSelect.value;
    loadHistory();
  });
  examNameInput.addEventListener('input', function () {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(function () {
      filters.examName = examNameInput.value.trim();
      loadHistory();
    }, 220);
  });
  refreshButton.addEventListener('click', loadHistory);
  list.addEventListener('click', onListAction);
  document.addEventListener('rr:langchange', function () {
    renderExamControls();
    updateFavoriteButton();
    loadHistory();
  });
});