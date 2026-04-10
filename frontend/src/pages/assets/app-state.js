(function () {
  const STORE = window.sessionStorage;
  const KEYS = {
    draftLegacy: 'rr_draft_text_v2',
    reviewLegacy: 'rr_current_review_v2',
    sourcesLegacy: 'rr_sources_v2',
    activeSubject: 'rr_subject_context_v1',
    sessions: 'rr_subject_sessions_v1',
  };

  const SUBJECT_OPTIONS = [
    { value: '', labelKey: 'subject_option_none' },
    { value: 'math', labelKey: 'subject_math' },
    { value: 'physics', labelKey: 'subject_physics' },
    { value: 'chemistry', labelKey: 'subject_chemistry' },
    { value: 'biology', labelKey: 'subject_biology' },
    { value: 'chinese', labelKey: 'subject_chinese' },
    { value: 'english', labelKey: 'subject_english' },
    { value: 'history', labelKey: 'subject_history' },
    { value: 'geography', labelKey: 'subject_geography' },
    { value: 'politics', labelKey: 'subject_politics' },
    { value: 'computer_science', labelKey: 'subject_computer_science' },
    { value: 'economics', labelKey: 'subject_economics' },
    { value: 'other', labelKey: 'subject_other' },
  ];

  const EXAM_OPTIONS = [
    { value: '', labelKey: 'exam_option_none' },
    { value: 'quiz', labelKey: 'exam_quiz' },
    { value: 'midterm', labelKey: 'exam_midterm' },
    { value: 'final', labelKey: 'exam_final' },
    { value: 'mock', labelKey: 'exam_mock' },
    { value: 'competition', labelKey: 'exam_competition' },
    { value: 'other', labelKey: 'exam_other' },
  ];

  function readJSON(key, fallbackValue) {
    try {
      const raw = STORE.getItem(key);
      return raw ? JSON.parse(raw) : fallbackValue;
    } catch (_) {
      return fallbackValue;
    }
  }

  function writeJSON(key, value) {
    try {
      STORE.setItem(key, JSON.stringify(value));
    } catch (e) {
      // Quota exceeded — trim content from session sources and retry
      if (e && e.name === 'QuotaExceededError') {
        try {
          var slim = JSON.parse(JSON.stringify(value));
          trimSessionMap(slim);
          STORE.setItem(key, JSON.stringify(slim));
        } catch (_) {
          // Last resort: clear this key so the app doesn't get stuck
          STORE.removeItem(key);
        }
      }
    }
  }

  // Strip bulky content from session sources to fit within storage quota
  function trimSessionMap(map) {
    if (!map || typeof map !== 'object') return;
    Object.keys(map).forEach(function (key) {
      var bucket = map[key];
      if (!bucket || !Array.isArray(bucket.sources)) return;
      bucket.sources.forEach(function (src) {
        if (src.kind === 'session' && src.content && src.content.length > 2000) {
          src.content = src.content.slice(0, 2000);
          src.chars = src.content.length;
        }
      });
    });
  }

  function cleanOptionalText(value) {
    const cleaned = String(value || '').trim();
    return cleaned || '';
  }

  function normalizeSubjectCode(value) {
    const cleaned = cleanOptionalText(value);
    return cleaned ? cleaned.toLowerCase() : '';
  }

  function normalizeExamType(value) {
    const cleaned = cleanOptionalText(value);
    return cleaned ? cleaned.toLowerCase() : '';
  }

  function normalizeGenerationMode(value) {
    const cleaned = cleanOptionalText(value).toLowerCase();
    return ['materials', 'textbook', 'combined'].indexOf(cleaned) >= 0 ? cleaned : 'materials';
  }

  function uniqueStringArray(values) {
    const seen = new Set();
    return (values || []).map(function (value) {
      return String(value || '').trim();
    }).filter(function (value) {
      if (!value || seen.has(value)) {
        return false;
      }
      seen.add(value);
      return true;
    });
  }

  function normalizeChapterMatch(item) {
    const match = item || {};
    const chapterId = match.chapterId || match.chapter_id;
    return {
      chapterId: chapterId ? String(chapterId) : '',
      chapterTitle: String(match.chapterTitle || match.chapter_title || ''),
      unitId: match.unitId || match.unit_id ? String(match.unitId || match.unit_id) : '',
      unitTitle: String(match.unitTitle || match.unit_title || ''),
      confidence: Number(match.confidence || 0),
      mappingSource: String(match.mappingSource || match.mapping_source || 'manual'),
      label: String(match.label || ''),
    };
  }

  function normalizeCourseStructure(structure) {
    if (!structure || typeof structure !== 'object') {
      return null;
    }

    const units = Array.isArray(structure.units) ? structure.units : [];
    const textbook = structure.textbook && typeof structure.textbook === 'object'
      ? {
          fileId: structure.textbook.fileId || structure.textbook.file_id ? String(structure.textbook.fileId || structure.textbook.file_id) : '',
          filename: cleanOptionalText(structure.textbook.filename) || '',
          contentType: cleanOptionalText(structure.textbook.contentType || structure.textbook.content_type),
          size: Number(structure.textbook.size || 0),
          createdAt: structure.textbook.createdAt || structure.textbook.created_at || '',
        }
      : null;
    return {
      id: structure.id ? String(structure.id) : '',
      subjectCode: normalizeSubjectCode(structure.subjectCode || structure.subject_code),
      courseName: cleanOptionalText(structure.courseName || structure.course_name),
      textbook: textbook && textbook.fileId ? textbook : null,
      unitCount: Number(structure.unitCount || structure.unit_count || units.length || 0),
      chapterCount: Number(structure.chapterCount || structure.chapter_count || 0),
      hasStructure: Boolean(structure.hasStructure || structure.has_structure || Number(structure.chapterCount || structure.chapter_count || 0) > 0),
      units: units.map(function (unit, unitIndex) {
        const chapters = Array.isArray(unit.chapters) ? unit.chapters : [];
        return {
          id: unit.id ? String(unit.id) : '',
          title: cleanOptionalText(unit.title) || '',
          orderIndex: Number(unit.orderIndex || unit.order_index || unitIndex || 0),
          chapters: chapters.map(function (chapter, chapterIndex) {
            return {
              id: chapter.id ? String(chapter.id) : '',
              title: cleanOptionalText(chapter.title) || '',
              orderIndex: Number(chapter.orderIndex || chapter.order_index || chapterIndex || 0),
              unitId: chapter.unitId || chapter.unit_id ? String(chapter.unitId || chapter.unit_id) : '',
            };
          }),
        };
      }),
    };
  }

  function createSessionSourceId() {
    return 'session:' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function buildSubjectKey(subjectCode, courseName) {
    return encodeURIComponent(subjectCode || '') + '|' + encodeURIComponent(String(courseName || '').trim().toLowerCase());
  }

  function normalizeSubjectContext(input) {
    const raw = input || {};
    const subjectCode = normalizeSubjectCode(raw.subjectCode || raw.subject_code);
    const courseName = cleanOptionalText(raw.courseName || raw.course_name);
    return {
      subjectCode: subjectCode,
      courseName: courseName,
      key: buildSubjectKey(subjectCode, courseName),
    };
  }

  function getActiveSubjectContext() {
    const raw = readJSON(KEYS.activeSubject, null);
    const context = normalizeSubjectContext(raw);
    if (!raw) {
      writeJSON(KEYS.activeSubject, {
        subjectCode: context.subjectCode,
        courseName: context.courseName,
      });
    }
    return context;
  }

  function createEmptyBucket(context) {
    return {
      subjectCode: context.subjectCode,
      courseName: context.courseName,
      sources: [],
      draftText: '',
      courseStructure: null,
      selectedChapterIds: [],
      generationMode: 'materials',
      review: null,
    };
  }

  function normalizeSource(item) {
    const source = item || {};
    const kind = source.kind === 'file' ? 'file' : 'session';
    const fileId = kind === 'file' && source.fileId ? Number(source.fileId) : null;
    const id = source.id || (kind === 'file' && fileId ? 'file:' + fileId : createSessionSourceId());
    const content = kind === 'session' ? String(source.content || '') : '';
    const chars = Number(source.chars || source.size || content.length || 0);

    return {
      id: id,
      kind: kind,
      fileId: fileId,
      name: String(source.name || source.filename || 'Untitled'),
      content: content,
      chars: Number.isFinite(chars) ? chars : 0,
      createdAt: source.createdAt || source.created_at || new Date().toISOString(),
      selected: Boolean(source.selected),
      subjectCode: normalizeSubjectCode(source.subjectCode || source.subject_code),
      courseName: cleanOptionalText(source.courseName || source.course_name),
      chapterMatches: Array.isArray(source.chapterMatches || source.chapter_matches)
        ? (source.chapterMatches || source.chapter_matches).map(normalizeChapterMatch).filter(function (match) { return match.chapterId; })
        : [],
    };
  }

  function normalizeReview(review, fallbackContext) {
    if (!review || typeof review !== 'object') {
      return null;
    }

    const context = fallbackContext || getActiveSubjectContext();
    const normalized = {
      id: review.id ? String(review.id) : '',
      text: String(review.text || ''),
      format: String(review.format || review.kind || 'review_sheet_pro'),
      length: String(review.length || 'medium'),
      createdAt: review.createdAt || review.created_at || new Date().toISOString(),
      sourceLabels: Array.isArray(review.sourceLabels) ? review.sourceLabels : (Array.isArray(review.source_labels) ? review.source_labels : []),
      sourceIds: Array.isArray(review.sourceIds) ? review.sourceIds.map(String) : (Array.isArray(review.source_ids) ? review.source_ids.map(String) : []),
      subjectCode: normalizeSubjectCode(review.subjectCode || review.subject_code) || context.subjectCode,
      courseName: cleanOptionalText(review.courseName || review.course_name) || context.courseName,
      examType: normalizeExamType(review.examType || review.exam_type),
      examName: cleanOptionalText(review.examName || review.exam_name),
      selectedChapterIds: uniqueStringArray(review.selectedChapterIds || review.selected_chapter_ids || []),
      selectedChapterLabels: Array.isArray(review.selectedChapterLabels || review.selected_chapter_labels)
        ? (review.selectedChapterLabels || review.selected_chapter_labels).map(function (label) { return String(label || '').trim(); }).filter(Boolean)
        : [],
      generationMode: normalizeGenerationMode(review.generationMode || review.generation_mode),
      textbookFileId: review.textbookFileId || review.textbook_file_id ? String(review.textbookFileId || review.textbook_file_id) : '',
      textbookName: cleanOptionalText(review.textbookName || review.textbook_name),
    };

    return normalized.id || normalized.text ? normalized : null;
  }

  function readLegacyReview(context) {
    const storedReview = normalizeReview(readJSON(KEYS.reviewLegacy, null), context);
    if (storedReview) {
      return storedReview;
    }

    try {
      const legacyId = STORE.getItem('review_id') || '';
      const legacyText = STORE.getItem('review') || '';
      if (!legacyId && !legacyText) {
        return null;
      }
      return normalizeReview({
        id: legacyId,
        text: legacyText,
        format: 'review_sheet_pro',
        length: 'medium',
        createdAt: new Date().toISOString(),
      }, context);
    } catch (_) {
      return null;
    }
  }

  function normalizeBucket(bucket, context) {
    const currentContext = context || getActiveSubjectContext();
    const sourceItems = Array.isArray(bucket && bucket.sources) ? bucket.sources.map(normalizeSource) : [];

    return {
      subjectCode: currentContext.subjectCode,
      courseName: currentContext.courseName,
      sources: sourceItems,
      draftText: String(bucket && bucket.draftText ? bucket.draftText : ''),
      courseStructure: normalizeCourseStructure(bucket && bucket.courseStructure),
      selectedChapterIds: uniqueStringArray(bucket && bucket.selectedChapterIds),
      generationMode: normalizeGenerationMode(bucket && bucket.generationMode),
      review: normalizeReview(bucket && bucket.review, currentContext),
    };
  }

  function syncLegacyMirror(bucket) {
    const current = bucket || normalizeBucket(getCurrentBucket(), getActiveSubjectContext());
    writeJSON(KEYS.sourcesLegacy, current.sources || []);

    try {
      if (current.draftText) {
        STORE.setItem(KEYS.draftLegacy, current.draftText);
        STORE.setItem('rr_draft', current.draftText);
      } else {
        STORE.removeItem(KEYS.draftLegacy);
        STORE.removeItem('rr_draft');
      }

      if (current.review) {
        writeJSON(KEYS.reviewLegacy, current.review);
        if (current.review.id) {
          STORE.setItem('review_id', current.review.id);
        } else {
          STORE.removeItem('review_id');
        }
        STORE.setItem('review', current.review.text || '');
        STORE.setItem('review_text', current.review.text || '');
      } else {
        STORE.removeItem(KEYS.reviewLegacy);
        STORE.removeItem('review_id');
        STORE.removeItem('review');
        STORE.removeItem('review_text');
      }
    } catch (_) {}
  }

  function migrateLegacyState() {
    const activeContext = getActiveSubjectContext();
    const draftText = String(STORE.getItem(KEYS.draftLegacy) || STORE.getItem('rr_draft') || '');
    const review = readLegacyReview(activeContext);
    const sources = readJSON(KEYS.sourcesLegacy, []);
    const map = {};

    if ((Array.isArray(sources) && sources.length) || draftText || review) {
      map[activeContext.key] = normalizeBucket({
        sources: sources,
        draftText: draftText,
        review: review,
      }, activeContext);
    }

    writeJSON(KEYS.sessions, map);
    return map;
  }

  function getSessionMap() {
    const stored = readJSON(KEYS.sessions, null);
    if (stored && typeof stored === 'object' && !Array.isArray(stored)) {
      return stored;
    }
    return migrateLegacyState();
  }

  function getCurrentBucket() {
    const context = getActiveSubjectContext();
    const map = getSessionMap();
    if (!map[context.key]) {
      map[context.key] = createEmptyBucket(context);
      writeJSON(KEYS.sessions, map);
    }
    return normalizeBucket(map[context.key], context);
  }

  function updateCurrentBucket(transform) {
    const context = getActiveSubjectContext();
    const map = getSessionMap();
    const bucket = normalizeBucket(map[context.key] || createEmptyBucket(context), context);
    const nextBucket = normalizeBucket(transform(bucket) || bucket, context);
    map[context.key] = nextBucket;
    writeJSON(KEYS.sessions, map);
    syncLegacyMirror(nextBucket);
    return nextBucket;
  }

  function getSubjectOptions() {
    return SUBJECT_OPTIONS.map(function (item) {
      return { value: item.value, labelKey: item.labelKey };
    });
  }

  function getExamOptions() {
    return EXAM_OPTIONS.map(function (item) {
      return { value: item.value, labelKey: item.labelKey };
    });
  }

  function getSubjectLabelKey(subjectCode) {
    const match = SUBJECT_OPTIONS.find(function (item) {
      return item.value === normalizeSubjectCode(subjectCode);
    });
    return match ? match.labelKey : 'subject_other';
  }

  function getExamLabelKey(examType) {
    const match = EXAM_OPTIONS.find(function (item) {
      return item.value === normalizeExamType(examType);
    });
    return match ? match.labelKey : 'exam_other';
  }

  function setSubjectContext(context) {
    const next = normalizeSubjectContext(context);
    writeJSON(KEYS.activeSubject, {
      subjectCode: next.subjectCode,
      courseName: next.courseName,
    });

    const map = getSessionMap();
    if (!map[next.key]) {
      map[next.key] = createEmptyBucket(next);
      writeJSON(KEYS.sessions, map);
    }
    syncLegacyMirror(normalizeBucket(map[next.key], next));
    return next;
  }

  function getSubjectContext() {
    return getActiveSubjectContext();
  }

  function getSources() {
    return getCurrentBucket().sources;
  }

  function setSources(items) {
    return updateCurrentBucket(function (bucket) {
      bucket.sources = (items || []).map(normalizeSource);
      return bucket;
    }).sources;
  }

  function upsertSource(item) {
    const normalized = normalizeSource(item);
    const sources = getSources();
    const next = [];
    let replaced = false;

    sources.forEach(function (source) {
      if (source.id === normalized.id) {
        next.push({ ...source, ...normalized });
        replaced = true;
      } else {
        next.push(source);
      }
    });

    if (!replaced) {
      next.unshift(normalized);
    }

    return setSources(next);
  }

  function mergeServerSources(items) {
    const existing = getSources();
    const serverMap = new Map();
    existing.forEach(function (source) {
      if (source.kind === 'file') {
        serverMap.set(source.id, source);
      }
    });

    const merged = existing.filter(function (source) {
      return source.kind !== 'file';
    });

    (items || []).forEach(function (file) {
      const id = 'file:' + String(file.id);
      const previous = serverMap.get(id) || {};
      merged.push(normalizeSource({
        id: id,
        kind: 'file',
        fileId: file.id,
        name: file.filename,
        chars: file.size || previous.chars,
        createdAt: file.created_at || previous.createdAt,
        selected: previous.selected,
        subjectCode: file.subject_code,
        courseName: file.course_name,
        chapterMatches: file.chapter_matches || previous.chapterMatches,
      }));
    });

    merged.sort(function (left, right) {
      return String(right.createdAt || '').localeCompare(String(left.createdAt || ''));
    });
    return setSources(merged);
  }

  function addUploadedSource(payload) {
    const data = payload || {};
    if (data.file_id) {
      return upsertSource({
        id: 'file:' + String(data.file_id),
        kind: 'file',
        fileId: data.file_id,
        name: (data.meta && data.meta.filename) || data.name || 'Uploaded file',
        chars: data.chars || 0,
        createdAt: new Date().toISOString(),
        selected: true,
        subjectCode: data.subject_code,
        courseName: data.course_name,
        chapterMatches: data.chapter_matches,
      });
    }

    return upsertSource({
      id: createSessionSourceId(),
      kind: 'session',
      name: data.name || (data.meta && data.meta.filename) || 'Session source',
      content: String(data.content || ''),
      chars: Number(data.chars || (data.content ? data.content.length : 0) || 0),
      createdAt: new Date().toISOString(),
      selected: true,
    });
  }

  function removeSource(id) {
    return setSources(getSources().filter(function (source) {
      return source.id !== id;
    }));
  }

  function clearSessionSources() {
    return setSources(getSources().filter(function (source) {
      return source.kind === 'file';
    }));
  }

  function setSourceSelected(id, selected) {
    return setSources(getSources().map(function (source) {
      if (source.id !== id) {
        return source;
      }
      return { ...source, selected: Boolean(selected) };
    }));
  }

  function toggleSourceSelected(id) {
    const source = getSources().find(function (item) {
      return item.id === id;
    });
    return setSourceSelected(id, source ? !source.selected : true);
  }

  function getSelectedSources() {
    return getSources().filter(function (source) {
      return source.selected;
    });
  }

  function getDraftText() {
    return getCurrentBucket().draftText;
  }

  function setDraftText(text) {
    const value = String(text || '');
    updateCurrentBucket(function (bucket) {
      bucket.draftText = value;
      return bucket;
    });
    return value;
  }

  function clearDraftText() {
    updateCurrentBucket(function (bucket) {
      bucket.draftText = '';
      return bucket;
    });
  }

  function getCurrentReview() {
    return getCurrentBucket().review;
  }

  function getCourseStructure() {
    return getCurrentBucket().courseStructure;
  }

  function setCourseStructure(structure) {
    const normalized = normalizeCourseStructure(structure);
    updateCurrentBucket(function (bucket) {
      bucket.courseStructure = normalized;
      return bucket;
    });
    return normalized;
  }

  function getSelectedChapterIds() {
    return getCurrentBucket().selectedChapterIds;
  }

  function getGenerationMode() {
    return getCurrentBucket().generationMode;
  }

  function setSelectedChapterIds(chapterIds) {
    const normalized = uniqueStringArray(chapterIds);
    updateCurrentBucket(function (bucket) {
      bucket.selectedChapterIds = normalized;
      return bucket;
    });
    return normalized;
  }

  function setGenerationMode(mode) {
    const normalized = normalizeGenerationMode(mode);
    updateCurrentBucket(function (bucket) {
      bucket.generationMode = normalized;
      return bucket;
    });
    return normalized;
  }

  function updateSourceChapterMatches(sourceId, chapterMatches) {
    return setSources(getSources().map(function (source) {
      if (source.id !== sourceId) {
        return source;
      }
      return {
        ...source,
        chapterMatches: Array.isArray(chapterMatches) ? chapterMatches.map(normalizeChapterMatch).filter(function (match) { return match.chapterId; }) : [],
      };
    }));
  }

  function setCurrentReview(review) {
    const context = getActiveSubjectContext();
    const normalized = normalizeReview(review, context);
    updateCurrentBucket(function (bucket) {
      bucket.review = normalized;
      bucket.selectedChapterIds = normalized ? normalized.selectedChapterIds : [];
      bucket.generationMode = normalized ? normalized.generationMode : bucket.generationMode;
      return bucket;
    });
    return normalized;
  }

  function clearCurrentReview() {
    updateCurrentBucket(function (bucket) {
      bucket.review = null;
      return bucket;
    });
  }

  function getSummary() {
    return {
      subject: getSubjectContext(),
      selectedCount: getSelectedSources().length,
      draftChars: getDraftText().trim().length,
      selectedChapterCount: getSelectedChapterIds().length,
      generationMode: getGenerationMode(),
      courseStructure: getCourseStructure(),
      review: getCurrentReview(),
    };
  }

  function getReviewPayload() {
    const selected = getSelectedSources();
    const context = getSubjectContext();
    return {
      subjectCode: context.subjectCode,
      courseName: context.courseName,
      generationMode: getGenerationMode(),
      sourceIds: selected.filter(function (source) {
        return source.kind === 'file' && source.fileId;
      }).map(function (source) {
        return String(source.fileId);
      }),
      chapterIds: getSelectedChapterIds(),
      inlineTexts: selected.filter(function (source) {
        return source.kind === 'session' && source.content;
      }).map(function (source) {
        return source.content;
      }),
      labels: selected.map(function (source) {
        return source.name;
      }),
    };
  }

  syncLegacyMirror(getCurrentBucket());

  window.RRState = {
    addUploadedSource: addUploadedSource,
    clearCurrentReview: clearCurrentReview,
    getCourseStructure: getCourseStructure,
    clearDraftText: clearDraftText,
    clearSessionSources: clearSessionSources,
    getCurrentReview: getCurrentReview,
    getDraftText: getDraftText,
    getExamLabelKey: getExamLabelKey,
    getExamOptions: getExamOptions,
    getGenerationMode: getGenerationMode,
    getReviewPayload: getReviewPayload,
    getSelectedChapterIds: getSelectedChapterIds,
    getSelectedSources: getSelectedSources,
    getSources: getSources,
    getSubjectContext: getSubjectContext,
    getSubjectLabelKey: getSubjectLabelKey,
    getSubjectOptions: getSubjectOptions,
    getSummary: getSummary,
    mergeServerSources: mergeServerSources,
    removeSource: removeSource,
    setCourseStructure: setCourseStructure,
    setCurrentReview: setCurrentReview,
    setDraftText: setDraftText,
    setGenerationMode: setGenerationMode,
    setSelectedChapterIds: setSelectedChapterIds,
    setSourceSelected: setSourceSelected,
    setSubjectContext: setSubjectContext,
    toggleSourceSelected: toggleSourceSelected,
    updateSourceChapterMatches: updateSourceChapterMatches,
  };
})();