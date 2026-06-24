(function () {
  var canvas = document.getElementById('hud-canvas');
  if (!canvas) return;

  var ctx = canvas.getContext('2d');
  var state = 'idle', tick = 0, animId = null;
  var cx = 0, cy = 0, fw = 0;
  var scale = 1, tgtScale = 1, halo = 55, tgtHalo = 55;
  var lastT = Date.now();
  var scan = 0, scan2 = 180;
  var rings = [0, 120, 240];
  var pulses = [0, 50, 100];
  var particles = [];
  var blink = true, blinkTick = 0;
  var speaking = false;
  var bgDots = [];

  var PRI = '#00d4ff', PRI_DIM = '#007a99', PRI_GHO = '#001f2e';
  var ACC = '#ff6b00', ACC2 = '#ffcc00', GREEN = '#00ff88';
  var MUTED = '#ff3366', BORDER_B = '#1a5c7a';

  function hex(c, a) {
    var r = parseInt(c.slice(1, 3), 16), g = parseInt(c.slice(3, 5), 16), b = parseInt(c.slice(5, 7), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + a + ')';
  }

  function resize() {
    var rect = canvas.parentElement.getBoundingClientRect();
    var size = Math.min(rect.width * 0.95, rect.height * 0.85, 560);
    var dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr; canvas.height = size * dpr;
    canvas.style.width = size + 'px'; canvas.style.height = size + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    fw = size; cx = fw / 2; cy = fw / 2;
    bgDots = [];
    for (var x = 0; x < fw; x += 40) for (var y = 0; y < fw; y += 40) bgDots.push([x, y]);
  }

  function draw() {
    ctx.clearRect(0, 0, fw, fw);

    var rFace = fw * 0.30;
    var clr = speaking ? MUTED : PRI;

    // Halo glow
    for (var i = 0; i < 10; i++) {
      ctx.beginPath(); ctx.arc(cx, cy, rFace * (1.9 - i * 0.08), 0, Math.PI * 2);
      ctx.strokeStyle = hex(PRI, Math.max(0, halo * 0.0012 * (1 - i / 10))); ctx.lineWidth = 1; ctx.stroke();
    }

    // Pulse rings
    for (var pi = 0; pi < pulses.length; pi++) {
      if (pulses[pi] < fw * 0.74) {
        ctx.beginPath(); ctx.arc(cx, cy, pulses[pi], 0, Math.PI * 2);
        ctx.strokeStyle = hex(clr, Math.max(0, 1 - pulses[pi] / (fw * 0.74)) * 0.6); ctx.lineWidth = 1.2; ctx.stroke();
      }
    }

    // Spinning arcs
    var specs = [[0.50, 2.5, 115, 78], [0.42, 2, 78, 55], [0.34, 1.5, 56, 40]];
    for (var ai = 0; ai < specs.length; ai++) {
      var s = specs[ai], ringR = fw * s[0], aVal = Math.max(0, halo * 0.002 * (1 - ai * 0.25));
      var a = rings[ai], end = a + 360;
      while (a < end) {
        ctx.beginPath(); ctx.arc(cx, cy, ringR, a * Math.PI / 180, (a + s[2]) * Math.PI / 180);
        ctx.strokeStyle = hex(clr, aVal); ctx.lineWidth = s[1]; ctx.stroke(); a += s[2] + s[3];
      }
    }

    // Scanner arcs
    var sr = fw * 0.52, sa = Math.min(1, halo * 0.025), ex = speaking ? 70 : 42;
    ctx.beginPath(); ctx.arc(cx, cy, sr, scan * Math.PI / 180, (scan + ex) * Math.PI / 180);
    ctx.strokeStyle = hex(clr, sa); ctx.lineWidth = 2; ctx.stroke();
    ctx.beginPath(); ctx.arc(cx, cy, sr, scan2 * Math.PI / 180, (scan2 + ex) * Math.PI / 180);
    ctx.strokeStyle = hex(ACC, sa * 0.6); ctx.lineWidth = 1.2; ctx.stroke();

    // Tick marks
    var tO = fw * 0.518, tI = fw * 0.494;
    for (var d = 0; d < 360; d += 10) {
      var rad = d * Math.PI / 180, inner = d % 30 === 0 ? tI : tI + 6;
      ctx.beginPath(); ctx.moveTo(cx + tO * Math.cos(rad), cy - tO * Math.sin(rad));
      ctx.lineTo(cx + inner * Math.cos(rad), cy - inner * Math.sin(rad));
      ctx.strokeStyle = hex(PRI, 0.5); ctx.lineWidth = d % 30 === 0 ? 1.2 : 0.6; ctx.stroke();
    }

    // Crosshair
    var chR = fw * 0.53, gap = fw * 0.18;
    ctx.strokeStyle = hex(PRI, halo * 0.008); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx - chR, cy); ctx.lineTo(cx - gap, cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx + gap, cy); ctx.lineTo(cx + chR, cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, cy - chR); ctx.lineTo(cx, cy - gap); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, cy + gap); ctx.lineTo(cx, cy + chR); ctx.stroke();

    // Corner brackets
    var bl = 22, hl = cx - fw / 2 + 4, hr = cx + fw / 2 - 4, ht = cy - fw / 2 + 4, hb = cy + fw / 2 - 4;
    ctx.strokeStyle = hex(PRI, 0.7); ctx.lineWidth = 1.5;
    [[hl,ht,1,1],[hr,ht,-1,1],[hl,hb,1,-1],[hr,hb,-1,-1]].forEach(function(c) {
      ctx.beginPath(); ctx.moveTo(c[0], c[1]); ctx.lineTo(c[0]+c[2]*bl, c[1]); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(c[0], c[1]); ctx.lineTo(c[0], c[1]+c[3]*bl); ctx.stroke();
    });

    // Center text
    var ls = fw * 0.22;
    var orbR = ls * scale;
    for (var oi = 8; oi > 0; oi--) {
      ctx.beginPath(); ctx.arc(cx, cy, orbR * oi / 8, 0, Math.PI * 2);
      ctx.fillStyle = hex(PRI, Math.max(0, halo * 0.018 * oi / 8) * 0.3); ctx.fill();
    }
    ctx.fillStyle = PRI; ctx.font = 'bold ' + Math.floor(ls * 0.28) + 'px monospace';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('N.E.X.I', cx, cy - 4);
    ctx.fillStyle = PRI_DIM; ctx.font = Math.floor(ls * 0.14) + 'px monospace';
    ctx.fillText('ONLINE', cx, cy + ls * 0.3);

    // Particles
    particles.forEach(function(p) {
      ctx.beginPath(); ctx.arc(p[0], p[1], 2, 0, Math.PI * 2);
      ctx.fillStyle = hex(PRI, p[4]); ctx.fill();
    });

    // Waveform
    var wf = document.getElementById('waveform');
    if (wf) {
      var html = '';
      for (var wi = 0; wi < 28; wi++) {
        var h = speaking ? 3 + Math.floor(Math.random() * 18) : Math.max(2, Math.floor(3 + 2 * Math.sin(tick * 0.09 + wi * 0.7)));
        html += '<span style="height:' + h + 'px;background:' + (speaking ? PRI : BORDER_B) + ';width:5px;border-radius:1px;"></span>';
      }
      wf.innerHTML = html;
    }
  }

  function step() {
    tick++;
    var now = Date.now(), since = now - lastT;

    // Throttle to ~30fps when idle, 60fps when speaking
    var targetFps = speaking ? 60 : 30;
    var minInterval = 1000 / targetFps;
    if (since < minInterval) {
        animId = requestAnimationFrame(step);
        return;
    }

    if (since > (speaking ? 100 : 450)) {
      if (speaking) { tgtScale = 1.04 + Math.random() * 0.08; tgtHalo = 130 + Math.random() * 70; }
      else if (state === 'sleeping') { tgtScale = 0.995 + Math.random() * 0.005; tgtHalo = 15 + Math.random() * 12; }
      else { tgtScale = 0.998 + Math.random() * 0.006; tgtHalo = 45 + Math.random() * 20; }
      lastT = now;
    }

    var sp = speaking ? 0.35 : 0.12;
    scale += (tgtScale - scale) * sp; halo += (tgtHalo - halo) * sp;

    var speeds = speaking ? [1.3, -0.9, 2.0] : [0.55, -0.35, 0.9];
    for (var ri = 0; ri < 3; ri++) rings[ri] = (rings[ri] + speeds[ri]) % 360;
    scan = (scan + (speaking ? 3 : 1.3)) % 360;
    scan2 = (scan2 + (speaking ? -2 : -0.75)) % 360; if (scan2 < 0) scan2 += 360;

    var lim = fw * 0.74, pspd = speaking ? 3.8 : 1.6;
    pulses = pulses.map(function(r) { return r + pspd; }).filter(function(r) { return r < lim; });
    if (pulses.length < 3 && Math.random() < (speaking ? 0.07 : 0.02)) pulses.push(0);

    if (speaking && Math.random() < 0.25) {
      var ang = Math.random() * 2 * Math.PI, rS = fw * 0.28;
      particles.push([cx + Math.cos(ang) * rS, cy + Math.sin(ang) * rS, Math.cos(ang) * (0.8 + Math.random() * 1.4), Math.sin(ang) * (0.8 + Math.random() * 1.4) - 0.3, 1]);
    }
    particles = particles.map(function(p) { return [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.025]; }).filter(function(p) { return p[4] > 0; });

    blinkTick++; if (blinkTick >= 38) { blink = !blink; blinkTick = 0; }

    draw(); animId = requestAnimationFrame(step);
  }

  window.setOrbState = function (s) {
    var valid = ['idle','listening','thinking','speaking','sleeping','error','wake_detected','recognising'];
    if (valid.indexOf(s) >= 0) state = s;
    speaking = (s === 'speaking');
    if (s === 'wake_detected') { pulses = [0, 0]; halo = 130; scale = 1.03; }
    if (s === 'listening') { pulses = [0]; halo = 120; }
    if (s === 'recognising') { halo = 100; }
    if (s === 'speaking') { halo = 150; scale = 1.05; }
    if (s === 'thinking') { halo = 90; }
    if (s === 'sleeping' || s === 'idle') { tgtHalo = s === 'sleeping' ? 20 : 55; tgtScale = 1.0; }
  };

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { if (animId) { cancelAnimationFrame(animId); animId = null; } }
    else { if (!animId) { lastT = Date.now(); animId = requestAnimationFrame(step); } }
  });

  resize(); window.addEventListener('resize', resize);
  lastT = Date.now(); animId = requestAnimationFrame(step);
})();
