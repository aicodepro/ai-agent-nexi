(function () {
  var MAX_LOG_ENTRIES = 300;
  var logEntries = [];
  var lastStateLog = { key: '', at: 0 };

  var ALLOWED_STATES = {
    sleep: 'sleep', idle: 'sleep', sleeping: 'sleep', tts_done: 'sleep',
    online: 'online', wake: 'online', wake_detected: 'online',
    hotword_detected: 'online', clap_detected: 'online', double_clap_detected: 'online',
    listening_started: 'listening', listening: 'listening', waiting_for_speech: 'listening',
    hearing_speech: 'listening', speech_started: 'recognising', speech_ended: 'recognising',
    recognising: 'recognising', recognizing: 'recognising', asr_started: 'recognising',
    transcribing: 'recognising', asr_result: 'thinking', thinking: 'thinking',
    running_tool: 'thinking', searching: 'thinking', checking_files: 'thinking',
    react_thinking: 'thinking', react_tool_start: 'thinking', react_tool_end: 'thinking',
    command_started: 'thinking', saying: 'saying', speaking: 'saying', tts_started: 'saying',
    interrupted: 'error', error: 'error'
  };

  var TONE_CLASSES = ['tone-calm', 'tone-urgent', 'tone-focused', 'tone-friendly', 'tone-technical', 'tone-uncertain'];

  var STATE_LABELS = {
    sleep: 'SLEEPING',
    online: 'ONLINE',
    listening: 'LISTENING',
    recognising: 'RECOGNISING',
    thinking: 'THINKING',
    saying: 'SAYING',
    error: 'ERROR'
  };

  var ORB_STATES = {
    sleep: 'sleeping',
    online: 'wake_detected',
    listening: 'listening',
    recognising: 'recognising',
    thinking: 'thinking',
    saying: 'speaking',
    error: 'error'
  };

  function ts() {
    var d = new Date();
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function esc(text) {
    return String(text || '').replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function parsePayload(payload) {
    if (typeof payload === 'string') {
      try { payload = JSON.parse(payload); } catch (e) { payload = {}; }
    }
    return payload || {};
  }

  function normalizeState(state) {
    var key = String(state || 'sleep').trim().toLowerCase();
    return ALLOWED_STATES[key] || 'sleep';
  }

  function addLog(level, msg) {
    var now = Date.now();
    var logKey = String(level || '') + '|' + String(msg || '');
    if (lastStateLog.key === logKey && now - lastStateLog.at < 250) return;
    lastStateLog = { key: logKey, at: now };
    logEntries.push({ level: level, message: msg, time: ts() });
    if (logEntries.length > MAX_LOG_ENTRIES) logEntries = logEntries.slice(-MAX_LOG_ENTRIES);
    var body = document.getElementById('nexi-log') || document.getElementById('activity-log');
    if (body) {
      var cls = level === 'err' ? 'err' : level === 'you' ? 'you' :
                level === 'ai' ? 'ai' : level === 'file' ? 'file' :
                level === 'tool' ? 'tool' : level === 'wake' ? 'wake' : 'sys';
      body.innerHTML += '<div class="log-msg ' + cls + '">' + esc(msg) + '</div>';
      body.scrollTop = body.scrollHeight;
      if (body.children.length > 200) {
        while (body.children.length > 100) body.removeChild(body.firstChild);
      }
    }
    var db = document.getElementById('debug-log-body');
    if (db) {
      var lvlCls = { info: 'info', warn: 'warn', error: 'error', route: 'route', tool: 'tool', voice: 'voice' }[level] || 'info';
      db.innerHTML += '<div class="log-entry ' + lvlCls + ' hidden"><span class="ts">' + ts() + '</span>' + esc(msg) + '</div>';
      if (db.children.length > 300) db.removeChild(db.firstChild);
      renderDebugLog();
    }
  }

  function renderDebugLog() {
    var db = document.getElementById('debug-log-body');
    if (!db) return;
    var filter = (document.getElementById('log-level-filter') || {}).value || 'all';
    Array.prototype.forEach.call(db.children, function (el) {
      el.classList.toggle('hidden', filter !== 'all' && !el.classList.contains(filter));
    });
    db.scrollTop = db.scrollHeight;
  }

  function eachStateTarget(fn) {
    ['nexi-state', 'nexi-center-state', 'nexi-bottom-state', 'nexi-status-badge', 'nexi-mode', 'nexi-orb-state'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) fn(el, id);
    });
  }

  function setStateClasses(el, state) {
    ['sleep', 'online', 'listening', 'recognising', 'thinking', 'saying', 'error'].forEach(function (name) {
      el.classList.remove('nexi-state-' + name);
    });
    el.classList.add('nexi-state-' + state);
    el.setAttribute('data-nexi-state', state);
    el.setAttribute('data-state', state);
  }

  function updateMainHudState(state, label) {
    eachStateTarget(function (el) {
      el.textContent = label;
      setStateClasses(el, state);
    });
  }

  function updateBottomState(state, label) {
    var el = document.getElementById('nexi-bottom-state');
    if (!el) return;
    el.textContent = label;
    setStateClasses(el, state);
  }

  function updateStatusBadge(state, label) {
    var el = document.getElementById('nexi-status-badge');
    if (!el) return;
    el.textContent = label;
    setStateClasses(el, state);
  }

  function updateSourceText(state, source) {
    var hint = document.getElementById('nexi-source') || document.getElementById('wake-hint');
    if (!hint) return;
    if (state === 'sleep') hint.textContent = 'Say Hey Nexi or double clap to wake';
    else if (state === 'online') hint.textContent = source ? 'Source: ' + source : 'Online';
    else if (state === 'listening') hint.textContent = 'Listening... speak now';
    else if (state === 'recognising') hint.textContent = 'Recognising...';
    else if (state === 'thinking') hint.textContent = 'Thinking...';
    else if (state === 'saying') hint.textContent = 'Saying...';
    else if (state === 'error') hint.textContent = 'Error';
  }

  function defaultLogFor(state, source, text) {
    if (state === 'online') {
      var src = String(source || '').toLowerCase();
      if (src === 'hotword') return ['wake', 'WAKE: Hotword detected'];
      if (src === 'clap' || src === 'double_clap' || src === 'double-clap' || src === 'double clap') return ['wake', 'WAKE: Double clap detected'];
      return ['wake', 'WAKE: Wake detected'];
    }
    if (state === 'listening') return ['sys', 'SYS: Listening...'];
    if (state === 'recognising') return ['sys', 'SYS: Recognising speech...'];
    if (state === 'thinking') return ['sys', 'SYS: Thinking...'];
    if (state === 'saying') return ['sys', 'SYS: Saying...'];
    if (state === 'error') return ['err', 'SYS: Error' + (text ? ': ' + String(text).slice(0, 80) : '')];
    return ['sys', 'SYS: Sleep mode'];
  }

  function updateActivityLog(state, label, source, payload) {
    if (payload.log) {
      addLog(payload.log_level || 'sys', payload.log);
      return;
    }
    if (payload.status === 'asr_result' && payload.text) {
      window.senderText(payload.text);
      return;
    }
    var entry = defaultLogFor(state, source, payload.text || '');
    addLog(entry[0], entry[1]);
  }

  function updateBodyClass(state) {
    var body = document.body;
    if (!body) return;
    ['sleep', 'online', 'listening', 'recognising', 'thinking', 'saying', 'error'].forEach(function (name) {
      body.classList.remove('nexi-ui-state-' + name);
      body.classList.remove('nexi-app-state-' + name);
    });
    body.classList.add('nexi-ui-state-' + state);
    body.classList.add('nexi-app-state-' + state);
    body.setAttribute('data-nexi-state', state);
    body.setAttribute('data-state', state);
  }

  function updateOrbMode(state) {
    if (window.setOrbState) window.setOrbState(ORB_STATES[state] || 'sleeping');
  }

  function applyToneClass(tone) {
    var raw = String(tone || 'calm').trim().toLowerCase().replace(/_/g, '-');
    var cls = raw === 'low-confidence' ? 'tone-uncertain' : 'tone-' + raw;
    if (TONE_CLASSES.indexOf(cls) === -1) cls = 'tone-calm';
    var body = document.body;
    if (!body) return;
    TONE_CLASSES.forEach(function (name) { body.classList.remove(name); });
    body.classList.add(cls);
    body.setAttribute('data-nexi-tone', raw);
  }

  function renderPresence(payload) {
    payload = parsePayload(payload);
    var attention = document.getElementById('PresenceAttention');
    var goal = document.getElementById('PresenceGoal');
    var confidence = document.getElementById('PresenceConfidence');
    if (attention) attention.textContent = String(payload.attention || 'none').toUpperCase();
    if (goal) goal.textContent = String(payload.current_goal || 'waiting for wake word').toUpperCase().slice(0, 120);
    if (confidence) confidence.textContent = Math.round(Number(payload.confidence || 0) * 100) + '%';
    if (payload.tone) applyToneClass(payload.tone);
  }

  function renderDashboardValue(value) {
    if (value === null || value === undefined) return '--';
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return esc(value);
    if (Array.isArray(value)) {
      return value.slice(0, 4).map(function (item) { return '<div class="dashboard-line">' + renderDashboardValue(item) + '</div>'; }).join('');
    }
    var rows = [];
    Object.keys(value).slice(0, 6).forEach(function (key) {
      rows.push('<div class="dashboard-line"><span>' + esc(key) + '</span><b>' + renderDashboardValue(value[key]) + '</b></div>');
    });
    return rows.join('');
  }

  function renderDashboard(payload) {
    payload = parsePayload(payload);
    var panels = payload.panels || [];
    var summary = document.getElementById('dashboard-summary');
    var target = document.getElementById('dashboard-panels');
    if (!target) return;
    if (summary) summary.textContent = panels.length ? panels.length + ' panels updated ' + ts() : 'Dashboard unavailable';
    target.innerHTML = panels.map(function (panel) {
      return '<div class="dashboard-panel" data-panel-id="' + esc(panel.id) + '">' +
        '<div class="dashboard-panel-title">' + esc(panel.title || panel.id) + '</div>' +
        '<div class="dashboard-panel-body">' + renderDashboardValue(panel.data || {}) + '</div>' +
        '</div>';
    }).join('');
  }

  function refreshDashboard() {
    try {
      if (typeof eel !== 'undefined' && eel.getDashboardState) {
        eel.getDashboardState()(function (payload) { renderDashboard(payload); });
      }
    } catch (e) {}
  }

  window.nexiApplyState = function (payload) {
    payload = parsePayload(payload);
    var state = normalizeState(payload.state || payload.status || 'sleep');
    var label = payload.label || payload.message || STATE_LABELS[state] || state.toUpperCase();
    var source = payload.source || 'system';
    var sessionId = payload.session_id || '';

    updateMainHudState(state, label);
    updateBottomState(state, label);
    updateStatusBadge(state, label);
    updateSourceText(state, source);
    updateActivityLog(state, label, source, payload);
    updateBodyClass(state);
    updateOrbMode(state);
    applyToneClass(payload.tone || (payload.presence && payload.presence.tone));
    if (payload.presence) renderPresence(payload.presence);

    window.__nexiLastState = { state: state, label: label, source: source, sessionId: sessionId, ts: Date.now() };

    try { eel.ui_state_ack(sessionId, state, label)(); } catch (e) {}
  };

  window.updateNexiState = function (payload) {
    window.nexiApplyState(payload);
  };

  window.updatePresence = function (payload) {
    renderPresence(payload);
  };

  window.senderText = function (msg) {
    if (!msg) return;
    var el = document.getElementById('nexi-transcript');
    if (el) el.textContent = 'You: ' + String(msg).slice(0, 200);
    addLog('you', 'You: ' + String(msg).slice(0, 200));
  };

  window.receiverText = function (msg) {
    if (!msg) return;
    var el = document.getElementById('nexi-response');
    if (el) el.textContent = 'NEXI: ' + String(msg).slice(0, 300);
    addLog('ai', 'NEXI: ' + String(msg).slice(0, 300));
  };

  window.updateTranscript = function (payload) {
    payload = parsePayload(payload);
    var userText = String(payload.user_text || '');
    var nexiText = String(payload.nexi_text || '');
    var meta = payload.metadata || {};
    if (userText) window.senderText(userText);
    if (nexiText) window.receiverText(nexiText);
    if (meta.route || meta.intent || meta.provider) {
      var metaParts = [];
      if (meta.route) metaParts.push('Route: ' + esc(meta.route));
      if (meta.provider) metaParts.push('Provider: ' + esc(meta.provider));
      if (meta.intent) metaParts.push('Intent: ' + esc(meta.intent));
      if (meta.latency_ms) metaParts.push('Latency: ' + (meta.latency_ms / 1000).toFixed(1) + 's');
      var userEl = document.getElementById('UserText');
      var nexiEl = document.getElementById('NexiText');
      var metaEl = document.getElementById('ResponseMeta');
      if (userEl && userText) userEl.textContent = userText.slice(0, 300);
      if (nexiEl && nexiText) nexiEl.textContent = nexiText.slice(0, 400);
      if (metaEl) metaEl.innerHTML = metaParts.join(' <span class="meta-sep">|</span> ');
      var el = document.getElementById('nexi-response');
      if (el) {
        el.setAttribute('title', metaParts.join('  '));
      }
    }
  };

  window.updateState = function (state) {
    window.nexiApplyState(typeof state === 'string' ? { state: state } : state);
  };

  window.appendLog = function (level, message) {
    addLog(typeof level === 'string' ? level : 'sys', String(message || ''));
  };

  window.appendResponse = function (text) {
    window.receiverText(text);
  };

  window.updateDashboard = renderDashboard;
  window.diagnosticsResult = function (payload) { renderDashboard(payload); };
  window.refreshDashboard = refreshDashboard;
  window.toggleDiagnostics = function () {
    var panel = document.getElementById('diagnostics-dashboard');
    if (panel) panel.classList.toggle('collapsed');
  };

  window.updateSpeechCapsule = function () {};
  window.hideSpeechCapsule = function () {};
  window.setContextIndicator = function () {};
  window.DisplayMessage = function (m) { window.nexiApplyState({ state: 'saying', source: 'tts' }); };
  window.ShowHood = function () { window.nexiApplyState({ state: 'sleep', source: 'ready' }); };
  window.setStatus = function (t) {
    var text = String(t || '').trim();
    if (text) {
      var el = document.getElementById('nexi-status-badge');
      if (el) el.textContent = text;
    }
  };
  window.displayControlResult = function (m) { addLog('tool', 'Control: ' + m); };
  window.showEmergencyStop = function (r) { addLog('err', 'EMERGENCY: ' + r); };
  window.showOutputWorkspace = function () {};
  window.closeOutputWorkspace = function () {};
  window.minimizeOutputWorkspace = function () {};
  window.pinOutputWorkspace = function () {};

  window.addLogEntry = addLog;
  window.getLogEntries = function () { return logEntries; };
  window.__renderDebug = renderDebugLog;

  if (typeof eel !== 'undefined') {
    eel.expose(window.nexiApplyState, 'nexiApplyState');
    eel.expose(window.updateNexiState, 'updateNexiState');
    eel.expose(window.updatePresence, 'updatePresence');
    eel.expose(window.updateState, 'updateState');
    eel.expose(window.senderText, 'senderText');
    eel.expose(window.receiverText, 'receiverText');
    eel.expose(window.updateTranscript, 'updateTranscript');
    eel.expose(window.appendLog, 'appendLog');
    eel.expose(window.appendResponse, 'appendResponse');
    eel.expose(window.updateDashboard, 'updateDashboard');
    eel.expose(window.diagnosticsResult, 'diagnosticsResult');
    eel.expose(window.DisplayMessage, 'DisplayMessage');
    eel.expose(window.ShowHood, 'ShowHood');
    eel.expose(window.setStatus, 'setStatus');
    eel.expose(window.updateSpeechCapsule, 'updateSpeechCapsule');
    eel.expose(window.hideSpeechCapsule, 'hideSpeechCapsule');
    eel.expose(window.setContextIndicator, 'setContextIndicator');
    eel.expose(window.displayControlResult, 'displayControlResult');
    eel.expose(window.showEmergencyStop, 'showEmergencyStop');
    eel.expose(window.showOutputWorkspace, 'showOutputWorkspace');
    eel.expose(window.closeOutputWorkspace, 'closeOutputWorkspace');
    eel.expose(window.minimizeOutputWorkspace, 'minimizeOutputWorkspace');
    eel.expose(window.pinOutputWorkspace, 'pinOutputWorkspace');
  }

  var refreshBtn = document.getElementById('dashboard-refresh');
  if (refreshBtn) refreshBtn.addEventListener('click', refreshDashboard);
  var toggleBtn = document.getElementById('dashboard-toggle');
  if (toggleBtn) toggleBtn.addEventListener('click', window.toggleDiagnostics);
  window.setTimeout(refreshDashboard, 600);
  window.setInterval(refreshDashboard, 2000);

  console.log('[MarkUI] controller.js loaded');
})();
