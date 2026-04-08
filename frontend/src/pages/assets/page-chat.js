document.addEventListener('DOMContentLoaded', async function () {
  await window.RRApp.initPage('chat');

  if (!window.RRApp.isLoggedIn()) {
    location.href = 'index.html?login=1';
    return;
  }

  const chatLog = document.getElementById('chat-log');
  const chatEmpty = document.getElementById('chat-empty');
  const chatStatus = document.getElementById('chat-status');
  const reviewSummary = document.getElementById('chat-review-summary');
  const questionInput = document.getElementById('chat-question');
  const sendButton = document.getElementById('btn-send');
  const clearButton = document.getElementById('btn-clear-chat');

  let currentReview = window.RRState.getCurrentReview();
  let messages = [];

  function getChatKey() {
    return currentReview && currentReview.id ? 'rr_chat_v2_' + currentReview.id : '';
  }

  function loadMessages() {
    const key = getChatKey();
    if (!key) {
      messages = [];
      return;
    }
    try {
      messages = JSON.parse(sessionStorage.getItem(key) || '[]');
    } catch (_) {
      messages = [];
    }
  }

  function saveMessages() {
    const key = getChatKey();
    if (!key) {
      return;
    }
    try {
      sessionStorage.setItem(key, JSON.stringify(messages));
    } catch (_) {}
  }

  function scrollToBottom() {
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function buildRefs(refs) {
    if (!refs || !refs.length) {
      return null;
    }

    const details = document.createElement('details');
    details.className = 'chat-entry__refs';
    const summary = document.createElement('summary');
    summary.textContent = window.RRApp.t('chat_refs');
    details.appendChild(summary);

    const list = document.createElement('ol');
    refs.forEach(function (ref) {
      const item = document.createElement('li');
      item.textContent = ref.text || '';
      list.appendChild(item);
    });
    details.appendChild(list);
    return details;
  }

  function buildMessageNode(message) {
    const entry = document.createElement('article');
    entry.className = 'chat-entry chat-entry--' + message.role;

    const bubble = document.createElement('div');
    bubble.className = 'chat-entry__bubble';

    if (message.role === 'assistant') {
      const body = document.createElement('div');
      body.className = 'prose prose-slate max-w-none';
      window.RRApp.renderMarkdown(body, message.content);
      bubble.appendChild(body);

      const refs = buildRefs(message.refs || []);
      if (refs) {
        bubble.appendChild(refs);
      }
    } else {
      bubble.textContent = message.content;
    }

    entry.appendChild(bubble);
    return entry;
  }

  function renderReviewSummary() {
    currentReview = window.RRState.getCurrentReview();
    if (!currentReview || !currentReview.text) {
      reviewSummary.innerHTML = '<div class="empty-state">' + window.RRApp.escapeHtml(window.RRApp.t('chat_no_review')) + '</div>';
      return;
    }

    const subjectParts = [];
    if (currentReview.subjectCode) {
      subjectParts.push(window.RRApp.t(window.RRState.getSubjectLabelKey(currentReview.subjectCode)));
    }
    if (currentReview.courseName) {
      subjectParts.push(currentReview.courseName);
    }

    const examParts = [];
    if (currentReview.examName) {
      examParts.push(currentReview.examName);
    }
    if (currentReview.examType) {
      examParts.push(window.RRApp.t(window.RRState.getExamLabelKey(currentReview.examType)));
    }

    reviewSummary.innerHTML = [
      '<div class="review-summary">',
      '  <div class="review-summary__meta">',
      '    <span class="source-badge">' + window.RRApp.escapeHtml(currentReview.format || 'review_sheet_pro') + '</span>',
      '    <span>' + window.RRApp.escapeHtml(window.RRApp.formatRelativeDate(currentReview.createdAt)) + '</span>',
      subjectParts.length ? '    <span>' + window.RRApp.escapeHtml(subjectParts.join(' · ')) + '</span>' : '',
      examParts.length ? '    <span>' + window.RRApp.escapeHtml(examParts.join(' · ')) + '</span>' : '',
      '  </div>',
      '  <div class="review-summary__preview">' + window.RRApp.escapeHtml(String(currentReview.text || '').slice(0, 320)) + '</div>',
      '</div>',
    ].join('');
  }

  function renderMessages() {
    chatLog.innerHTML = '';
    const canChat = currentReview && currentReview.id;

    if (!messages.length) {
      chatEmpty.classList.remove('hidden');
      chatLog.classList.add('hidden');
      chatEmpty.textContent = canChat ? window.RRApp.t('chat_empty_state') : window.RRApp.t('chat_no_review');
    } else {
      chatEmpty.classList.add('hidden');
      chatLog.classList.remove('hidden');
    }

    messages.forEach(function (message) {
      chatLog.appendChild(buildMessageNode(message));
    });
    sendButton.disabled = !canChat;
    scrollToBottom();
  }

  function addMessage(message) {
    messages.push(message);
    saveMessages();
    renderMessages();
  }

  async function askFallback(question) {
    const data = await window.RRApp.fetchJSON('/chat', {
      method: 'POST',
      headers: window.RRApp.authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        question: question,
        review_sheet_id: currentReview.id,
      }),
    });
    return { text: data.text || '', refs: [] };
  }

  async function sendMessage() {
    currentReview = window.RRState.getCurrentReview();
    const question = questionInput.value.trim();
    if (!currentReview || !currentReview.id) {
      window.showToast('info', window.RRApp.t('chat_no_review'));
      return;
    }
    if (!question) {
      questionInput.focus();
      return;
    }

    addMessage({ role: 'user', content: question });
    questionInput.value = '';
    chatStatus.textContent = window.RRApp.t('chat_thinking');
    sendButton.disabled = true;

    const liveEntry = document.createElement('article');
    liveEntry.className = 'chat-entry chat-entry--assistant';
    const liveBubble = document.createElement('div');
    liveBubble.className = 'chat-entry__bubble';
    liveBubble.textContent = '';
    liveEntry.appendChild(liveBubble);
    chatLog.appendChild(liveEntry);
    scrollToBottom();

    let answer = '';
    let refs = [];
    let failure = '';

    try {
      const stream = window.RRApp.streamSSE('/chat/stream', {
        question: question,
        review_sheet_id: currentReview.id,
      }, {
        refs: function (raw) {
          try {
            refs = JSON.parse(raw);
          } catch (_) {
            refs = [];
          }
        },
        chunk: function (raw) {
          try {
            answer += JSON.parse(raw);
          } catch (_) {
            answer += raw;
          }
          liveBubble.textContent = answer;
          scrollToBottom();
        },
        error: function (raw) {
          failure = raw || window.RRApp.t('request_failed');
        },
      });
      await stream.done;

      if (failure) {
        throw new Error(failure);
      }
      if (!answer) {
        const fallback = await askFallback(question);
        answer = fallback.text;
        refs = fallback.refs;
      }
    } catch (streamError) {
      try {
        const fallback = await askFallback(question);
        answer = fallback.text;
        refs = fallback.refs;
      } catch (fallbackError) {
        liveEntry.remove();
        chatStatus.textContent = '';
        sendButton.disabled = false;
        window.showToast('error', fallbackError.message || streamError.message || window.RRApp.t('request_failed'));
        renderMessages();
        return;
      }
    }

    liveEntry.remove();
    addMessage({ role: 'assistant', content: answer, refs: refs });
    chatStatus.textContent = '';
    sendButton.disabled = false;
  }

  function clearMessages() {
    if (!messages.length) {
      return;
    }
    if (!window.confirm(window.RRApp.t('chat_confirm_clear'))) {
      return;
    }
    messages = [];
    saveMessages();
    renderMessages();
  }

  renderReviewSummary();
  loadMessages();
  renderMessages();

  sendButton.addEventListener('click', sendMessage);
  clearButton.addEventListener('click', clearMessages);
  questionInput.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });
  document.addEventListener('rr:langchange', function () {
    renderReviewSummary();
    renderMessages();
  });
});