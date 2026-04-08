document.addEventListener('DOMContentLoaded', async function () {
  await window.RRApp.initPage('workspace');

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
    if (current) select.value = current;
  }

  function readAllBuckets() {
    try {
      var raw = sessionStorage.getItem('rr_subject_sessions_v1');
      return raw ? JSON.parse(raw) : {};
    } catch (_) {
      return {};
    }
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
    var bucketKey = encodeURIComponent(subjectCode) + '|' + encodeURIComponent(courseName);
    return [
      '<article class="course-card" data-bucket-key="' + escapeHtml(bucketKey) + '">',
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

    // Also include the active context if it's not in buckets yet
    var active = window.RRState.getSubjectContext();
    if (active && active.subjectCode) {
      var activeKey = encodeURIComponent(active.subjectCode) + '|' + encodeURIComponent(active.courseName || '');
      if (!buckets[activeKey]) {
        buckets[activeKey] = { sources: [], review: null };
        keys.push(activeKey);
      }
    }

    if (!keys.length) {
      courseGrid.innerHTML = '';
      courseGridEmpty.classList.remove('hidden');
      return;
    }

    courseGridEmpty.classList.add('hidden');
    courseGrid.innerHTML = keys.map(function (key) {
      var parts = key.split('|');
      var subjectCode = decodeURIComponent(parts[0] || '');
      var courseName = decodeURIComponent(parts[1] || '');
      if (!subjectCode) return '';
      return renderCourseCard(subjectCode, courseName, buckets[key] || {});
    }).filter(Boolean).join('');
  }

  function openDialog() {
    var active = window.RRState.getSubjectContext();
    populateSubjectSelect(dialogSubject, active.subjectCode || 'math');
    dialogCourseName.value = '';
    dialog.showModal();
    dialogCourseName.focus();
  }

  function closeDialog() {
    dialog.close();
  }

  function confirmNewCourse() {
    var subjectCode = dialogSubject.value;
    var courseName = dialogCourseName.value.trim();
    if (!subjectCode) return;
    window.RRState.setSubjectContext({ subjectCode: subjectCode, courseName: courseName });
    closeDialog();
    location.href = 'upload.html';
  }

  // Event: enter course card
  courseGrid.addEventListener('click', function (e) {
    var btn = e.target.closest('.course-enter-btn');
    if (!btn) return;
    var subjectCode = btn.dataset.subject;
    var courseName = btn.dataset.course;
    window.RRState.setSubjectContext({ subjectCode: subjectCode, courseName: courseName });
    location.href = 'upload.html';
  });

  // Event: new course
  newCourseBtn.addEventListener('click', openDialog);
  dialogCancel.addEventListener('click', closeDialog);
  dialogConfirm.addEventListener('click', confirmNewCourse);

  // Allow Enter in course name field to confirm
  dialogCourseName.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') confirmNewCourse();
  });

  // Close dialog on backdrop click
  dialog.addEventListener('click', function (e) {
    if (e.target === dialog) closeDialog();
  });

  // Re-render on language change
  window.addEventListener('rr:langchange', renderGallery);

  // Initial render
  renderGallery();
});