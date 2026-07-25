/* Live Studio / agency panel.
 *
 * Devendra: "whenever I run the studio or any agency for development, a new space opens
 * for NEXI — show the results and tell me NEXI is handling this part, with live updates."
 *
 * The panel stays hidden until the first studio event arrives, so it costs nothing during
 * normal voice use and appears exactly when a build starts. It is driven by
 * `eel.studioEvent(payload)` from engine/ui_event_bridge.studio_event, which is emitted
 * from supervisor._checkpoint — the single funnel every stage passes through, so the
 * panel reflects the real run instead of a separate narration that could drift.
 *
 * Built with DOM nodes and textContent, never innerHTML +=: that pattern re-parses the
 * whole list on every event (measured 8.5ms/line, half a frame budget) and would make
 * stage text parseable as markup.
 */
(function () {
  var STAGES = [
    'requirements', 'research', 'architecture', 'sprint_plan', 'implementation',
    'developer_tests', 'qa', 'security_review', 'integration', 'release', 'closeout'
  ];

  var el = {};            // cached nodes — built once
  var stageRow = {};      // stage name -> its row element
  var built = false;
  var lastRun = '';

  function build() {
    if (built) return;
    var panel = document.getElementById('studio-panel');
    if (!panel) return;

    el.panel = panel;
    el.title = document.getElementById('studio-run-title');
    el.status = document.getElementById('studio-status');
    el.meta = document.getElementById('studio-meta');
    el.stages = document.getElementById('studio-stages');
    el.log = document.getElementById('studio-log');

    // one row per stage, created ONCE; later updates only touch className/textContent
    el.stages.textContent = '';
    STAGES.forEach(function (name, i) {
      var row = document.createElement('div');
      row.className = 'studio-stage pending';
      var num = document.createElement('span');
      num.className = 'studio-stage-num';
      num.textContent = 'G' + (i + 1);
      var label = document.createElement('span');
      label.className = 'studio-stage-name';
      label.textContent = name.replace(/_/g, ' ');
      var mark = document.createElement('span');
      mark.className = 'studio-stage-mark';
      mark.textContent = '';
      row.appendChild(num); row.appendChild(label); row.appendChild(mark);
      el.stages.appendChild(row);
      stageRow[name] = row;
    });
    var closeBtn = document.getElementById('studio-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        panel.classList.remove('open');   // hide only; the run keeps going
      });
    }
    built = true;
  }

  function show() {
    build();
    if (el.panel) el.panel.classList.add('open');
  }

  function setStageState(name, state) {
    var row = stageRow[name];
    if (!row) return;
    row.className = 'studio-stage ' + state;
    var mark = row.querySelector('.studio-stage-mark');
    if (mark) mark.textContent = state === 'done' ? '✓'
      : state === 'active' ? '…'
      : state === 'failed' ? '✕' : '';
  }

  function appendLog(text) {
    if (!el.log || !text) return;
    var line = document.createElement('div');
    line.className = 'studio-log-line';
    line.textContent = text;              // textContent: stage output is untrusted
    el.log.appendChild(line);
    el.log.scrollTop = el.log.scrollHeight;
    while (el.log.children.length > 200) el.log.removeChild(el.log.firstChild);
  }

  function onEvent(p) {
    if (!p || typeof p !== 'object') return;
    show();

    if (p.run_id && p.run_id !== lastRun) {   // new build -> reset the board
      lastRun = p.run_id;
      STAGES.forEach(function (s) { setStageState(s, 'pending'); });
      if (el.log) el.log.textContent = '';
      appendLog('NEXI is handling this build — run ' + p.run_id);
    }

    (p.completed || []).forEach(function (s) { setStageState(s, 'done'); });
    if (p.stage && (p.completed || []).indexOf(p.stage) === -1) {
      setStageState(p.stage, /fail|block/i.test(p.status || '') ? 'failed' : 'active');
    }

    if (el.title) {
      el.title.textContent = p.stage
        ? 'NEXI · ' + String(p.stage).replace(/_/g, ' ')
        : 'NEXI Studio';
    }
    if (el.status) {
      el.status.textContent = p.status || '';
      el.status.className = 'studio-status ' + (/fail|block/i.test(p.status || '') ? 'bad' : 'ok');
    }
    if (el.meta) {
      // who/what is doing the work right now — the "NEXI is handling this part" signal
      var bits = [];
      if (p.agent) bits.push(p.agent);
      if (p.model) bits.push(p.model);
      if (p.mode) bits.push(p.mode);
      var done = (p.completed || []).length;
      if (p.total_stages) bits.push(done + '/' + p.total_stages + ' stages');
      el.meta.textContent = bits.join('  ·  ');
    }
    if (p.message) appendLog((p.stage ? '[' + p.stage + '] ' : '') + p.message);
  }

  // Expose to Eel. eel.expose is a no-op shim in the static Playwright harness.
  if (typeof eel !== 'undefined' && eel && typeof eel.expose === 'function') {
    try { eel.expose(onEvent, 'studioEvent'); } catch (e) { /* offline preview */ }
  }
  window.studioEvent = onEvent;      // also callable directly (tests, manual drive)
  window.__nexiStudioPanel = { build: build, show: show, stages: STAGES };
})();
