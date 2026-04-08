document.addEventListener('DOMContentLoaded', async function () {
  await window.RRApp.initPage('workspace');

  const guestSection = document.getElementById('workspace-guest');
  const memberSection = document.getElementById('workspace-member');
  const courseGrid = document.getElementById('course-grid');
  const courseGridEmpty = document.getElementById('course-grid-empty');
  const newCourseBtn = document.getElementById('btn-new-course');
  const dialog = document.getElementById('new-course-dialog');
  const dialogSubject = document.getElementById('dialog-subject');
  const dialogCourseName = document.getElementById('dialog-course-name');
  const dialogConfirm = document.getElementById('btn-dialog-confirm');
  const dialogCancel = document.getElementById('btn-dialog-cancel');

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

  function subjectCssKey(subjectCode) {
    var map = {
      math: 'math', physics: 'physics', chemistry: 'chemistry',
      biology: 'biology', chinese: 'chinese', english: 'english',
      history: 'history', geography: 'geography', politics: 'politics',
      computer_science: 'cs', economics: 'economics',
    };
    return map[subjectCode] || 'other';
  }

  function populateSubjectSelect(select, selectedValue) {
    var options = window.RRState.getSubjectOptions();
    var current = String(selectedValue || '');
    select.innerHTML = options.map(function (opt) {
      if (opt.value === '') return '';
      return '<option value="' + escapeHtml(opt.value) + '">' + escapeHtml(t(opt.labelKey)) + '</option>';
    }).filter(Boolean).join('');
    if (current) {
      select.value = current;
    }
  }

  function readAllBuckets() {
    try {
      var raw = sessionStorage.getItem('rr_subject_sessions_v1');
      var parsed = raw ? JSON.parse(raw) : {};
      var normalized = normalizeBuckets(parsed);
      if (normalized.changed) {
        sessionStorage.setItem('rr_subject_sessions_v1', JSON.stringify(normalized.map));
      }
      return normalized.map;
    } catch (_) {
      return {};
    }
  }

  function buildCourseKey(subjectCode, courseName) {
    return encodeURIComponent(String(subjectCode || '').trim().toLowerCase()) + '|' + encodeURIComponent(String(courseName || '').trim().toLowerCase());
  }

  function pickCourseName(primary, secondary) {
    var first = String(primary || '').trim();
    var second = String(secondary || '').trim();
    if (first && first !== first.toLowerCase()) {
      return first;
    }
    if (second && second !== second.toLowerCase()) {
      return second;
    }
    return first || second;
  }

  function uniqueChapterIds(values) {
    var seen = {};
    return (values || []).map(function (value) {
      return String(value || '').trim();
    }).filter(function (value) {
      if (!value || seen[value]) {
        return false;
      }
      seen[value] = true;
      return true;
    });
  }

  function mergeSources(left, right) {
    var merged = [];
    var indexById = {};

    function appendList(list) {
      (list || []).forEach(function (item) {
        if (!item || !item.id) {
          return;
        }
        if (indexById[item.id] === undefined) {
          indexById[item.id] = merged.length;
          merged.push(item);
          return;
        }
        var existingIndex = indexById[item.id];
        var existing = merged[existingIndex] || {};
        merged[existingIndex] = Object.assign({}, existing, item, {
          chapterMatches: Array.isArray(item.chapterMatches) && item.chapterMatches.length
            ? item.chapterMatches
            : (Array.isArray(existing.chapterMatches) ? existing.chapterMatches : []),
          courseName: pickCourseName(item.courseName, existing.courseName),
        });
      });
    }

    appendList(left);
    appendList(right);
    return merged;
  }

  function pickLatestReview(left, right) {
    if (!left) {
      return right || null;
    }
    if (!right) {
      return left;
    }
    return String(right.createdAt || '') > String(left.createdAt || '') ? right : left;
  }

  function mergeBucket(existing, incoming) {
    if (!existing) {
      return incoming;
    }
    return {
      subjectCode: String(incoming.subjectCode || existing.subjectCode || '').trim().toLowerCase(),
      courseName: pickCourseName(existing.courseName, incoming.courseName),
      sources: mergeSources(existing.sources, incoming.sources),
      draftText: String(existing.draftText || '').length >= String(incoming.draftText || '').length
        ? String(existing.draftText || '')
        : String(incoming.draftText || ''),
      courseStructure: (incoming.courseStructure && incoming.courseStructure.hasStructure)
        ? incoming.courseStructure
        : (existing.courseStructure || incoming.courseStructure || null),
      selectedChapterIds: uniqueChapterIds((existing.selectedChapterIds || []).concat(incoming.selectedChapterIds || [])),
      review: pickLatestReview(existing.review, incoming.review),
    };
  }

  function normalizeBuckets(rawMap) {
    var sourceMap = rawMap && typeof rawMap === 'object' ? rawMap : {};
    var normalized = {};
    var changed = false;

    Object.keys(sourceMap).forEach(function (key) {
      var bucket = sourceMap[key] || {};
      var parts = key.split('|');
      var keySubject = decodeURIComponent(parts[0] || '');
      var keyCourseName = decodeURIComponent(parts[1] || '');
      var subjectCode = String(bucket.subjectCode || keySubject || '').trim().toLowerCase();
      var courseName = pickCourseName(bucket.courseName, keyCourseName);
      var normalizedKey = buildCourseKey(subjectCode, courseName);
      var normalizedBucket = {
        subjectCode: subjectCode,
        courseName: courseName,
        sources: Array.isArray(bucket.sources) ? bucket.sources.slice() : [],
        draftText: String(bucket.draftText || ''),
        courseStructure: bucket.courseStructure || null,
        selectedChapterIds: uniqueChapterIds(bucket.selectedChapterIds || []),
        review: bucket.review || null,
      };

      if (normalizedKey !== key) {
        changed = true;
      }

      if (normalized[normalizedKey]) {
        normalized[normalizedKey] = mergeBucket(normalized[normalizedKey], normalizedBucket);
        changed = true;
      } else {
        normalized[normalizedKey] = normalizedBucket;
      }
    });

    if (Object.keys(normalized).length !== Object.keys(sourceMap).length) {
      changed = true;
    }

    return { map: normalized, changed: changed };
  }

  function renderCourseCard(subjectCode, courseName, bucket) {
    var cssKey = subjectCssKey(subjectCode);
    var subjectLabel = t(window.RRState.getSubjectLabelKey(subjectCode));
    var displayName = courseName || subjectLabel;
    var sourceCount = Array.isArray(bucket.sources) ? bucket.sources.length : 0;
    var review = bucket.review;
    var lastReviewText = review && review.createdAt
      ? (t('course_last_review') + window.RRApp.formatRelativeDate(review.createdAt))
      : t('course_never_reviewed');
    return [
      '<article class="course-card">',
      '  <div class="course-card__banner course-banner--' + cssKey + '">',
      '    <span class="course-badge course-badge--' + cssKey + '">' + escapeHtml(subjectLabel) + '</span>',
      '  </div>',
      '  <div class="course-card__body">',
      '    <div class="course-card__name">' + escapeHtml(displayName) + '</div>',
      '    <div class="course-card__meta">' + interpolate('course_source_count', { n: sourceCount }) + '</div>',
      '    <div class="course-card__meta">' + escapeHtml(lastReviewText) + '</div>',
      '  </div>',
      '  <div class="course-card__footer">',
      '    <button type="button" class="primary-btn course-enter-btn" data-subject="' + escapeHtml(subjectCode) + '" data-course="' + escapeHtml(courseName) + '">' + t('enter_course') + '</button>',
      '  </div>',
      '</article>',
    ].join('');
  }

  function renderGallery() {
    var buckets = readAllBuckets();
    var keys = Object.keys(buckets);
    var active = window.RRState.getSubjectContext();

    if (active && active.subjectCode) {
      var activeKey = buildCourseKey(active.subjectCode, active.courseName || '');
      if (!buckets[activeKey]) {
        buckets[activeKey] = {
          subjectCode: String(active.subjectCode || '').trim().toLowerCase(),
          courseName: String(active.courseName || '').trim(),
          sources: [],
          draftText: '',
          courseStructure: null,
          selectedChapterIds: [],
          review: null,
        };
        keys.push(activeKey);
      } else if (active.courseName) {
        buckets[activeKey] = Object.assign({}, buckets[activeKey], {
          courseName: pickCourseName(active.courseName, buckets[activeKey].courseName),
        });
      }
    }

    if (!keys.length) {
      courseGrid.innerHTML = '';
      courseGridEmpty.classList.remove('hidden');
      return;
    }

    courseGridEmpty.classList.add('hidden');
    courseGrid.innerHTML = keys.map(function (key) {
      var bucket = buckets[key] || {};
      var parts = key.split('|');
      var subjectCode = String(bucket.subjectCode || decodeURIComponent(parts[0] || '')).trim().toLowerCase();
      var courseName = pickCourseName(bucket.courseName, decodeURIComponent(parts[1] || ''));
      if (!subjectCode) {
        return '';
      }
      return renderCourseCard(subjectCode, courseName, bucket);
    }).filter(Boolean).join('');
  }

  async function syncCoursesFromServer() {
    if (!window.RRApp.isLoggedIn()) return;
    try {
      var r = await window.apiFetch('/course-structure/list', {
        headers: window.RRApp.authHeaders({ 'Accept': 'application/json' }),
      });
      var j = await r.json();
      if (!j.ok || !Array.isArray(j.courses)) return;
      var map = readAllBuckets();
      var changed = false;
      j.courses.forEach(function (c) {
        var subjectCode = String(c.subject_code || '').trim().toLowerCase();
        var courseName = String(c.course_name || '').trim();
        var key = buildCourseKey(subjectCode, courseName);
        if (!map[key]) {
          map[key] = {
            subjectCode: subjectCode,
            courseName: courseName,
            sources: [],
            draftText: '',
            courseStructure: null,
            selectedChapterIds: [],
            review: null,
          };
          changed = true;
          return;
        }

        var nextName = pickCourseName(map[key].courseName, courseName);
        if (map[key].courseName !== nextName || map[key].subjectCode !== subjectCode) {
          map[key] = Object.assign({}, map[key], {
            subjectCode: subjectCode,
            courseName: nextName,
          });
          changed = true;
        }
      });
      if (changed) {
        sessionStorage.setItem('rr_subject_sessions_v1', JSON.stringify(map));
      }
    } catch (_) {}
  }

  async function ensureCourseExists(subjectCode, courseName) {
    return window.RRApp.fetchJSON('/course-structure/ensure', {
      method: 'POST',
      headers: window.RRApp.authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        subject_code: subjectCode || undefined,
        course_name: courseName,
      }),
    });
  }

  function renderWorkspace() {
    var loggedIn = window.RRApp.isLoggedIn();
    guestSection.classList.toggle('hidden', loggedIn);
    memberSection.classList.toggle('hidden', !loggedIn);

    if (!loggedIn) {
      courseGrid.innerHTML = '';
      courseGridEmpty.classList.add('hidden');
      if (dialog.open) {
        dialog.close();
      }
      return;
    }

    renderGallery();
  }

  async function initWorkspace() {
    await syncCoursesFromServer();
    renderWorkspace();
  }

  function openDialog() {
    if (!window.RRApp.isLoggedIn()) {
      location.href = 'index.html?login=1';
      return;
    }

    var active = window.RRState.getSubjectContext();
    populateSubjectSelect(dialogSubject, active.subjectCode || 'math');
    dialogCourseName.value = '';
    dialog.showModal();
    dialogCourseName.focus();
  }

  function closeDialog() {
    if (dialog.open) {
      dialog.close();
    }
  }

  async function confirmNewCourse() {
    if (!window.RRApp.isLoggedIn()) {
      location.href = 'index.html?login=1';
      return;
    }

    var subjectCode = dialogSubject.value;
    var courseName = dialogCourseName.value.trim();
    if (!subjectCode) {
      return;
    }
    if (!courseName) {
      window.showToast('info', t('new_course_need_name'));
      dialogCourseName.focus();
      return;
    }

    var confirmLabel = t('new_course_confirm');
    dialogConfirm.disabled = true;
    dialogCancel.disabled = true;
    dialogConfirm.textContent = t('common_loading');
    try {
      await ensureCourseExists(subjectCode, courseName);
      await syncCoursesFromServer();
      window.RRState.setSubjectContext({ subjectCode: subjectCode, courseName: courseName });
      closeDialog();
      location.href = 'upload.html';
    } catch (error) {
      window.showToast('error', error.message || t('operation_failed'));
    } finally {
      dialogConfirm.disabled = false;
      dialogCancel.disabled = false;
      dialogConfirm.textContent = confirmLabel;
    }
  }

  courseGrid.addEventListener('click', function (event) {
    var btn = event.target.closest('.course-enter-btn');
    if (!btn) {
      return;
    }
    var subjectCode = btn.dataset.subject;
    var courseName = btn.dataset.course;
    window.RRState.setSubjectContext({ subjectCode: subjectCode, courseName: courseName });
    location.href = 'upload.html';
  });

  newCourseBtn.addEventListener('click', openDialog);
  dialogCancel.addEventListener('click', closeDialog);
  dialogConfirm.addEventListener('click', function () {
    confirmNewCourse();
  });

  dialogCourseName.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      confirmNewCourse();
    }
  });

  dialog.addEventListener('click', function (event) {
    if (event.target === dialog) {
      closeDialog();
    }
  });

  document.addEventListener('rr:langchange', renderWorkspace);

  initWorkspace();
});