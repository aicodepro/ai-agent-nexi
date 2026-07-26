(function () {
  var clockEl, cmdInput, sendBtn, micBtn;
  var debugVisible = false, settingsVisible = false;

  function $(id) { return document.getElementById(id); }

  function init() {
    clockEl = $('header-clock');
    cmdInput = $('command-input');
    sendBtn = $('send-button');
    micBtn = $('mic-button');

    // ONLINE is applied only by backend wake events; startup remains SLEEPING.
    if (window.nexiApplyState) window.nexiApplyState({ state: 'sleep', source: 'system', message: 'SLEEPING' });

    startClock();
    loadProviders();
    loadSuggestions();
    wireInput();
    wireButtons();
    wireFileDrop();
    wireDebugPanel();
    wireSettings();
    updateMetrics();
    setInterval(updateMetrics, 2000);
  }

  // === CLOCK ===
  function startClock() {
    function tick() {
      var d = new Date();
      if (clockEl) clockEl.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
    tick();
    setInterval(tick, 1000);
  }

  // === PROVIDERS ===
  function loadProviders() {
    eel.ui_get_env_status()(function (s) {
      if (!s) return;
      var short = $('provider-status-short');
      if (short) {
        var parts = [];
        if (s.groq) parts.push('GROQ');
        if (s.gemini) parts.push('GEMINI');
        if (s.openrouter) parts.push('OR');
        short.textContent = parts.length ? parts.join(' | ') : 'No API';
      }
    });
  }

  // === SUGGESTIONS ===
  function loadSuggestions() {
    var list = $('suggestion-list');
    if (!list) return;
    var suggestions = [
      { label: 'Open Chrome', text: 'open chrome' },
      { label: 'Open YouTube', text: 'open youtube' },
      { label: 'Search latest AI news', text: 'search latest AI news' },
      { label: 'What do you know?', text: 'what did you understand?' },
      { label: 'Create folder on desktop', text: 'create folder on desktop' },
      { label: 'System info', text: 'system info' },
      { label: 'Copy it', text: 'copy it' },
      { label: 'Stop', text: 'stop' }
    ];
    suggestions.forEach(function (s) {
      var chip = document.createElement('div');
      chip.className = 'suggestion-chip';
      chip.textContent = s.label;
      chip.addEventListener('click', function () { submit(s.text); });
      list.appendChild(chip);
    });
  }

  // === INPUT ===
  function wireInput() {
    cmdInput.addEventListener('input', function () {
      var v = cmdInput.value.trim();
      if (v) { sendBtn.classList.remove('hidden'); micBtn.classList.add('hidden'); }
      else { sendBtn.classList.add('hidden'); micBtn.classList.remove('hidden'); }
    });

    cmdInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { var v = cmdInput.value.trim(); if (v) submit(v); }
      if (e.key === 'Escape') cmdInput.value = '';
    });

    sendBtn.addEventListener('click', function () {
      var v = cmdInput.value.trim();
      if (v) submit(v);
    });

    micBtn.addEventListener('click', function () {
      cmdInput.value = '';
      sendBtn.classList.add('hidden');
      micBtn.classList.remove('hidden');
      if (window.addLogEntry) window.addLogEntry('voice', 'SYS: Mic button wake requested.');
      eel.wakeNexiFromUi('mic_button')();
    });
  }

  function submit(text) {
    if (!text || !text.trim()) return;
    text = text.trim();
    cmdInput.value = '';
    sendBtn.classList.add('hidden');
    micBtn.classList.remove('hidden');

    // Show user message immediately in activity log
    if (window.senderText) window.senderText(text);
    // Go through the ordered reducer, not setOrbState directly: the reducer is
    // what rejects stale/out-of-order events. Bypassing it lets a typed command
    // overwrite the state of a newer voice session.
    if (window.updateNexiState) window.updateNexiState({ state: 'thinking', source: 'typed' });

    eel.ui_submit_text(text)(function (result) {
      if (result && result.ok === false) {
        if (window.addLogEntry) window.addLogEntry('err', 'Command failed');
        if (window.updateNexiState) window.updateNexiState({ state: 'sleep', source: 'typed' });
      }
    });
  }

  // === BUTTONS ===
  function wireButtons() {
    $('power-button').addEventListener('click', function () { eel.toggleNexiSleepWake()(); });
    $('chat-button').addEventListener('click', function () {
      var body = $('activity-log');
      if (body) { body.scrollTop = body.scrollHeight; body.focus(); }
    });
    $('settings-button').addEventListener('click', openSettings);
  }

  // === FILE DROP ===
  function wireFileDrop() {
    var zone = $('file-drop-zone');
    var hint = $('file-drop-hint');
    var status = $('file-status');
    if (!zone) return;

    zone.addEventListener('click', function () {
      if (window.addLogEntry) window.addLogEntry('sys', 'File browse requested (click)');
    });

    zone.addEventListener('dragover', function (e) {
      e.preventDefault();
      zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', function () {
      zone.classList.remove('drag-over');
    });
    zone.addEventListener('drop', function (e) {
      e.preventDefault();
      zone.classList.remove('drag-over');
      var files = e.dataTransfer.files;
      if (!files || files.length === 0) return;
      var paths = [];
      for (var i = 0; i < Math.min(files.length, 5); i++) paths.push(files[i].path || files[i].name);
      eel.ui_submit_file_drop(paths)(function (r) {
        if (r && r.ok && r.files && r.files.length) {
          var f = r.files[0];
          if (status) status.textContent = '\u{1F4CE} ' + f.name;
          if (window.addLogEntry) window.addLogEntry('file', 'Dropped: ' + f.name);
          if (window.receiverText) {
            var names = r.files.map(function (x) { return x.name; }).join(', ');
            window.receiverText('File' + (r.files.length > 1 ? 's' : '') + ' uploaded: ' + names + '. What should I do?');
          }
        }
      });
    });
  }

  // === DEBUG LOG ===
  function wireDebugPanel() {
    $('log-toggle-btn').addEventListener('click', function () {
      debugVisible = !debugVisible;
      $('debug-panel').classList.toggle('hidden', !debugVisible);
    });
    $('debug-close').addEventListener('click', function () {
      debugVisible = false;
      $('debug-panel').classList.add('hidden');
    });
    var filter = $('log-level-filter');
    if (filter) filter.addEventListener('change', function () {
      if (window.__renderDebug) window.__renderDebug();
    });
  }

  // === SETTINGS ===
  function wireSettings() {
    $('settings-close').addEventListener('click', closeSettings);
    var backdrop = document.querySelector('#settings-overlay .overlay-backdrop');
    if (backdrop) backdrop.addEventListener('click', closeSettings);
  }

  function openSettings() {
    settingsVisible = true;
    $('settings-overlay').classList.remove('hidden');
    eel.ui_get_env_status()(function (s) {
      var el = $('provider-list');
      if (!el) return;
      var html = '';
      Object.keys(s || {}).forEach(function (k) {
        html += '<div class="provider-row"><span class="provider-dot ' + (s[k] ? 'on' : 'off') + '"></span>' +
                k.toUpperCase() + ': ' + (s[k] ? 'CONFIGURED' : 'NOT CONFIGURED') + '</div>';
      });
      el.innerHTML = html;
    });
    eel.ui_get_runtime_status()(function (s) {
      var el = $('runtime-list');
      if (!el) return;
      el.innerHTML = '<div class="provider-row">Wake: ' + (s && s.wake_enabled ? 'ENABLED' : 'DISABLED') + '</div>' +
                     '<div class="provider-row">Workflow: ' + (s && s.active_workflow ? 'ACTIVE' : 'NONE') + '</div>';
    });
  }

  function closeSettings() {
    settingsVisible = false;
    $('settings-overlay').classList.add('hidden');
  }

  // === METRICS ===
  function updateMetrics() {
    // Real host metrics from the backend. Never fabricate these: an assistant
    // that invents telemetry can't be trusted about anything else it reports.
    if (typeof eel === 'undefined' || !eel.ui_get_metrics) {
      ['cpu', 'mem', 'net', 'gpu', 'tmp'].forEach(function (k) { setMetric(k, '--'); });
      return;
    }
    eel.ui_get_metrics()(function (m) {
      m = m || {};
      ['cpu', 'mem', 'net', 'gpu', 'tmp'].forEach(function (k) {
        setMetric(k, m[k] || '--');
      });
    });
  }

  function setMetric(id, val) {
    var bar = $('metric-' + id);
    var valEl = $('metric-' + id + '-val');
    if (valEl) valEl.textContent = val;
    if (bar) {
      var pct = parseFloat(val);
      bar.style.width = Math.min(100, Math.max(0, isNaN(pct) ? 0 : pct)) + '%';
      if (pct > 85) bar.style.background = '#ff3355';
      else if (pct > 65) bar.style.background = '#ff6b00';
    }
  }

  // === KEYBOARD SHORTCUTS ===
  document.addEventListener('keydown', function (e) {
    if ((e.key === 'j' || e.key === 'J') && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (window.addLogEntry) window.addLogEntry('sys', 'SYS: Keyboard wake shortcut disabled; use hotword or double clap.');
    }
    if (e.altKey && (e.key === 'm' || e.key === 'M')) {
      e.preventDefault();
      if (window.addLogEntry) window.addLogEntry('sys', 'Mute toggled');
    }
    if (e.key === 'F11') {
      e.preventDefault();
      if (window.addLogEntry) window.addLogEntry('sys', 'Fullscreen toggled');
    }
  });

  init();
  console.log('[MarkUI] main.js loaded');
})();
