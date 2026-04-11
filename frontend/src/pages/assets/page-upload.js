document.addEventListener('DOMContentLoaded', async function () {
  await window.RRApp.initPage('upload');

  const fileInput = document.getElementById('file-input');
  const pickButton = document.getElementById('btn-pick-files');
  const urlInput = document.getElementById('url-input');
  const urlButton = document.getElementById('btn-add-url');
  const draftText = document.getElementById('draft-text');
  const draftCount = document.getElementById('draft-char-count');
  const draftSave = document.getElementById('btn-save-draft');
  const serverList = document.getElementById('server-list');
  const sessionList = document.getElementById('session-list');
  const selectedList = document.getElementById('selected-list');
  const serverEmpty = document.getElementById('server-empty');
  const sessionEmpty = document.getElementById('session-empty');
  const selectedEmpty = document.getElementById('selected-empty');
  const libraryNote = document.getElementById('server-library-note');
  const serverSection = document.getElementById('upload-server-section');
  const refreshButton = document.getElementById('btn-refresh-server');
  const clearServerButton = document.getElementById('btn-clear-server');
  const clearSessionButton = document.getElementById('btn-clear-session');
  const clearSelectedButton = document.getElementById('btn-clear-selected');
  const goReviewButton = document.getElementById('btn-go-review');
  const uploadActionDock = document.getElementById('upload-action-dock');
  const uploadSummarySelected = document.getElementById('upload-summary-selected');
  const uploadSummaryDraft = document.getElementById('upload-summary-draft');
  const uploadSummaryMode = document.getElementById('upload-summary-mode');
  const uploadSummaryText = document.getElementById('upload-summary-text');
  const uploadSummaryPreview = document.getElementById('upload-summary-preview');
  const structureNote = document.getElementById('upload-structure-note');
  const structureDetails = document.getElementById('structure-details');
  const structureEditor = document.getElementById('upload-structure-editor');
  const structureBadge = document.getElementById('structure-summary-badge');
  const addUnitButton = document.getElementById('btn-add-unit');
  const saveStructureButton = document.getElementById('btn-save-structure');
  const textbookInput = document.getElementById('course-textbook-input');
  const textbookNote = document.getElementById('course-textbook-note');
  const textbookCard = document.getElementById('course-textbook-card');
  const uploadTextbookButton = document.getElementById('btn-upload-textbook');
  const removeTextbookButton = document.getElementById('btn-remove-textbook');

  // Logged-in users enter via course mode; guests can use upload/review directly.
  const _initContext = window.RRState.getSubjectContext();
  if (window.RRApp.isLoggedIn() && (!_initContext || !_initContext.subjectCode)) {
    location.href = 'workspace.html';
    return;
  }

  if (structureDetails) {
    structureDetails.classList.toggle('hidden', !window.RRApp.isLoggedIn());
  }

  let structureDraft = { units: [] };
  let openMappingId = '';
  let mappingDrafts = {};

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
    return parts.length ? parts.join(' · ') : '';
  }

  function formatStructureSummary(structure) {
    if (!structure || !structure.hasStructure) {
      return t('course_structure_empty');
    }
    return [
      structure.unitCount + ' ' + t('course_units_short'),
      structure.chapterCount + ' ' + t('course_chapters_short'),
    ].join(' · ');
  }

  function formatBytes(value) {
    const size = Number(value || 0);
    if (!size) {
      return '0 B';
    }
    if (size >= 1024 * 1024) {
      return (size / (1024 * 1024)).toFixed(1) + ' MB';
    }
    if (size >= 1024) {
      return Math.round(size / 1024) + ' KB';
    }
    return size + ' B';
  }

  function cloneStructure(structure) {
    if (!structure || !Array.isArray(structure.units)) {
      return { units: [] };
    }
    return {
      id: structure.id || '',
      units: structure.units.map(function (unit) {
        return {
          id: unit.id || '',
          title: unit.title || '',
          chapters: Array.isArray(unit.chapters) ? unit.chapters.map(function (chapter) {
            return {
              id: chapter.id || '',
              title: chapter.title || '',
            };
          }) : [],
        };
      }),
    };
  }

  function getSubjectParams() {
    const context = window.RRState.getSubjectContext();
    const params = new URLSearchParams();
    if (context.subjectCode) {
      params.set('subject_code', context.subjectCode);
    }
    if (context.courseName) {
      params.set('course_name', context.courseName);
    }
    return params;
  }

  function setBusy(button, busy, busyText, idleText) {
    button.disabled = Boolean(busy);
    button.textContent = busy ? busyText : idleText;
  }

  function formatCount(value) {
    return new Intl.NumberFormat().format(Number(value || 0));
  }

  function normalizeToastLabel(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function uniqueToastLabels(values) {
    const seen = new Set();
    return (values || []).map(normalizeToastLabel).filter(function (value) {
      if (!value || seen.has(value)) {
        return false;
      }
      seen.add(value);
      return true;
    });
  }

  function buildToastNamePreview(values, limit) {
    const names = uniqueToastLabels(values);
    if (!names.length) {
      return '';
    }
    const visible = names.slice(0, Math.max(1, Number(limit || 0) || 2));
    const preview = visible.join(' · ');
    return names.length > visible.length ? preview + ' · +' + (names.length - visible.length) : preview;
  }

  function summarizeUploadedFiles(values) {
    const names = uniqueToastLabels(values);
    if (!names.length) {
      return { message: '', detail: '' };
    }
    if (names.length === 1) {
      return { message: names[0], detail: '' };
    }
    return {
      message: interpolate('upload_success_multi_files', { n: formatCount(names.length) }),
      detail: buildToastNamePreview(names, 2),
    };
  }

  function showUploadSuccessPopup(options) {
    const message = normalizeToastLabel(options && options.message);
    const detail = normalizeToastLabel(options && options.detail);
    const titleKey = options && options.titleKey ? options.titleKey : 'upload_done';
    const messageKey = options && options.messageKey ? options.messageKey : '';
    window.showToast('success', {
      title: t(titleKey),
      message: message || (messageKey ? t(messageKey) : ''),
      detail: detail,
      timeout: 4200,
    });
  }

  function buildInputPreview(selectedSources, draftValue) {
    const names = selectedSources.map(function (item) {
      return String(item.name || '').trim();
    }).filter(Boolean);
    if (names.length) {
      const preview = names.slice(0, 3).join(' · ');
      return names.length > 3 ? preview + ' +' + (names.length - 3) : preview;
    }
    const compact = String(draftValue || '').replace(/\s+/g, ' ').trim();
    if (!compact) {
      return '';
    }
    return compact.length > 96 ? compact.slice(0, 96) + '...' : compact;
  }

  function renderActionDock() {
    const selectedSources = window.RRState.getSelectedSources();
    const draftValue = draftText.value.trim();
    const selectedCount = selectedSources.length;
    const draftChars = draftValue.length;
    const hasInput = selectedCount > 0 || draftChars > 0;
    const preview = buildInputPreview(selectedSources, draftValue);

    uploadSummarySelected.textContent = selectedCount
      ? interpolate('flow_selected_count', { n: formatCount(selectedCount) })
      : t('flow_selected_none');
    uploadSummaryDraft.textContent = draftChars
      ? interpolate('flow_draft_count', { n: formatCount(draftChars) })
      : t('flow_draft_none');
    uploadSummaryMode.textContent = t(window.RRApp.isLoggedIn() ? 'shell_mode_member' : 'shell_mode_guest');
    uploadSummaryText.textContent = hasInput
      ? t(window.RRApp.isLoggedIn() ? 'upload_flow_ready_member' : 'upload_flow_ready_guest')
      : t('upload_flow_empty');
    uploadSummaryPreview.textContent = preview;
    uploadSummaryPreview.classList.toggle('hidden', !preview);
    uploadActionDock.classList.toggle('is-ready', hasInput);
    goReviewButton.disabled = !hasInput;
    clearSelectedButton.disabled = !selectedCount;
  }

  function renderDraftCount() {
    draftCount.textContent = formatCount(draftText.value.trim().length);
    renderActionDock();
  }

  function canEditStructure() {
    return window.RRApp.isLoggedIn() && Boolean(window.RRState.getSubjectContext().courseName);
  }

  function getSavedStructure() {
    return window.RRState.getCourseStructure();
  }

  function sanitizeStructureDraft() {
    return {
      units: (structureDraft.units || []).map(function (unit) {
        return {
          id: unit.id || undefined,
          title: String(unit.title || '').trim(),
          chapters: (unit.chapters || []).map(function (chapter) {
            return {
              id: chapter.id || undefined,
              title: String(chapter.title || '').trim(),
            };
          }).filter(function (chapter) {
            return chapter.title;
          }),
        };
      }).filter(function (unit) {
        return unit.title;
      }),
    };
  }

  function renderStructureEditor() {
    const context = window.RRState.getSubjectContext();
    const savedStructure = getSavedStructure();
    const editable = canEditStructure();

    addUnitButton.disabled = !editable;
    saveStructureButton.disabled = !editable;

    // Update the <details> summary badge
    if (structureBadge) {
      structureBadge.textContent = savedStructure && savedStructure.hasStructure
        ? formatStructureSummary(savedStructure)
        : '';
    }

    renderTextbookPanel();

    if (!window.RRApp.isLoggedIn()) {
      if (structureNote) structureNote.textContent = t('files_need_login');
      structureEditor.innerHTML = '<div class="empty-state">' + escapeHtml(t('files_need_login')) + '</div>';
      return;
    }

    if (structureNote) structureNote.textContent = savedStructure && savedStructure.hasStructure
      ? formatStructureSummary(savedStructure)
      : t('course_structure_copy');

    if (!structureDraft.units.length) {
      structureEditor.innerHTML = '<div class="empty-state">' + escapeHtml(t('course_structure_empty')) + '</div>';
      return;
    }

    structureEditor.innerHTML = structureDraft.units.map(function (unit, unitIndex) {
      return [
        '<article class="structure-unit-card" data-unit-index="' + unitIndex + '">',
        '  <div class="structure-unit-head">',
        '    <label class="field-stack" style="flex:1;">',
        '      <span class="field-label">' + escapeHtml(t('course_unit_label')) + '</span>',
        '      <input class="input-field" type="text" data-structure-field="unit-title" data-unit-index="' + unitIndex + '" placeholder="' + escapeHtml(t('course_unit_placeholder')) + '" value="' + escapeHtml(unit.title || '') + '" />',
        '    </label>',
        '    <button type="button" class="danger-btn" data-action="remove-unit" data-unit-index="' + unitIndex + '">' + escapeHtml(t('course_remove_unit')) + '</button>',
        '  </div>',
        '  <div class="chapter-list">',
        (unit.chapters || []).map(function (chapter, chapterIndex) {
          return [
            '    <div class="chapter-item">',
            '      <input class="input-field" type="text" data-structure-field="chapter-title" data-unit-index="' + unitIndex + '" data-chapter-index="' + chapterIndex + '" placeholder="' + escapeHtml(t('course_chapter_placeholder')) + '" value="' + escapeHtml(chapter.title || '') + '" />',
            '      <button type="button" class="ghost-btn" data-action="remove-chapter" data-unit-index="' + unitIndex + '" data-chapter-index="' + chapterIndex + '">' + escapeHtml(t('course_remove_chapter')) + '</button>',
            '    </div>',
          ].join('');
        }).join(''),
        '  </div>',
        '  <button type="button" class="ghost-btn" data-action="add-chapter" data-unit-index="' + unitIndex + '">' + escapeHtml(t('course_structure_add_chapter')) + '</button>',
        '</article>',
      ].join('');
    }).join('');
  }

  function renderTextbookPanel() {
    const context = window.RRState.getSubjectContext();
    const structure = getSavedStructure();
    const textbook = structure && structure.textbook ? structure.textbook : null;
    const editable = canEditStructure();

    uploadTextbookButton.disabled = !editable;
    removeTextbookButton.disabled = !editable || !textbook;
    uploadTextbookButton.textContent = textbook ? t('course_textbook_replace') : t('course_textbook_upload');

    if (!window.RRApp.isLoggedIn()) {
      textbookNote.textContent = t('files_need_login');
      textbookCard.innerHTML = '<div class="empty-state">' + escapeHtml(t('files_need_login')) + '</div>';
      return;
    }

    if (!context.courseName) {
      textbookNote.textContent = t('course_textbook_need_course');
      textbookCard.innerHTML = '<div class="empty-state">' + escapeHtml(t('course_textbook_need_course')) + '</div>';
      return;
    }

    textbookNote.textContent = textbook ? t('course_textbook_ready') : t('course_textbook_copy');
    if (!textbook) {
      textbookCard.innerHTML = '<div class="empty-state">' + escapeHtml(t('course_textbook_empty')) + '</div>';
      return;
    }

    const meta = [
      formatBytes(textbook.size),
      textbook.createdAt ? window.RRApp.formatRelativeDate(textbook.createdAt) : '',
      structure ? formatStructureSummary(structure) : '',
    ].filter(Boolean).join(' · ');

    textbookCard.innerHTML = [
      '<div class="source-card source-card--selected">',
      '  <div class="source-card__meta">',
      '    <span class="source-badge">' + escapeHtml(t('course_textbook_badge')) + '</span>',
      meta ? '    <span>' + escapeHtml(meta) + '</span>' : '',
      '  </div>',
      '  <div class="source-card__title">' + escapeHtml(textbook.filename || '') + '</div>',
      '  <div class="source-card__preview">' + escapeHtml(t('course_textbook_ready')) + '</div>',
      '</div>',
    ].join('');
  }

  function renderMappingChips(matches) {
    if (!matches || !matches.length) {
      return '<div class="helper-text">' + escapeHtml(t('chapter_mapping_none')) + '</div>';
    }
    return '<div class="mapping-list">' + matches.map(function (match) {
      const sourceKey = match.mappingSource === 'manual' ? 'chapter_mapping_manual' : 'chapter_mapping_auto';
      return [
        '<span class="mapping-chip">',
        '  <span>' + escapeHtml(match.label || match.chapterTitle || '') + '</span>',
        '  <span class="mapping-chip__tag">' + escapeHtml(t(sourceKey)) + '</span>',
        '</span>',
      ].join('');
    }).join('') + '</div>';
  }

  function getMappingDraftIds(source) {
    if (mappingDrafts[source.id]) {
      return mappingDrafts[source.id];
    }
    return (source.chapterMatches || []).map(function (match) {
      return String(match.chapterId || '');
    }).filter(Boolean);
  }

  function renderMappingEditor(source) {
    const structure = getSavedStructure();
    if (!structure || !structure.hasStructure) {
      return '';
    }
    const selectedIds = new Set(getMappingDraftIds(source));
    return [
      '<div class="mapping-editor">',
      structure.units.map(function (unit) {
        return [
          '<section class="chapter-group">',
          '  <div class="chapter-group__title">' + escapeHtml(unit.title || '') + '</div>',
          '  <div class="chapter-checklist">',
          (unit.chapters || []).map(function (chapter) {
            const chapterId = String(chapter.id || '');
            return [
              '    <label class="chapter-option">',
              '      <input type="checkbox" data-mapping-toggle="true" data-source-id="' + escapeHtml(source.id) + '" data-chapter-id="' + escapeHtml(chapterId) + '"' + (selectedIds.has(chapterId) ? ' checked' : '') + ' />',
              '      <span>' + escapeHtml(chapter.title || '') + '</span>',
              '    </label>',
            ].join('');
          }).join(''),
          '  </div>',
          '</section>',
        ].join('');
      }).join(''),
      '  <div class="toolbar-row" style="margin-top:0.85rem;">',
      '    <button type="button" class="soft-btn" data-action="save-mapping" data-id="' + escapeHtml(source.id) + '">' + escapeHtml(t('chapter_mapping_save')) + '</button>',
      '  </div>',
      '</div>',
    ].join('');
  }

  function sourceCard(item, allowRemove) {
    const preview = item.kind === 'session' && item.content
      ? '<div class="source-card__preview">' + escapeHtml(item.content.slice(0, 160)) + '</div>'
      : '';
    const showMappingControls = item.kind === 'file' && getSavedStructure() && getSavedStructure().hasStructure;
    const mappingSection = item.kind === 'file'
      ? '<div class="source-card__preview">' + renderMappingChips(item.chapterMatches || []) + '</div>'
      : '';
    const mappingEditor = item.kind === 'file' && openMappingId === item.id ? renderMappingEditor(item) : '';

    return [
      '<article class="source-card' + (item.selected ? ' source-card--selected' : '') + '">',
      '  <div class="source-card__meta">',
      '    <span class="source-badge">' + escapeHtml(t(item.kind === 'file' ? 'source_kind_uploaded' : 'source_kind_session')) + '</span>',
      '    <span>' + escapeHtml(formatCount(item.chars)) + '</span>',
      '  </div>',
      '  <div class="source-card__title">' + escapeHtml(item.name) + '</div>',
      preview,
      mappingSection,
      mappingEditor,
      '  <div class="source-card__actions">',
      '    <button class="soft-btn" type="button" data-action="toggle" data-id="' + escapeHtml(item.id) + '">' + escapeHtml(t(item.selected ? 'source_selected' : 'source_select')) + '</button>',
      showMappingControls ? '    <button class="ghost-btn" type="button" data-action="edit-mapping" data-id="' + escapeHtml(item.id) + '">' + escapeHtml(t('chapter_mapping_edit')) + '</button>' : '',
      allowRemove ? '    <button class="ghost-btn" type="button" data-action="remove" data-id="' + escapeHtml(item.id) + '">' + escapeHtml(t('source_remove')) + '</button>' : '',
      '  </div>',
      '</article>',
    ].join('');
  }

  function renderSelected() {
    const items = window.RRState.getSelectedSources();
    if (!items.length) {
      selectedList.innerHTML = '';
      selectedEmpty.classList.remove('hidden');
      return;
    }

    selectedEmpty.classList.add('hidden');
    selectedList.innerHTML = items.map(function (item) {
      return [
        '<span class="source-chip">',
        '  <span>' + escapeHtml(item.name) + '</span>',
        '  <span class="source-chip__tag">' + escapeHtml(t(item.kind === 'file' ? 'source_kind_uploaded' : 'source_kind_session')) + '</span>',
        '</span>',
      ].join('');
    }).join('');
  }

  function renderLists() {
    const sources = window.RRState.getSources();
    const structure = getSavedStructure();
    const serverItems = sources.filter(function (item) {
      return item.kind === 'file';
    });
    const sessionItems = sources.filter(function (item) {
      return item.kind === 'session';
    });

    serverSection.classList.toggle('hidden', !window.RRApp.isLoggedIn());

    libraryNote.textContent = window.RRApp.isLoggedIn()
      ? formatStructureSummary(structure) || ''
      : t('guest_session_only_note');

    serverList.innerHTML = serverItems.map(function (item) {
      return sourceCard(item, false);
    }).join('');
    sessionList.innerHTML = sessionItems.map(function (item) {
      return sourceCard(item, true);
    }).join('');

    serverEmpty.classList.toggle('hidden', serverItems.length > 0);
    sessionEmpty.classList.toggle('hidden', sessionItems.length > 0);

    clearServerButton.disabled = !window.RRApp.isLoggedIn() || !serverItems.length;
    clearSessionButton.disabled = !sessionItems.length;

    renderSelected();
    renderDraftCount();
  }

  async function refreshServerSources() {
    if (!window.RRApp.isLoggedIn()) {
      window.RRState.mergeServerSources([]);
      renderLists();
      return;
    }

    try {
      const params = getSubjectParams();
      const path = '/upload/list' + (params.toString() ? '?' + params.toString() : '');
      const data = await window.RRApp.fetchJSON(path, {
        headers: window.RRApp.authHeaders(),
      });
      window.RRState.mergeServerSources((data && data.items) || []);
    } catch (error) {
      window.showToast('error', error.message || t('support_load_failed'));
    }

    renderLists();
  }

  async function loadCourseStructure() {
    const context = window.RRState.getSubjectContext();
    if (!window.RRApp.isLoggedIn() || !context.courseName) {
      window.RRState.setCourseStructure(null);
      structureDraft = { units: [] };
      renderStructureEditor();
      renderLists();
      return;
    }

    try {
      const params = getSubjectParams();
      const path = '/course-structure' + (params.toString() ? '?' + params.toString() : '');
      const data = await window.RRApp.fetchJSON(path, {
        headers: window.RRApp.authHeaders(),
      });
      const structure = window.RRState.setCourseStructure(data ? data.course : null);
      structureDraft = cloneStructure(structure);
    } catch (error) {
      window.RRState.setCourseStructure(null);
      structureDraft = { units: [] };
      window.showToast('error', error.message || t('support_load_failed'));
    }

    renderStructureEditor();
    renderLists();
  }

  async function uploadFiles(files) {
    if (!files.length) {
      return;
    }

    const context = window.RRState.getSubjectContext();
    const uploadedNames = [];
    setBusy(pickButton, true, t('uploading'), t('upload_pick_files'));
    try {
      for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);
        if (context.subjectCode) {
          formData.append('subject_code', context.subjectCode);
        }
        if (context.courseName) {
          formData.append('course_name', context.courseName);
        }
        const data = await window.RRApp.fetchJSON('/upload', {
          method: 'POST',
          headers: window.RRApp.authHeaders(),
          body: formData,
        });
        const sourceName = (data.meta && data.meta.filename) || file.name;
        uploadedNames.push(sourceName);
        window.RRState.addUploadedSource({
          ...data,
          name: sourceName,
        });
      }
      await refreshServerSources();
      const uploadSummary = summarizeUploadedFiles(uploadedNames);
      showUploadSuccessPopup({
        titleKey: 'upload_done',
        message: uploadSummary.message,
        detail: uploadSummary.detail,
      });
    } catch (error) {
      window.showToast('error', error.message || t('operation_failed'));
    } finally {
      fileInput.value = '';
      setBusy(pickButton, false, t('uploading'), t('upload_pick_files'));
    }
  }

  async function uploadTextbook(file) {
    if (!file) {
      return;
    }

    const context = window.RRState.getSubjectContext();
    if (!window.RRApp.isLoggedIn()) {
      window.showToast('info', t('files_need_login'));
      return;
    }
    if (!context.courseName) {
      window.showToast('info', t('course_textbook_need_course'));
      return;
    }

    setBusy(uploadTextbookButton, true, t('common_loading'), t(window.RRState.getCourseStructure() && window.RRState.getCourseStructure().textbook ? 'course_textbook_replace' : 'course_textbook_upload'));
    try {
      const formData = new FormData();
      formData.append('file', file);
      if (context.subjectCode) {
        formData.append('subject_code', context.subjectCode);
      }
      formData.append('course_name', context.courseName);

      const data = await window.RRApp.fetchJSON('/course-structure/textbook', {
        method: 'POST',
        headers: window.RRApp.authHeaders(),
        body: formData,
      });
      const structure = window.RRState.setCourseStructure(data ? data.course : null);
      structureDraft = cloneStructure(structure);
      renderStructureEditor();
      renderLists();
      showUploadSuccessPopup({
        titleKey: 'course_textbook_success_title',
        message: (structure && structure.textbook && structure.textbook.filename) || file.name,
      });
    } catch (error) {
      window.showToast('error', error.message || t('operation_failed'));
    } finally {
      textbookInput.value = '';
      setBusy(uploadTextbookButton, false, t('common_loading'), t(window.RRState.getCourseStructure() && window.RRState.getCourseStructure().textbook ? 'course_textbook_replace' : 'course_textbook_upload'));
    }
  }

  async function removeTextbook() {
    if (!window.RRApp.isLoggedIn()) {
      window.showToast('info', t('files_need_login'));
      return;
    }
    if (!window.RRState.getCourseStructure() || !window.RRState.getCourseStructure().textbook) {
      return;
    }
    if (!window.confirm(t('confirm_remove_textbook'))) {
      return;
    }

    try {
      const params = getSubjectParams();
      const data = await window.RRApp.fetchJSON('/course-structure/textbook?' + params.toString(), {
        method: 'DELETE',
        headers: window.RRApp.authHeaders(),
      });
      const structure = window.RRState.setCourseStructure(data ? data.course : null);
      structureDraft = cloneStructure(structure);
      renderStructureEditor();
      renderLists();
      window.showToast('success', t('course_textbook_removed'));
    } catch (error) {
      window.showToast('error', error.message || t('operation_failed'));
    }
  }

  async function addFromUrl() {
    const url = urlInput.value.trim();
    if (!url) {
      urlInput.focus();
      return;
    }

    const context = window.RRState.getSubjectContext();
    setBusy(urlButton, true, t('uploading'), t('add_from_url'));
    try {
      const formData = new FormData();
      formData.append('url', url);
      if (context.subjectCode) {
        formData.append('subject_code', context.subjectCode);
      }
      if (context.courseName) {
        formData.append('course_name', context.courseName);
      }
      const data = await window.RRApp.fetchJSON('/upload', {
        method: 'POST',
        headers: window.RRApp.authHeaders(),
        body: formData,
      });
      const sourceName = (data.meta && data.meta.filename) || url;
      window.RRState.addUploadedSource({
        ...data,
        name: sourceName,
      });
      urlInput.value = '';
      await refreshServerSources();
      showUploadSuccessPopup({
        titleKey: 'source_added',
        message: sourceName,
      });
    } catch (error) {
      window.showToast('error', error.message || t('operation_failed'));
    } finally {
      setBusy(urlButton, false, t('uploading'), t('add_from_url'));
    }
  }

  function saveDraft(notify) {
    window.RRState.setDraftText(draftText.value);
    renderDraftCount();
    if (notify) {
      showUploadSuccessPopup({
        titleKey: 'upload_draft_saved',
        messageKey: 'upload_success_current_draft',
      });
    }
  }

  async function clearServerLibrary() {
    if (!window.RRApp.isLoggedIn()) {
      window.showToast('info', t('files_need_login'));
      return;
    }
    if (!window.confirm(t('confirm_clear_files'))) {
      return;
    }

    try {
      const params = getSubjectParams();
      const path = '/upload/all' + (params.toString() ? '?' + params.toString() : '');
      await window.RRApp.fetchJSON(path, {
        method: 'DELETE',
        headers: window.RRApp.authHeaders(),
      });
      window.RRState.mergeServerSources([]);
      renderLists();
      window.showToast('success', t('cleared'));
    } catch (error) {
      window.showToast('error', error.message || t('operation_failed'));
    }
  }

  async function saveStructure() {
    const context = window.RRState.getSubjectContext();
    if (!window.RRApp.isLoggedIn()) {
      window.showToast('info', t('files_need_login'));
      return;
    }
    if (!context.courseName) {
      window.showToast('info', t('course_structure_need_course'));
      return;
    }

    const payload = sanitizeStructureDraft();
    setBusy(saveStructureButton, true, t('common_loading'), t('course_structure_save'));
    try {
      const data = await window.RRApp.fetchJSON('/course-structure', {
        method: 'PUT',
        headers: window.RRApp.authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          subject_code: context.subjectCode || undefined,
          course_name: context.courseName,
          units: payload.units,
        }),
      });
      const structure = window.RRState.setCourseStructure(data ? data.course : null);
      structureDraft = cloneStructure(structure);
      renderStructureEditor();
      renderLists();
      window.showToast('success', t('course_structure_saved'));
    } catch (error) {
      window.showToast('error', error.message || t('operation_failed'));
    } finally {
      setBusy(saveStructureButton, false, t('common_loading'), t('course_structure_save'));
    }
  }

  async function saveFileMapping(sourceId) {
    const source = window.RRState.getSources().find(function (item) {
      return item.id === sourceId;
    });
    if (!source || !source.fileId) {
      return;
    }

    try {
      const data = await window.RRApp.fetchJSON('/upload/' + encodeURIComponent(source.fileId) + '/chapters', {
        method: 'PUT',
        headers: window.RRApp.authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          chapter_ids: (mappingDrafts[sourceId] || []).map(function (chapterId) {
            return Number(chapterId);
          }),
        }),
      });
      window.RRState.updateSourceChapterMatches(sourceId, data.chapter_matches || []);
      delete mappingDrafts[sourceId];
      openMappingId = '';
      renderLists();
      window.showToast('success', t('chapter_mapping_saved'));
    } catch (error) {
      window.showToast('error', error.message || t('operation_failed'));
    }
  }

  function clearSelectedSources() {
    window.RRState.getSelectedSources().forEach(function (source) {
      window.RRState.setSourceSelected(source.id, false);
    });
    renderLists();
    window.showToast('success', t('cleared'));
  }

  function onStructureClick(event) {
    const button = event.target.closest('[data-action]');
    if (!button) {
      return;
    }
    const action = button.getAttribute('data-action');
    const unitIndex = Number(button.getAttribute('data-unit-index'));
    const chapterIndex = Number(button.getAttribute('data-chapter-index'));
    if (action === 'add-unit') {
      structureDraft.units.push({ id: '', title: '', chapters: [] });
      renderStructureEditor();
      return;
    }
    if (action === 'remove-unit' && Number.isFinite(unitIndex)) {
      structureDraft.units.splice(unitIndex, 1);
      renderStructureEditor();
      return;
    }
    if (action === 'add-chapter' && Number.isFinite(unitIndex) && structureDraft.units[unitIndex]) {
      structureDraft.units[unitIndex].chapters.push({ id: '', title: '' });
      renderStructureEditor();
      return;
    }
    if (action === 'remove-chapter' && Number.isFinite(unitIndex) && Number.isFinite(chapterIndex) && structureDraft.units[unitIndex]) {
      structureDraft.units[unitIndex].chapters.splice(chapterIndex, 1);
      renderStructureEditor();
    }
  }

  function onStructureInput(event) {
    const target = event.target;
    if (!target || !target.dataset) {
      return;
    }
    const field = target.dataset.structureField;
    const unitIndex = Number(target.dataset.unitIndex);
    const chapterIndex = Number(target.dataset.chapterIndex);
    if (field === 'unit-title' && Number.isFinite(unitIndex) && structureDraft.units[unitIndex]) {
      structureDraft.units[unitIndex].title = target.value;
      return;
    }
    if (field === 'chapter-title' && Number.isFinite(unitIndex) && Number.isFinite(chapterIndex) && structureDraft.units[unitIndex] && structureDraft.units[unitIndex].chapters[chapterIndex]) {
      structureDraft.units[unitIndex].chapters[chapterIndex].title = target.value;
    }
  }

  async function onSourceAction(event) {
    const actionButton = event.target.closest('[data-action]');
    if (!actionButton) {
      return;
    }

    const id = actionButton.getAttribute('data-id');
    const action = actionButton.getAttribute('data-action');
    if (!id || !action) {
      return;
    }

    if (action === 'toggle') {
      window.RRState.toggleSourceSelected(id);
      renderLists();
      return;
    }

    if (action === 'remove') {
      window.RRState.removeSource(id);
      renderLists();
      return;
    }

    if (action === 'edit-mapping') {
      openMappingId = openMappingId === id ? '' : id;
      const source = window.RRState.getSources().find(function (item) { return item.id === id; });
      mappingDrafts[id] = source ? getMappingDraftIds(source) : [];
      renderLists();
      return;
    }

    if (action === 'save-mapping') {
      await saveFileMapping(id);
    }
  }

  function onServerChange(event) {
    const input = event.target;
    if (!input || !input.matches('[data-mapping-toggle="true"]')) {
      return;
    }
    const sourceId = String(input.getAttribute('data-source-id') || '');
    const chapterId = String(input.getAttribute('data-chapter-id') || '');
    const next = new Set(mappingDrafts[sourceId] || []);
    if (input.checked) {
      next.add(chapterId);
    } else {
      next.delete(chapterId);
    }
    mappingDrafts[sourceId] = Array.from(next);
  }

  draftText.value = window.RRState.getDraftText();
  renderStructureEditor();
  renderLists();
  await loadCourseStructure();
  await refreshServerSources();

  addUnitButton.setAttribute('data-action', 'add-unit');
  addUnitButton.addEventListener('click', function (event) {
    onStructureClick(event);
  });
  uploadTextbookButton.addEventListener('click', function () {
    textbookInput.click();
  });
  textbookInput.addEventListener('change', function () {
    uploadTextbook((textbookInput.files || [])[0]);
  });
  removeTextbookButton.addEventListener('click', removeTextbook);
  saveStructureButton.addEventListener('click', saveStructure);
  structureEditor.addEventListener('click', onStructureClick);
  structureEditor.addEventListener('input', onStructureInput);

  pickButton.addEventListener('click', function () {
    fileInput.click();
  });
  fileInput.addEventListener('change', function () {
    uploadFiles(Array.from(fileInput.files || []));
  });
  urlButton.addEventListener('click', addFromUrl);
  draftSave.addEventListener('click', function () {
    saveDraft(true);
  });
  draftText.addEventListener('input', function () {
    saveDraft(false);
  });
  refreshButton.addEventListener('click', async function () {
    await loadCourseStructure();
    await refreshServerSources();
  });
  clearServerButton.addEventListener('click', clearServerLibrary);
  clearSessionButton.addEventListener('click', function () {
    window.RRState.clearSessionSources();
    renderLists();
    window.showToast('success', t('cleared'));
  });
  clearSelectedButton.addEventListener('click', clearSelectedSources);
  goReviewButton.addEventListener('click', function () {
    saveDraft(false);
    if (!window.RRState.getSelectedSources().length && !draftText.value.trim()) {
      window.showToast('info', t('upload_flow_empty'));
      draftText.focus();
      return;
    }
    location.href = 'review.html';
  });
  serverList.addEventListener('click', function (event) {
    onSourceAction(event);
  });
  serverList.addEventListener('change', onServerChange);
  sessionList.addEventListener('click', function (event) {
    onSourceAction(event);
  });
  document.addEventListener('rr:langchange', function () {
    renderStructureEditor();
    renderLists();
  });
});