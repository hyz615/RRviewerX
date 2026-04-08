document.addEventListener('DOMContentLoaded', async function () {
  const shellContext = await window.RRApp.initPage('review');

  const _initContext = window.RRState.getSubjectContext();
  if (!_initContext || !_initContext.subjectCode) {
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
  const chapterNote = document.getElementById('review-chapter-note');
  const chapterGroups = document.getElementById('review-chapter-groups');
  const chapterEmpty = document.getElementById('review-chapter-empty');

  let draftTimer = 0;
  let currentLength = 'medium';

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

  async function loadCourseStructure() {
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
    const selected = window.RRState.getSelectedSources();
    const currentReview = window.RRState.getCurrentReview();
    const restored = !selected.length && currentReview && Array.isArray(currentReview.sourceLabels)
      ? currentReview.sourceLabels.map(function (label) {
          return { name: label, kind: 'restored' };
        })
      : [];
    const items = selected.length ? selected : restored;

    if (!items.length) {
      sourcesBox.innerHTML = '';
      sourcesEmpty.classList.remove('hidden');
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
  }

  function renderChapterScope() {
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
        : t('review_chapter_scope_copy');
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
      : t('review_chapter_scope_all');
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

    const canUseLong = Boolean(shellContext && shellContext.quota && shellContext.quota.vip);
    longButton.disabled = !canUseLong;
    longButton.title = canUseLong ? '' : t('vip_only_long');
    if (!canUseLong && currentLength === 'long') {
      currentLength = 'medium';
      setStoredValue(LENGTH_KEY, currentLength);
      renderLengthButtons();
    }
  }

  function renderDraftMeta(message) {
    charCount.textContent = formatCount(sourceText.value.trim().length);
    draftStatus.textContent = message || '';
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
      current.selectedChapterLabels && current.selectedChapterLabels.length ? current.selectedChapterLabels.join(' · ') : '',
      (current.sourceLabels || []).join(' · '),
    ].filter(Boolean).join(' · ');
    window.RRApp.renderMarkdown(output, current.text);
  }

  function setGenerateBusy(busy) {
    generateButton.disabled = Boolean(busy);
    generateButton.textContent = busy ? t('generating') : t('generate_btn');
  }

  function buildPayload() {
    const sourcePayload = window.RRState.getReviewPayload();
    const inlineParts = sourcePayload.inlineTexts.concat(sourceText.value.trim() ? [sourceText.value.trim()] : []);
    return {
      format: formatSelect.value,
      lang: (document.documentElement.lang || '').toLowerCase().indexOf('en') === 0 ? 'en' : 'zh',
      length: currentLength,
      subject_code: window.RRState.getSubjectContext().subjectCode || undefined,
      course_name: window.RRState.getSubjectContext().courseName || undefined,
      exam_type: examTypeSelect.value || undefined,
      exam_name: examNameInput.value.trim() || undefined,
      source_ids: sourcePayload.sourceIds.length ? sourcePayload.sourceIds : undefined,
      chapter_ids: sourcePayload.chapterIds.length ? sourcePayload.chapterIds : undefined,
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
    if (!payload.text && (!payload.source_ids || !payload.source_ids.length) && (!payload.chapter_ids || !payload.chapter_ids.length)) {
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
      try {
        if (!window.RRApp.isLoggedIn()) {
          localStorage.setItem('rr_trial', 'used');
        }
      } catch (_) {}
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
  renderExamControls();
  renderSources();
  renderLengthButtons();
  syncLongModeAvailability();
  renderDraftMeta('');
  renderOutput();
  await loadCourseStructure();

  examTypeSelect.addEventListener('change', function () {
    renderChapterScope();
  });
  examNameInput.addEventListener('input', function () {
    renderChapterScope();
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
  mockTestLink.addEventListener('click', function () {
    const review = window.RRState.getCurrentReview();
    if (!review || !review.text) {
      return;
    }
    try {
      sessionStorage.setItem('review_text', review.text);
    } catch (_) {}
  });
  document.addEventListener('rr:langchange', function () {
    renderExamControls();
    renderSources();
    renderChapterScope();
    renderLengthButtons();
    syncLongModeAvailability();
    renderOutput();
  });
});