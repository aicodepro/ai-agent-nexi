(function () {
  var canvas = document.getElementById('hud-canvas');
  if (!canvas) return;

  var ctx = canvas.getContext('2d');
  var state = 'idle';
  var tick = 0;
  var animId = null;
  var cx = 0, cy = 0, fw = 0;
  var scale = 1, tgtScale = 1, halo = 55, tgtHalo = 55;
  var lastT = Date.now();
  var scan = 0, scan2 = 180;
  var rings = [0, 120, 240];
  var pulses = [0, 50, 100];
  var particles = [];
  var blink = true, blinkTick = 0;
  var logoImg = null;
  var speaking = false;
  var bgDots = [];

  var PRI = '#00d4ff', PRI_DIM = '#007a99', PRI_GHO = '#001f2e';
  var ACC = '#ff6b00', ACC2 = '#ffcc00', GREEN = '#00ff88';
  var RED = '#ff3355', MUTED_COLOR = '#ff3366';
  var BORDER_B = '#1a5c7a', WHITE = '#d8f8ff';

  function hexToRgba(hex, alpha) {
    var r = parseInt(hex.slice(1, 3), 16);
    var g = parseInt(hex.slice(3, 5), 16);
    var b = parseInt(hex.slice(5, 7), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
  }

  // Load logo
  var logo = new Image();
  logo.onload = function () { logoImg = logo; };
  logo.src = 'assets/jarvis-logo.svg';

  function resize() {
    var rect = canvas.parentElement.getBoundingClientRect();
    var size = Math.min(rect.width * 0.95, rect.height * 0.85, 560);
    var dpr = (window.devicePixelRatio || 1);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = size + 'px';
    canvas.style.height = size + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    fw = size;
    cx = fw / 2; cy = fw / 2;
    bgDots = [];
    for (var x = 0; x < fw; x += 40) {
      for (var y = 0; y < fw; y += 40) {
        bgDots.push([x, y]);
      }
    }
  }

  function hex(c, a) { return hexToRgba(c, a); }

  function draw(t) {
    ctx.clearRect(0, 0, fw, fw);
    ctx.fillStyle = '#00060a';
    ctx.fillRect(0, 0, fw, fw);

    // Grid dots
    for (var di = 0; di < bgDots.length; di++) {
      ctx.fillStyle = PRI_GHO;
      ctx.fillRect(bgDots[di][0], bgDots[di][1], 1, 1);
    }

    var rFace = fw * 0.30;

    // Halo glow rings
    for (var i = 0; i < 10; i++) {
      var r = rFace * (1.9 - i * 0.08);
      var frc = 1 - i / 10;
      var a = Math.max(0, Math.min(1, halo * 0.0012 * frc));
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.strokeStyle = hex(PRI, a);
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Pulse rings
    for (var pi = 0; pi < pulses.length; pi++) {
      var pr = pulses[pi];
      if (pr < fw * 0.74) {
        var pa = Math.max(0, 1 - pr / (fw * 0.74));
        ctx.beginPath();
        ctx.arc(cx, cy, pr, 0, Math.PI * 2);
        ctx.strokeStyle = hex(speaking ? MUTED_COLOR : PRI, pa * 0.6);
        ctx.lineWidth = 1.2;
        ctx.stroke();
      }
    }

    // Spinning arc rings
    var arcSpecs = [
      [0.50, 2.5, 115, 78],
      [0.42, 2, 78, 55],
      [0.34, 1.5, 56, 40]
    ];
    for (var ai = 0; ai < arcSpecs.length; ai++) {
      var s = arcSpecs[ai];
      var ringR = fw * s[0];
      var w = s[1];
      var arcL = s[2];
      var gap = s[3];
      var aVal = Math.max(0, Math.min(1, halo * 0.002 * (1 - ai * 0.25)));
      var angle = rings[ai];
      var endAng = angle + 360;
      while (angle < endAng) {
        ctx.beginPath();
        ctx.arc(cx, cy, ringR, angle * Math.PI / 180, (angle + arcL) * Math.PI / 180);
        ctx.strokeStyle = hex(speaking ? MUTED_COLOR : PRI, aVal);
        ctx.lineWidth = w;
        ctx.stroke();
        angle += arcL + gap;
      }
    }

    // Scanner arcs
    var sr = fw * 0.52;
    var sa = Math.min(1, halo * 0.025);
    var ex = speaking ? 70 : 42;
    ctx.beginPath();
    ctx.arc(cx, cy, sr, scan * Math.PI / 180, (scan + ex) * Math.PI / 180);
    ctx.strokeStyle = hex(speaking ? MUTED_COLOR : PRI, sa);
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, sr, scan2 * Math.PI / 180, (scan2 + ex) * Math.PI / 180);
    ctx.strokeStyle = hex(ACC, sa * 0.6);
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // Tick marks
    var tOut = fw * 0.518;
    var tIn = fw * 0.494;
    for (var deg = 0; deg < 360; deg += 10) {
      var rad = deg * Math.PI / 180;
      var inR = deg % 30 === 0 ? tIn : tIn + 6;
      ctx.beginPath();
      ctx.moveTo(cx + tOut * Math.cos(rad), cy - tOut * Math.sin(rad));
      ctx.lineTo(cx + inR * Math.cos(rad), cy - inR * Math.sin(rad));
      ctx.strokeStyle = hex(PRI, 0.5);
      ctx.lineWidth = (deg % 30 === 0 ? 1.2 : 0.6);
      ctx.stroke();
    }

    // Crosshair
    var chR = fw * 0.53;
    var gapH = fw * 0.18;
    ctx.strokeStyle = hex(PRI, halo * 0.008);
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx - chR, cy); ctx.lineTo(cx - gapH, cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx + gapH, cy); ctx.lineTo(cx + chR, cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, cy - chR); ctx.lineTo(cx, cy - gapH); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, cy + gapH); ctx.lineTo(cx, cy + chR); ctx.stroke();

    // Corner brackets
    var bl = 22;
    var hl = cx - fw / 2 + 4, hr = cx + fw / 2 - 4;
    var ht = cy - fw / 2 + 4, hb = cy + fw / 2 - 4;
    ctx.strokeStyle = hex(PRI, 0.7);
    ctx.lineWidth = 1.5;
    var corners = [[hl,ht,1,1],[hr,ht,-1,1],[hl,hb,1,-1],[hr,hb,-1,-1]];
    for (var ci = 0; ci < 4; ci++) {
      var c = corners[ci];
      ctx.beginPath(); ctx.moveTo(c[0], c[1]); ctx.lineTo(c[0] + c[2] * bl, c[1]); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(c[0], c[1]); ctx.lineTo(c[0], c[1] + c[3] * bl); ctx.stroke();
    }

    // Logo in center
    var logoSize = fw * 0.22;
    if (logoImg) {
      // Draw black circle behind logo
      ctx.beginPath();
      ctx.arc(cx, cy, logoSize * 1.15, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
      ctx.fill();
      ctx.drawImage(logoImg, cx - logoSize, cy - logoSize, logoSize * 2, logoSize * 2);
    } else {
      // Draw dark circle + text
      var orbR = fw * 0.22 * scale;
      for (var oi = 8; oi > 0; oi--) {
        var r2 = orbR * oi / 8;
        var frc = oi / 8;
        var a = Math.max(0, Math.min(1, halo * 0.018 * frc));
        ctx.beginPath();
        ctx.arc(cx, cy, r2, 0, Math.PI * 2);
        ctx.fillStyle = hex(PRI, a * 0.3);
        ctx.fill();
      }
      ctx.fillStyle = PRI;
      ctx.font = 'bold ' + Math.floor(logoSize * 0.28) + 'px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('J.A.R.V.I.S', cx, cy - 4);
      ctx.fillStyle = PRI_DIM;
      ctx.font = Math.floor(logoSize * 0.14) + 'px monospace';
      ctx.fillText('ONLINE', cx, cy + logoSize * 0.3);
    }

    // Particles when speaking
    for (var p = particles.length - 1; p >= 0; p--) {
      var pt = particles[p];
      ctx.beginPath();
      ctx.arc(pt[0], pt[1], 2, 0, Math.PI * 2);
      ctx.fillStyle = hex(PRI, pt[4]);
      ctx.fill();
    }

    // Status text
    var sy = cy + fw * 0.42;
    var txt, col;
    if (state === 'sleeping') { txt = 'SLEEPING'; col = MUTED_COLOR; }
    else if (state === 'speaking') { txt = 'SPEAKING'; col = ACC; }
    else if (state === 'thinking') { txt = (blink ? 'THINKING' : 'THINKING'); col = ACC2; }
    else if (state === 'recognising') { txt = 'RECOGNISING'; col = ACC2; }
    else if (state === 'transcribing') { txt = 'TRANSCRIBING'; col = ACC2; }
    else if (state === 'processing') { txt = 'PROCESSING'; col = ACC2; }
    else if (state === 'listening') { txt = 'LISTENING'; col = GREEN; }
    else { txt = 'ONLINE'; col = PRI; }

    var sym = blink ? '' : '';
    if (state === 'listening') sym = blink ? '\u25CF ' : '\u25CB ';
    if (state === 'thinking') sym = blink ? '\u25C8 ' : '\u25C7 ';
    if (state === 'recognising' || state === 'transcribing') sym = blink ? '\u25C8 ' : '\u25C7 ';
    if (state === 'speaking') sym = '\u25CF ';

    ctx.fillStyle = col;
    ctx.font = 'bold 11px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(sym + txt, cx, sy);

    // Update DOM state badge
    var badge = document.getElementById('jarvis-status-badge');
    if (badge) { badge.textContent = sym + txt; badge.style.color = col; }

    // Waveform in center-stage
    var wfStrip = document.getElementById('waveform');
    if (wfStrip) {
      var N = 28;
      var html = '';
      for (var wi = 0; wi < N; wi++) {
        var h;
        if (state === 'speaking') {
          h = 3 + Math.floor(Math.random() * 18);
        } else {
          h = Math.max(2, Math.floor(3 + 2 * Math.sin(tick * 0.09 + wi * 0.7)));
        }
        var wfColor = state === 'speaking' ? PRI : BORDER_B;
        html += '<span style="height:' + h + 'px;background:' + wfColor + ';width:5px;border-radius:1px;"></span>';
      }
      wfStrip.innerHTML = html;
    }

    // Wake hint
    var hint = document.getElementById('jarvis-source');
    if (hint) {
      if (state === 'sleeping') hint.textContent = 'Say Hey Jarvis or double clap to wake';
      else if (state === 'idle') hint.textContent = 'Say Hey Jarvis or double clap';
      else hint.textContent = '';
    }
  }

  function step() {
    tick++;
    var now = Date.now();
    var since = now - lastT;

    // Randomize scale/halo
    if (since > (speaking ? 100 : 450)) {
      if (speaking) {
        tgtScale = 1.04 + Math.random() * 0.08;
        tgtHalo = 130 + Math.random() * 70;
      } else if (state === 'sleeping') {
        tgtScale = 0.995 + Math.random() * 0.005;
        tgtHalo = 15 + Math.random() * 12;
      } else {
        tgtScale = 0.998 + Math.random() * 0.006;
        tgtHalo = 45 + Math.random() * 20;
      }
      lastT = now;
    }

    var sp = speaking ? 0.35 : 0.12;
    scale += (tgtScale - scale) * sp;
    halo += (tgtHalo - halo) * sp;

    // Rotate rings
    var speeds = speaking ? [1.3, -0.9, 2.0] : [0.55, -0.35, 0.9];
    for (var ri = 0; ri < 3; ri++) rings[ri] = (rings[ri] + speeds[ri]) % 360;

    // Scan arcs
    scan = (scan + (speaking ? 3.0 : 1.3)) % 360;
    scan2 = (scan2 + (speaking ? -2.0 : -0.75)) % 360;
    if (scan2 < 0) scan2 += 360;

    // Pulse rings
    var lim = fw * 0.74;
    var spd = speaking ? 3.8 : 1.6;
    pulses = pulses.map(function (r) { return r + spd; }).filter(function (r) { return r < lim; });
    if (pulses.length < 3 && Math.random() < (speaking ? 0.07 : 0.02)) pulses.push(0);

    // Particles
    if (speaking && Math.random() < 0.25) {
      var ang = Math.random() * 2 * Math.PI;
      var rS = fw * 0.28;
      particles.push([cx + Math.cos(ang) * rS, cy + Math.sin(ang) * rS,
        Math.cos(ang) * (0.8 + Math.random() * 1.4), Math.sin(ang) * (0.8 + Math.random() * 1.4) - 0.3, 1]);
    }
    particles = particles.map(function (p) {
      return [p[0] + p[2], p[1] + p[3], p[2] * 0.97, p[3] * 0.97, p[4] - 0.025];
    }).filter(function (p) { return p[4] > 0; });

    // Blink
    blinkTick++;
    if (blinkTick >= 38) { blink = !blink; blinkTick = 0; }

    draw(tick);
    animId = requestAnimationFrame(step);
  }

  window.setOrbState = function (s) {
    var valid = ['idle','listening','thinking','speaking','processing','sleeping','error','wake_detected','recognising','transcribing'];
    if (valid.indexOf(s) >= 0) state = s;
    speaking = (s === 'speaking');
    if (s === 'wake_detected') {
      pulses = [0, 0];
      halo = 130;
      scale = 1.03;
    }
    if (s === 'listening') {
      pulses = [0];
      halo = 120;
    }
    if (s === 'recognising' || s === 'transcribing' || s === 'processing') {
      halo = 100;
    }
    if (s === 'speaking') {
      halo = 150;
      scale = 1.05;
    }
    if (s === 'thinking') {
      halo = 90;
    }
    if (s === 'sleeping') {
      halo = 20;
      scale = 1.0;
    }
    if (s === 'idle') {
      tgtScale = 1.0;
      tgtHalo = 55;
    }
  };

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      if (animId) { cancelAnimationFrame(animId); animId = null; }
    } else {
      if (!animId) { lastT = Date.now(); animId = requestAnimationFrame(step); }
    }
  });

  resize();
  window.addEventListener('resize', resize);
  lastT = Date.now();
  animId = requestAnimationFrame(step);
})();
