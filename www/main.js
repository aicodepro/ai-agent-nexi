(function () {
  var clockEl, cmdInput, sendBtn, micBtn;

  function $(id) { return document.getElementById(id); }

  function init() {
    clockEl = $('header-clock');
    cmdInput = $('command-input');
    sendBtn = $('send-button');
    micBtn = $('mic-button');

    if (window.addLogEntry) window.addLogEntry('sys', 'SYS: Sleep mode');
    if (window.setOrbState) window.setOrbState('idle');

    startClock();
    loadProviders();
    loadSuggestions();
    loadToolCategories();
    wireInput();
    wireButtons();
    wireFileDrop();
    wireDebugPanel();
    wireSettings();
    wireWorkspace();
    updateMetrics();
    setInterval(updateMetrics, 2000);
  }

  function startClock() {
    function tick() {
      if (clockEl) clockEl.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
    tick();
    setInterval(tick, 1000);
  }

  function loadProviders() {
    eel.ui_get_env_status()(function (s) {
      if (!s) return;
      var el = $('provider-status-short');
      if (el) {
        var parts = [];
        if (s.groq) parts.push('GROQ');
        if (s.gemini) parts.push('GEMINI');
        el.textContent = parts.length ? parts.join(' | ') : 'No API';
      }
    });
  }

  function loadSuggestions() {
    var list = $('suggestion-list');
    if (!list) return;
    eel.ui_get_suggestions()(function (items) {
      if (!items || !items.length) return;
      list.innerHTML = '';
      items.forEach(function (s) {
        var chip = document.createElement('div');
        chip.className = 'suggestion-chip';
        chip.textContent = s.label;
        chip.addEventListener('click', function () { submit(s.text); });
        list.appendChild(chip);
      });
    });
  }

  function loadToolCategories() {
    var el = $('tool-categories');
    if (!el) return;
    eel.ui_get_tool_categories()(function (cats) {
      if (!cats || !cats.length) return;
      el.innerHTML = '';
      cats.forEach(function (c) {
        var tag = document.createElement('span');
        tag.className = 'tool-cat';
        tag.textContent = c.label;
        tag.title = (c.tools || []).join(', ');
        el.appendChild(tag);
      });
    });
  }

  function wireInput() {
    cmdInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { var v = cmdInput.value.trim(); if (v) submit(v); }
      if (e.key === 'Escape') cmdInput.value = '';
    });
    sendBtn.addEventListener('click', function () { var v = cmdInput.value.trim(); if (v) submit(v); });
    micBtn.addEventListener('click', function () {
      if (window.addLogEntry) window.addLogEntry('sys', 'SYS: Mic wake requested');
      eel.wakeNexiFromUi('mic_button')();
    });
  }

  function submit(text) {
    if (!text || !text.trim()) return;
    text = text.trim();
    cmdInput.value = '';
    if (window.senderText) window.senderText(text);
    if (window.setOrbState) window.setOrbState('thinking');
    eel.ui_submit_text(text)(function (r) {
      if (r && r.status === 'error') {
        if (window.addLogEntry) window.addLogEntry('err', 'Command failed');
        if (window.setOrbState) window.setOrbState('idle');
      }
    });
  }

  var estopActive = false;
  function wireButtons() {
    $('power-button').addEventListener('click', function () {
      eel.submitUserCommand('sleep')();
    });
    $('settings-button').addEventListener('click', openSettings);
    var estop = $('estop-button');
    if (estop) estop.addEventListener('click', function () {
      estopActive = !estopActive;
      if (estopActive) {
        eel.emergencyStop()();
        estop.classList.add('estop-on');
        if (window.addLogEntry) window.addLogEntry('err', 'EMERGENCY STOP engaged');
      } else {
        eel.clearEmergencyStop()();
        estop.classList.remove('estop-on');
        if (window.addLogEntry) window.addLogEntry('sys', 'Emergency stop cleared');
      }
    });
  }

  function wireFileDrop() {
    var zone = $('file-drop-zone');
    var status = $('file-status');
    if (!zone) return;
    zone.addEventListener('dragover', function (e) { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', function () { zone.classList.remove('drag-over'); });
    zone.addEventListener('drop', function (e) {
      e.preventDefault();
      zone.classList.remove('drag-over');
      var files = e.dataTransfer.files;
      if (!files || !files.length) return;
      var paths = [];
      for (var i = 0; i < Math.min(files.length, 5); i++) paths.push(files[i].path || files[i].name);
      eel.ui_submit_file_drop(paths)(function (r) {
        if (r && r.status === 'ok' && r.files && r.files.length) {
          var names = r.files.map(function (x) { return x.name; }).join(', ');
          if (status) status.textContent = '\u{1F4CE} ' + names;
          if (window.addLogEntry) window.addLogEntry('file', 'Dropped: ' + names);
          if (window.receiverText) window.receiverText('File' + (r.files.length > 1 ? 's' : '') + ' uploaded: ' + names + '. What should I do?');
        }
      });
    });
  }

  function updateMetrics() {
    eel.ui_get_metrics()(function (m) {
      if (!m) return;
      if (typeof m.cpu === 'number') setMetric('cpu', m.cpu + '%');
      if (typeof m.mem === 'number') setMetric('mem', m.mem + '%');
      if (typeof m.net_bytes === 'number') {
        if (updateMetrics._lastNet != null) {
          var mbps = (m.net_bytes - updateMetrics._lastNet) / 1048576 / 2;
          setMetric('net', Math.max(0, mbps).toFixed(1) + 'MB/s');
        }
        updateMetrics._lastNet = m.net_bytes;
      }
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
      else bar.style.background = '';
    }
  }

  function wireDebugPanel() {
    $('log-toggle-btn').addEventListener('click', function () { $('debug-panel').classList.toggle('hidden'); });
    $('debug-close').addEventListener('click', function () { $('debug-panel').classList.add('hidden'); });
  }

  function openWorkspace(text) {
    var ov = $('workspace-overlay');
    var content = $('workspace-content');
    var status = $('workspace-status');
    if (!ov) return;
    if (status) status.textContent = '';
    if (text != null && content) {
      content.textContent = text;
      ov.classList.remove('hidden');
    } else {
      eel.ui_get_last_response()(function (r) {
        if (content) content.textContent = (r && r.text) ? r.text : 'No output yet.';
        ov.classList.remove('hidden');
      });
    }
  }
  window.openWorkspace = openWorkspace;

  function wireWorkspace() {
    var btn = $('workspace-button');
    if (btn) btn.addEventListener('click', function () { openWorkspace(); });
    var close = $('workspace-close');
    if (close) close.addEventListener('click', function () { $('workspace-overlay').classList.add('hidden'); });
    var bd = document.querySelector('#workspace-overlay .overlay-backdrop');
    if (bd) bd.addEventListener('click', function () { $('workspace-overlay').classList.add('hidden'); });
    document.querySelectorAll('#workspace-overlay .ws-btn').forEach(function (b) {
      b.addEventListener('click', function () {
        var action = b.getAttribute('data-action');
        var status = $('workspace-status');
        if (status) status.textContent = 'Working...';
        eel.ui_output_action(action)(function (r) {
          if (status) status.textContent = (r && r.message) ? r.message : '';
          if (r && r.text && $('workspace-content')) $('workspace-content').textContent = r.text;
        });
      });
    });
  }

  function wireSettings() {
    $('settings-close').addEventListener('click', function () { $('settings-overlay').classList.add('hidden'); });
    var bd = document.querySelector('#settings-overlay .overlay-backdrop');
    if (bd) bd.addEventListener('click', function () { $('settings-overlay').classList.add('hidden'); });
  }

  function openSettings() {
    $('settings-overlay').classList.remove('hidden');
    eel.ui_get_env_status()(function (s) {
      var el = $('provider-list');
      if (!el) return;
      var html = '';
      Object.keys(s || {}).forEach(function (k) {
        html += '<div class="provider-row"><span class="provider-dot ' + (s[k] ? 'on' : 'off') + '"></span>' +
                k.toUpperCase() + ': ' + (s[k] ? 'OK' : 'NOT SET') + '</div>';
      });
      el.innerHTML = html;
    });
    eel.ui_get_runtime_status()(function (s) {
      var el = $('runtime-list');
      if (!el || !s) return;
      el.innerHTML = '<div class="provider-row">Brain: ' + (s.brain_provider || 'N/A').toUpperCase() + '</div>' +
                     '<div class="provider-row">ASR: ' + (s.asr_provider || 'N/A').toUpperCase() + '</div>' +
                     '<div class="provider-row">Hotword: ' + (s.hotword_enabled ? 'ON' : 'OFF') + '</div>';
    });
    eel.getMemorySummary()(function (m) {
      var el = $('memory-list');
      if (!el) return;
      el.textContent = (m && m.summary) ? m.summary : 'No memory yet.';
    });
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'F11') { e.preventDefault(); }
  });

  init();
})();
