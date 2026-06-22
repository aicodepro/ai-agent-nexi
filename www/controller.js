(function () {
  var MAX_LOG = 300;
  var logEntries = [];
  var lastLog = { key: '', at: 0 };

  var STATES = {
    sleep: 'sleep', idle: 'sleep', sleeping: 'sleep',
    wake_detected: 'wake_detected', listening: 'listening',
    waiting_for_speech: 'waiting_for_speech',
    hearing_speech: 'listening', recognising: 'recognising',
    transcribing: 'recognising', thinking: 'thinking',
    saying: 'saying', speaking: 'saying', error: 'error'
  };

  function ts() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function esc(t) {
    return String(t || '').replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function addLog(level, msg) {
    var now = Date.now();
    var key = level + '|' + msg;
    if (lastLog.key === key && now - lastLog.at < 250) return;
    lastLog = { key: key, at: now };
    logEntries.push({ level: level, message: msg, time: ts() });
    if (logEntries.length > MAX_LOG) logEntries = logEntries.slice(-MAX_LOG);

    var body = document.getElementById('nexi-log');
    if (body) {
      var cls = { err: 'err', you: 'you', ai: 'ai', file: 'file' }[level] || 'sys';
      body.innerHTML += '<div class="log-msg ' + cls + '">' + esc(msg) + '</div>';
      body.scrollTop = body.scrollHeight;
      if (body.children.length > 200) while (body.children.length > 100) body.removeChild(body.firstChild);
    }

    var db = document.getElementById('debug-log-body');
    if (db) {
      var lvl = { warn: 'warn', error: 'error', route: 'route' }[level] || 'info';
      db.innerHTML += '<div class="log-entry ' + lvl + '"><span class="ts">' + ts() + '</span>' + esc(msg) + '</div>';
      if (db.children.length > 300) db.removeChild(db.firstChild);
    }
  }

  window.updateNexiState = function (payload) {
    if (typeof payload === 'string') try { payload = JSON.parse(payload); } catch (e) { payload = {}; }
    payload = payload || {};
    var raw = payload.state || 'sleep';
    var st = STATES[raw] || 'sleep';
    var src = payload.source || '';
    var txt = payload.text || '';

    if (window.setOrbState) window.setOrbState(st === 'saying' ? 'speaking' : st);

    var badge = document.getElementById('nexi-state');
    var labels = {
      sleep: 'SLEEP MODE', wake_detected: 'WAKE DETECTED', listening: 'LISTENING',
      waiting_for_speech: 'WAITING', recognising: 'RECOGNISING',
      thinking: 'THINKING', saying: 'SPEAKING', error: 'ERROR'
    };
    if (badge) {
      badge.textContent = payload.label || labels[st] || st.toUpperCase();
      ['sleep', 'listening', 'recognising', 'thinking', 'saying'].forEach(function (n) {
        badge.classList.remove('nexi-state-' + n);
      });
      badge.classList.add('nexi-state-' + st);
    }

    var hint = document.getElementById('nexi-source');
    if (hint) {
      if (st === 'sleep') hint.textContent = 'Say Hey Nexi or double clap to wake';
      else if (st === 'listening') hint.textContent = 'Listening... speak now';
      else if (st === 'recognising') hint.textContent = 'Recognising...';
      else if (st === 'thinking') hint.textContent = 'Thinking...';
      else if (st === 'saying') hint.textContent = 'Speaking...';
      else if (st === 'wake_detected') hint.textContent = 'Wake detected (' + (src || 'unknown') + ')';
      else hint.textContent = '';
    }

    if (st === 'listening') addLog('sys', 'SYS: Listening...');
    else if (st === 'recognising') addLog('sys', 'SYS: Recognising...');
    else if (st === 'thinking') addLog('sys', 'SYS: Thinking...');
    else if (st === 'saying') addLog('sys', 'SYS: Speaking...');
    else if (st === 'sleep') addLog('sys', 'SYS: Sleep mode');
    else if (st === 'wake_detected') addLog('wake', 'WAKE: ' + (src || 'detected'));
  };

  window.senderText = function (msg) {
    if (!msg) return;
    var el = document.getElementById('nexi-transcript');
    if (el) el.textContent = 'You: ' + String(msg).slice(0, 200);
    addLog('you', 'You: ' + msg.slice(0, 200));
  };

  window.receiverText = function (msg) {
    if (!msg) return;
    var el = document.getElementById('nexi-response');
    if (el) el.textContent = 'Nexi: ' + String(msg).slice(0, 300);
    addLog('ai', 'Nexi: ' + msg.slice(0, 300));
    if (String(msg).length > 400 && window.openWorkspace) window.openWorkspace(String(msg));
  };

  window.updateState = function (s) { window.updateNexiState(typeof s === 'string' ? { state: s } : s); };
  window.appendLog = function (l, m) { addLog(typeof l === 'string' ? l : 'sys', String(m || '')); };
  window.appendResponse = function (t) { window.receiverText(t); };
  window.DisplayMessage = function () { window.updateNexiState({ state: 'saying' }); };
  window.ShowHood = function () { window.updateNexiState({ state: 'sleep' }); };
  window.setStatus = function (t) { var b = document.getElementById('nexi-state'); if (b) b.textContent = t; };

  window.addLogEntry = addLog;
  window.getLogEntries = function () { return logEntries; };

  if (typeof eel !== 'undefined') {
    eel.expose(window.updateNexiState, 'updateNexiState');
    eel.expose(window.updateState, 'updateState');
    eel.expose(window.senderText, 'senderText');
    eel.expose(window.receiverText, 'receiverText');
    eel.expose(window.appendLog, 'appendLog');
    eel.expose(window.appendResponse, 'appendResponse');
    eel.expose(window.DisplayMessage, 'DisplayMessage');
    eel.expose(window.ShowHood, 'ShowHood');
    eel.expose(window.setStatus, 'setStatus');
  }
})();
