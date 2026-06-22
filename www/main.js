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
    wireInput();
    wireButtons();
    wireFileDrop();
    wireDebugPanel();
    wireSettings();
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
    var items = [
      { label: 'Open Chrome', text: 'open chrome' },
      { label: 'Search Google', text: 'search ' },
      { label: 'Create Project', text: 'create project ' },
      { label: 'What time is it?', text: 'what time is it' },
      { label: 'Screenshot', text: 'take a screenshot' },
      { label: 'Weather', text: "what's the weather" },
      { label: 'Remember', text: 'remember that ' },
      { label: 'Stop', text: 'stop' }
    ];
    items.forEach(function (s) {
      var chip = document.createElement('div');
      chip.className = 'suggestion-chip';
      chip.textContent = s.label;
      chip.addEventListener('click', function () { submit(s.text); });
      list.appendChild(chip);
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

  function wireButtons() {
    $('power-button').addEventListener('click', function () {
      eel.submitUserCommand('sleep')();
    });
    $('settings-button').addEventListener('click', openSettings);
  }

  function wireFileDrop() {
    var zone = $('file-drop-zone');
    if (!zone) return;
    zone.addEventListener('dragover', function (e) { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', function () { zone.classList.remove('drag-over'); });
    zone.addEventListener('drop', function (e) {
      e.preventDefault();
      zone.classList.remove('drag-over');
      if (window.addLogEntry) window.addLogEntry('file', 'File dropped');
    });
  }

  function wireDebugPanel() {
    $('log-toggle-btn').addEventListener('click', function () { $('debug-panel').classList.toggle('hidden'); });
    $('debug-close').addEventListener('click', function () { $('debug-panel').classList.add('hidden'); });
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
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'F11') { e.preventDefault(); }
  });

  init();
})();
