/* State-reactive HUD background layers.
 *
 * The CROSS-FADE is pure CSS (body[data-state] -> opacity). This file exists only to
 * solve what CSS can't: a video at opacity:0 still decodes every frame, so stacking
 * four of them would burn CPU/GPU continuously and undo the lag work. Here we keep
 * exactly ONE background layer playing and pause the rest — but only AFTER the fade
 * finishes, otherwise the outgoing layer freezes mid-fade and you see it stutter out.
 *
 * controller.js is the single source of truth for state; we only observe it.
 */
(function () {
  var FADE_MS = 700;          // must match the CSS transition on .hud-video-bg
  var PAUSE_DELAY = FADE_MS + 60;

  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var pauseTimers = new WeakMap();

  function layers() { return document.querySelectorAll('.hud-video-bg[data-for]'); }

  function wants(el, state) {
    return (' ' + (el.getAttribute('data-for') || '') + ' ').indexOf(' ' + state + ' ') !== -1;
  }

  function safePlay(v) {
    // Autoplay can reject (policy, or the element is mid-teardown). Muted+playsinline
    // is allowed everywhere we run, but never let a rejection surface as an error.
    try {
      var p = v.play();
      if (p && typeof p.catch === 'function') p.catch(function () {});
    } catch (e) { /* ignore */ }
  }

  function pauseLater(v) {
    var timer = pauseTimers.get(v);
    if (timer) clearTimeout(timer);
    pauseTimers.set(v, setTimeout(function () {
      v.pause();
      pauseTimers.delete(v);
    }, PAUSE_DELAY));
  }

  function pauseAll() {
    Array.prototype.forEach.call(document.querySelectorAll('video'), function (v) {
      var timer = pauseTimers.get(v);
      if (timer) { clearTimeout(timer); pauseTimers.delete(v); }
      v.pause();
    });
  }

  function apply(state) {
    if (reduced || document.hidden) { pauseAll(); return; }
    var sleeping = state === 'sleep' || state === 'sleeping';
    Array.prototype.forEach.call(layers(), function (v) {
      if (typeof v.play !== 'function') return;   // the <img> gif layer — CSS handles it

      var timer = pauseTimers.get(v);
      if (timer) { clearTimeout(timer); pauseTimers.delete(v); }

      if (!sleeping && wants(v, state)) {
        if (v.paused) safePlay(v);
      } else if (!v.paused) {
        pauseLater(v);
      }
    });
    Array.prototype.forEach.call(document.querySelectorAll('.hud-rail'), function (v) {
      if (sleeping) {
        if (!v.paused) pauseLater(v);
      } else {
        var timer = pauseTimers.get(v);
        if (timer) { clearTimeout(timer); pauseTimers.delete(v); }
        if (v.readyState === 0) v.load();
        if (v.paused) safePlay(v);
      }
    });
  }

  function currentState() {
    return document.body.getAttribute('data-state') || 'sleep';
  }

  function start() {
    if (reduced) { pauseAll(); return; }

    apply(currentState());

    // React to controller.js's body[data-state] writes.
    if (window.MutationObserver) {
      new MutationObserver(function (muts) {
        for (var i = 0; i < muts.length; i++) {
          if (muts[i].attributeName === 'data-state') { apply(currentState()); return; }
        }
      }).observe(document.body, { attributes: true, attributeFilter: ['data-state'] });
    }

    // A backgrounded tab pauses/throttles media; resync on return so we don't come
    // back to a frozen background.
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) pauseAll();
      else apply(currentState());
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

  // exposed for the Playwright check
  window.__nexiHudLayers = { apply: apply, current: currentState };
})();
