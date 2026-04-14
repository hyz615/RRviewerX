document.addEventListener('DOMContentLoaded', async function () {
  await window.RRApp.initPage('review');

  const _initContext = window.RRState.getSubjectContext();
  if (window.RRApp.isLoggedIn() && (!_initContext || !_initContext.subjectCode)) {
    location.href = 'workspace.html';
    return;
  }

  const FORMAT_KEY = 'rr_review_format_v2';
  const LENGTH_KEY = 'rr_review_length_v2';

  const formatSelect = document.getElementById('fmt');
  const sourceText = document.getElementById('src');
  const charCount = document.getElementById('char-count');
  const draftStatus = document.getElementById('draft-status');
  const generateButton = document.getElementById('btn-generate');
  const generateTopButton = document.getElementById('btn-generate-top');
  const copyButton = document.getElementById('btn-copy');
  const exportMdButton = document.getElementById('btn-export-md');
  const exportPdfButton = document.getElementById('btn-export-pdf');
  const mockTestLink = document.getElementById('btn-mock-test');
  const progressWrap = document.getElementById('gen-progress');
  const progressBar = document.getElementById('gen-progress-bar');
  const progressText = document.getElementById('gen-progress-text');
  const outputMeta = document.getElementById('review-meta');
  const outputEmpty = document.getElementById('review-empty');
  const output = document.getElementById('review-output');
  const sourcesBox = document.getElementById('review-sources');
  const sourcesEmpty = document.getElementById('review-sources-empty');
  const examTypeSelect = document.getElementById('review-exam-type');
  const examNameInput = document.getElementById('review-exam-name');
  const chapterSection = document.getElementById('review-chapter-section');
  const chapterNote = document.getElementById('review-chapter-note');
  const chapterGroups = document.getElementById('review-chapter-groups');
  const chapterEmpty = document.getElementById('review-chapter-empty');
  const generationModeNote = document.getElementById('review-generation-mode-note');
  const generationModeGroup = document.getElementById('review-generation-mode-group');
  const textbookMeta = document.getElementById('review-textbook-meta');
  const reviewOpenChat = document.getElementById('review-open-chat');
  const reviewOpenHistory = document.getElementById('review-open-history');
  const reviewActionDock = document.getElementById('review-action-dock');
  const reviewSummarySelected = document.getElementById('review-summary-selected');
  const reviewSummaryDraft = document.getElementById('review-summary-draft');
  const reviewSummaryMode = document.getElementById('review-summary-mode');
  const reviewSummaryText = document.getElementById('review-summary-text');
  const reviewSummaryPreview = document.getElementById('review-summary-preview');

  let draftTimer = 0;
  let currentLength = 'medium';
  let currentGenerationMode = window.RRState.getGenerationMode();
  let canGenerate = false;
  let generateBusy = false;

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

  function formatCount(value) {
    return new Intl.NumberFormat().format(Number(value || 0));
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

  function formatGenerationMode(mode) {
    if (mode === 'textbook') {
      return t('review_generation_mode_textbook');
    }
    if (mode === 'combined') {
      return t('review_generation_mode_combined');
    }
    return t('review_generation_mode_materials');
  }

  function getActiveTextbook() {
    const structure = window.RRState.getCourseStructure();
    return structure && structure.textbook ? structure.textbook : null;
  }

  function getTextbookPreview() {
    const textbook = getActiveTextbook();
    if (!textbook) {
      return '';
    }
    const chapterSummary = getSelectedChapterSummary();
    return [textbook.filename, chapterSummary !== t('review_chapter_scope_all') ? chapterSummary : ''].filter(Boolean).join(' · ');
  }

  function getRenderableSources() {
    const selected = window.RRState.getSelectedSources();
    const currentReview = window.RRState.getCurrentReview();
    const restored = !selected.length && currentReview && Array.isArray(currentReview.sourceLabels)
      ? currentReview.sourceLabels.map(function (label) {
          return { name: label, kind: 'restored' };
        })
      : [];
    return selected.length ? selected : restored;
  }

  function buildInputPreview(items, draftValue) {
    const names = items.map(function (item) {
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
    return compact.length > 120 ? compact.slice(0, 120) + '...' : compact;
  }

  function renderActionDock() {
    const items = window.RRState.getSelectedSources();
    const sourcePayload = window.RRState.getReviewPayload();
    const draftValue = sourceText.value.trim();
    const selectedCount = items.length;
    const draftChars = draftValue.length;
    const chapterCount = window.RRApp.isLoggedIn() ? sourcePayload.chapterIds.length : 0;
    const textbookReady = currentGenerationMode !== 'materials' && Boolean(getActiveTextbook());
    const hasInput = selectedCount > 0 || sourcePayload.inlineTexts.length > 0 || draftChars > 0 || chapterCount > 0 || textbookReady;
    const preview = buildInputPreview(items, draftValue)
      || (textbookReady ? getTextbookPreview() : '')
      || (chapterCount ? getSelectedChapterSummary() : '');

    canGenerate = hasInput;
    reviewSummarySelected.textContent = selectedCount
      ? interpolate('flow_selected_count', { n: formatCount(selectedCount) })
      : t('flow_selected_none');
    reviewSummaryDraft.textContent = draftChars
      ? interpolate('flow_draft_count', { n: formatCount(draftChars) })
      : t('flow_draft_none');
    reviewSummaryMode.textContent = t(window.RRApp.isLoggedIn() ? 'shell_mode_member' : 'shell_mode_guest');
    reviewSummaryText.textContent = hasInput
      ? t(window.RRApp.isLoggedIn() ? 'review_flow_ready_member' : 'review_flow_ready_guest')
      : t('review_flow_empty');
    reviewSummaryPreview.textContent = preview;
    reviewSummaryPreview.classList.toggle('hidden', !preview);
    reviewActionDock.classList.toggle('is-ready', hasInput);
    if (!generateBusy) {
      generateButton.disabled = !canGenerate;
      generateTopButton.disabled = !canGenerate;
    }
  }

  function setStoredValue(key, value) {
    try {
      sessionStorage.setItem(key, value);
    } catch (_) {}
  }

  function getStoredValue(key, fallbackValue) {
    try {
      return sessionStorage.getItem(key) || fallbackValue;
    } catch (_) {
      return fallbackValue;
    }
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

  function getSelectedChapterSummary(reviewOverride) {
    const review = reviewOverride || window.RRState.getCurrentReview();
    const selectedIds = window.RRState.getSelectedChapterIds();
    const labels = review && Array.isArray(review.selectedChapterLabels) ? review.selectedChapterLabels.filter(Boolean) : [];

    if (selectedIds.length) {
      return interpolate('review_chapter_selected_count', { n: selectedIds.length });
    }
    if (labels.length) {
      const preview = labels.slice(0, 3).join(' · ');
      return labels.length > 3 ? preview + ' +' + (labels.length - 3) : preview;
    }
    return t('review_chapter_scope_all');
  }

  function renderExamControls(reviewOverride) {
    const review = reviewOverride || window.RRState.getCurrentReview();
    populateSelect(examTypeSelect, window.RRState.getExamOptions(), review && review.examType ? review.examType : '');
    examNameInput.value = review && review.examName ? review.examName : '';
  }

  function renderGenerationModeControls() {
    const textbook = getActiveTextbook();
    const hasTextbook = Boolean(textbook);

    if (!window.RRApp.isLoggedIn()) {
      currentGenerationMode = 'materials';
      window.RRState.setGenerationMode(currentGenerationMode);
    } else if (!hasTextbook && currentGenerationMode !== 'materials') {
      currentGenerationMode = 'materials';
      window.RRState.setGenerationMode(currentGenerationMode);
    }

    Array.from(generationModeGroup.querySelectorAll('[data-generation-mode]')).forEach(function (button) {
      const mode = button.getAttribute('data-generation-mode') || 'materials';
      const disabled = mode !== 'materials' && !hasTextbook;
      button.disabled = disabled;
      button.classList.toggle('is-active', currentGenerationMode === mode);
    });

    if (!window.RRApp.isLoggedIn()) {
      generationModeNote.textContent = t('files_need_login');
      textbookMeta.textContent = t('files_need_login');
      return;
    }

    if (!window.RRState.getSubjectContext().courseName) {
      generationModeNote.textContent = t('course_textbook_need_course');
      textbookMeta.textContent = t('course_textbook_need_course');
      return;
    }

    generationModeNote.textContent = hasTextbook ? t('review_generation_mode_copy') : t('review_textbook_missing');
    if (!hasTextbook) {
      textbookMeta.textContent = t('review_textbook_missing');
      return;
    }

    textbookMeta.textContent = [
      t('course_textbook_badge'),
      textbook.filename,
      formatBytes(textbook.size),
      textbook.createdAt ? window.RRApp.formatRelativeDate(textbook.createdAt) : '',
      formatGenerationMode(currentGenerationMode),
    ].filter(Boolean).join(' · ');
  }

  function syncModeUI() {
    const courseMode = window.RRApp.isLoggedIn();
    if (chapterSection) {
      chapterSection.classList.toggle('hidden', !courseMode);
    }
    if (reviewOpenChat) {
      reviewOpenChat.classList.toggle('hidden', !courseMode);
    }
    if (reviewOpenHistory) {
      reviewOpenHistory.classList.toggle('hidden', !courseMode);
    }
    if (!courseMode) {
      currentGenerationMode = 'materials';
      window.RRState.setGenerationMode(currentGenerationMode);
      window.RRState.setSelectedChapterIds([]);
    }
  }

  async function loadCourseStructure() {
    if (!window.RRApp.isLoggedIn()) {
      window.RRState.setCourseStructure(null);
      window.RRState.setSelectedChapterIds([]);
      renderChapterScope();
      return;
    }

    const context = window.RRState.getSubjectContext();
    if (!context.courseName) {
      window.RRState.setCourseStructure(null);
      renderChapterScope();
      return;
    }

    if (!window.RRApp.isLoggedIn()) {
      renderChapterScope();
      return;
    }

    try {
      const params = getSubjectParams();
      const data = await window.RRApp.fetchJSON('/course-structure?' + params.toString(), {
        headers: window.RRApp.authHeaders(),
      });
      window.RRState.setCourseStructure(data ? data.course : null);
    } catch (error) {
      window.showToast('error', error.message || t('support_load_failed'));
    }

    renderGenerationModeControls();
    renderChapterScope();
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

  function renderSources() {
    const items = getRenderableSources();

    if (!items.length) {
      sourcesBox.innerHTML = '';
      sourcesEmpty.classList.remove('hidden');
      renderActionDock();
      return;
    }

    sourcesEmpty.classList.add('hidden');
    sourcesBox.innerHTML = items.map(function (source) {
      const tagKey = source.kind === 'restored'
        ? 'restored'
        : (source.kind === 'file' ? 'source_kind_uploaded' : 'source_kind_session');
      return [
        '<span class="source-chip">',
        '  <span>' + escapeHtml(source.name) + '</span>',
        '  <span class="source-chip__tag">' + escapeHtml(t(tagKey)) + '</span>',
        '</span>',
      ].join('');
    }).join('');
    renderActionDock();
  }

  function renderChapterScope() {
    if (!window.RRApp.isLoggedIn()) {
      chapterGroups.innerHTML = '';
      chapterEmpty.classList.add('hidden');
      return;
    }

    const context = window.RRState.getSubjectContext();
    const structure = window.RRState.getCourseStructure();
    const review = window.RRState.getCurrentReview();

    if (!context.courseName) {
      chapterGroups.innerHTML = '';
      chapterNote.textContent = t('review_chapter_scope_need_course');
      chapterEmpty.textContent = t('review_chapter_scope_need_course');
      chapterEmpty.classList.remove('hidden');
      return;
    }

    if (!structure || !structure.hasStructure || !Array.isArray(structure.units) || !structure.units.length) {
      chapterGroups.innerHTML = '';
      chapterNote.textContent = review && review.selectedChapterLabels && review.selectedChapterLabels.length
        ? getSelectedChapterSummary(review)
        : t(currentGenerationMode === 'textbook'
          ? 'review_chapter_scope_textbook_copy'
          : (currentGenerationMode === 'combined' ? 'review_chapter_scope_combined_copy' : 'review_chapter_scope_copy'));
      chapterEmpty.textContent = review && review.selectedChapterLabels && review.selectedChapterLabels.length
        ? review.selectedChapterLabels.join(' · ')
        : t('review_chapter_scope_empty');
      chapterEmpty.classList.remove('hidden');
      return;
    }

    const allowedIds = new Set();
    structure.units.forEach(function (unit) {
      (unit.chapters || []).forEach(function (chapter) {
        if (chapter.id) {
          allowedIds.add(String(chapter.id));
        }
      });
    });
    const selectedIds = window.RRState.getSelectedChapterIds().filter(function (chapterId) {
      return allowedIds.has(String(chapterId));
    });
    if (selectedIds.length !== window.RRState.getSelectedChapterIds().length) {
      window.RRState.setSelectedChapterIds(selectedIds);
    }
    const selectedSet = new Set(selectedIds);

    chapterNote.textContent = selectedIds.length
      ? interpolate('review_chapter_selected_count', { n: selectedIds.length })
      : t(currentGenerationMode === 'textbook'
        ? 'review_chapter_scope_textbook_all'
        : (currentGenerationMode === 'combined' ? 'review_chapter_scope_combined_all' : 'review_chapter_scope_all'));
    chapterEmpty.classList.add('hidden');
    chapterGroups.innerHTML = structure.units.map(function (unit) {
      return [
        '<section class="chapter-group">',
        '  <div class="chapter-group__title">' + escapeHtml(unit.title || '') + '</div>',
        '  <div class="chapter-checklist">',
        (unit.chapters || []).map(function (chapter) {
          const chapterId = String(chapter.id || '');
          return [
            '    <label class="chapter-option">',
            '      <input type="checkbox" data-chapter-id="' + escapeHtml(chapterId) + '"' + (selectedSet.has(chapterId) ? ' checked' : '') + ' />',
            '      <span>' + escapeHtml(chapter.title || '') + '</span>',
            '    </label>',
          ].join('');
        }).join(''),
        '  </div>',
        '</section>',
      ].join('');
    }).join('');
  }

  function renderLengthButtons() {
    const buttons = document.querySelectorAll('[data-length]');
    buttons.forEach(function (button) {
      const active = button.getAttribute('data-length') === currentLength;
      button.classList.toggle('is-active', active);
    });
  }

  function syncLongModeAvailability() {
    const longButton = document.querySelector('[data-length="long"]');
    if (!longButton) {
      return;
    }

    longButton.disabled = false;
    longButton.title = '';
  }

  function renderDraftMeta(message) {
    charCount.textContent = formatCount(sourceText.value.trim().length);
    draftStatus.textContent = message || '';
    renderActionDock();
  }

  function setProgress(label, percentage) {
    progressWrap.classList.remove('hidden');
    progressBar.style.width = String(Math.max(0, Math.min(100, percentage || 0))) + '%';
    progressText.textContent = label || t('generating_long');
  }

  function resetProgress() {
    progressBar.style.width = '0%';
    progressText.textContent = t('generating_long');
    progressWrap.classList.add('hidden');
  }

  function renderOutput(review) {
    const current = review || window.RRState.getCurrentReview();
    if (!current || !current.text) {
      output.innerHTML = '';
      output.classList.add('hidden');
      outputMeta.textContent = '';
      outputEmpty.classList.remove('hidden');
      copyButton.disabled = true;
      exportMdButton.disabled = true;
      exportPdfButton.disabled = true;
      mockTestLink.classList.add('hidden');
      return;
    }

    outputEmpty.classList.add('hidden');
    output.classList.remove('hidden');
    copyButton.disabled = false;
    exportMdButton.disabled = false;
    exportPdfButton.disabled = false;
    mockTestLink.classList.remove('hidden');
    outputMeta.textContent = [
      kindLabel(current.format),
      window.RRApp.formatRelativeDate(current.createdAt),
      formatSubjectContext({ subjectCode: current.subjectCode, courseName: current.courseName }),
      formatExamContext(current.examType, current.examName),
      current.generationMode ? formatGenerationMode(current.generationMode) : '',
      current.selectedChapterLabels && current.selectedChapterLabels.length ? current.selectedChapterLabels.join(' · ') : '',
      current.textbookName ? t('course_textbook_badge') + ': ' + current.textbookName : '',
      (current.sourceLabels || []).join(' · '),
    ].filter(Boolean).join(' · ');
    window.RRApp.renderMarkdown(output, current.text);
  }

  function setGenerateBusy(busy) {
    generateBusy = Boolean(busy);
    generateButton.disabled = generateBusy || !canGenerate;
    generateTopButton.disabled = generateBusy || !canGenerate;
    generateButton.textContent = generateBusy ? t('generating') : t('generate_btn');
    generateTopButton.textContent = generateBusy ? t('generating') : t('generate_btn');
  }

  function buildPayload() {
    const sourcePayload = window.RRState.getReviewPayload();
    const courseMode = window.RRApp.isLoggedIn();
    const context = window.RRState.getSubjectContext();
    const inlineParts = sourcePayload.inlineTexts.concat(sourceText.value.trim() ? [sourceText.value.trim()] : []);
    return {
      format: formatSelect.value,
      lang: (document.documentElement.lang || '').toLowerCase().indexOf('en') === 0 ? 'en' : 'zh',
      length: currentLength,
      generation_mode: currentGenerationMode,
      subject_code: courseMode ? (context.subjectCode || undefined) : undefined,
      course_name: courseMode ? (context.courseName || undefined) : undefined,
      exam_type: examTypeSelect.value || undefined,
      exam_name: examNameInput.value.trim() || undefined,
      source_ids: sourcePayload.sourceIds.length ? sourcePayload.sourceIds : undefined,
      chapter_ids: courseMode && sourcePayload.chapterIds.length ? sourcePayload.chapterIds : undefined,
      text: inlineParts.length ? inlineParts.join('\n\n') : undefined,
      sourceLabels: sourcePayload.labels,
    };
  }

  function persistReview(data, payload) {
    return window.RRState.setCurrentReview({
      id: data.id ? String(data.id) : '',
      text: data.text || '',
      format: payload.format,
      length: payload.length,
      createdAt: new Date().toISOString(),
      sourceLabels: payload.sourceLabels,
      sourceIds: payload.source_ids || [],
      subjectCode: payload.subject_code,
      courseName: payload.course_name,
      examType: payload.exam_type,
      examName: payload.exam_name,
      selectedChapterIds: data.selected_chapter_ids || payload.chapter_ids || [],
      selectedChapterLabels: data.selected_chapter_labels || [],
      generationMode: data.generation_mode || payload.generation_mode || currentGenerationMode,
      textbookFileId: data.textbook_file_id || '',
      textbookName: getActiveTextbook() ? getActiveTextbook().filename : '',
    });
  }

  async function streamGenerate(payload) {
    let finalText = '';
    let reviewId = '';
    let failure = '';

    setProgress(t('gen_stage_condense'), 12);
    const stream = window.RRApp.streamSSE('/generate/stream', payload, {
      condense: function () {
        setProgress(t('gen_stage_condense'), 18);
      },
      chapters: function () {
        setProgress(t('gen_stage_chapters'), 34);
      },
      chapter: function (raw) {
        let info = {};
        try {
          info = JSON.parse(raw);
        } catch (_) {}
        const current = Number(info.i || 1);
        const total = Number(info.n || current || 1);
        const percent = 38 + Math.round((current / Math.max(total, 1)) * 32);
        setProgress(t('gen_stage_chapter_processing') + ' ' + current + '/' + total, percent);
      },
      section: function (raw) {
        let info = {};
        try {
          info = JSON.parse(raw);
        } catch (_) {}
        const title = info.sectionTitle || info.chapterTitle || '';
        setProgress(t('gen_stage_section_extract') + (title ? ' · ' + title : ''), 74);
      },
      assemble: function () {
        setProgress(t('gen_stage_assemble'), 90);
      },
      id: function (raw) {
        reviewId = String(raw || '').trim();
      },
      text: function (raw) {
        try {
          finalText = JSON.parse(raw).text || '';
        } catch (_) {
          finalText = raw;
        }
        setProgress(t('generate_done'), 100);
      },
      error: function (raw) {
        failure = raw || t('generate_failed');
      },
    });

    await stream.done;

    if (failure) {
      throw new Error(failure);
    }
    if (!finalText) {
      throw new Error(t('generate_failed'));
    }

    return { id: reviewId, text: finalText };
  }

  async function generateReview() {
    const payload = buildPayload();
    const textbookReady = currentGenerationMode !== 'materials' && Boolean(getActiveTextbook());
    if (!payload.text && (!payload.source_ids || !payload.source_ids.length) && (!payload.chapter_ids || !payload.chapter_ids.length) && !textbookReady) {
      window.showToast('info', t('review_no_sources'));
      sourceText.focus();
      return;
    }

    setGenerateBusy(true);
    window.RRState.setDraftText(sourceText.value);
    renderDraftMeta(t('draft_saved'));

    try {
      let result = null;
      if (payload.format === 'review_sheet_pro' && payload.length === 'long') {
        result = await streamGenerate(payload);
      } else {
        resetProgress();
        setProgress(t('generating'), 24);
        result = await window.RRApp.fetchJSON('/generate', {
          method: 'POST',
          headers: window.RRApp.authHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
        setProgress(t('generate_done'), 100);
      }

      const review = persistReview(result, payload);
      renderExamControls(review);
      renderChapterScope();
      renderOutput(review);
      await window.RRApp.refreshShellStatus();
      window.showToast('success', t('generate_done'));
    } catch (error) {
      window.showToast('error', error.message || t('generate_failed'));
      setProgress(error.message || t('generate_failed'), 100);
    } finally {
      setGenerateBusy(false);
    }
  }

  function saveDraftSoon() {
    window.clearTimeout(draftTimer);
    draftTimer = window.setTimeout(function () {
      window.RRState.setDraftText(sourceText.value);
      renderDraftMeta(t('draft_saved'));
    }, 220);
  }

  formatSelect.value = getStoredValue(FORMAT_KEY, 'review_sheet_pro');
  currentLength = getStoredValue(LENGTH_KEY, 'medium');
  sourceText.value = window.RRState.getDraftText();
  syncModeUI();
  renderExamControls();
  renderGenerationModeControls();
  renderSources();
  renderLengthButtons();
  syncLongModeAvailability();
  renderDraftMeta('');
  renderOutput();
  await loadCourseStructure();
  setGenerateBusy(false);

  examTypeSelect.addEventListener('change', function () {
    renderChapterScope();
  });
  examNameInput.addEventListener('input', function () {
    renderChapterScope();
  });
  generationModeGroup.addEventListener('click', function (event) {
    const button = event.target.closest('[data-generation-mode]');
    if (!button || button.disabled) {
      return;
    }
    currentGenerationMode = button.getAttribute('data-generation-mode') || 'materials';
    window.RRState.setGenerationMode(currentGenerationMode);
    renderGenerationModeControls();
    renderChapterScope();
    renderActionDock();
  });
  chapterGroups.addEventListener('change', function (event) {
    const input = event.target;
    if (!input || !input.matches('[data-chapter-id]')) {
      return;
    }
    const selectedIds = Array.from(chapterGroups.querySelectorAll('[data-chapter-id]:checked')).map(function (checkbox) {
      return String(checkbox.getAttribute('data-chapter-id') || '');
    }).filter(Boolean);
    window.RRState.setSelectedChapterIds(selectedIds);
    renderChapterScope();
  });
  formatSelect.addEventListener('change', function () {
    setStoredValue(FORMAT_KEY, formatSelect.value);
  });
  document.querySelectorAll('[data-length]').forEach(function (button) {
    button.addEventListener('click', function () {
      if (button.disabled) {
        return;
      }
      currentLength = button.getAttribute('data-length') || 'medium';
      setStoredValue(LENGTH_KEY, currentLength);
      renderLengthButtons();
    });
  });
  sourceText.addEventListener('input', function () {
    renderDraftMeta('');
    saveDraftSoon();
  });
  generateButton.addEventListener('click', generateReview);
  generateTopButton.addEventListener('click', generateReview);
  copyButton.addEventListener('click', async function () {
    const review = window.RRState.getCurrentReview();
    if (!review || !review.text) {
      window.showToast('info', t('export_no_content'));
      return;
    }
    await navigator.clipboard.writeText(review.text);
    window.showToast('success', t('copied'));
  });
  exportMdButton.addEventListener('click', function () {
    const review = window.RRState.getCurrentReview();
    if (!review || !review.text) {
      window.showToast('info', t('export_no_content'));
      return;
    }
    window.RRApp.downloadText('rrviewer-review.md', review.text);
  });
  exportPdfButton.addEventListener('click', function () {
    const review = window.RRState.getCurrentReview();
    if (!review || !review.text) {
      window.showToast('info', t('export_no_content'));
      return;
    }
    if (!window.RRApp.printElement(document.title, output)) {
      window.showToast('error', t('request_failed'));
    }
  });
  mockTestLink.addEventListener('click', function (e) {
    const review = window.RRState.getCurrentReview();
    if (!review || !review.text) {
      e.preventDefault();
      return;
    }
    try {
      sessionStorage.setItem('review_text', review.text);
    } catch (_) {}
    var lang = (document.documentElement.lang || '').toLowerCase().indexOf('en') === 0 ? 'en' : 'zh';
    mockTestLink.href = 'mocktest.html?lang=' + lang;
  });
  document.addEventListener('rr:langchange', function () {
    syncModeUI();
    renderExamControls();
    renderGenerationModeControls();
    renderSources();
    renderChapterScope();
    renderLengthButtons();
    syncLongModeAvailability();
    renderOutput();
  });
});