/* Nexi × Claude Code — embedded terminal panel.
 * Self-contained: builds its own floating panel, streams live events from the
 * Python dispatcher (eel), lets you send a task and STOP a run. Toggle with
 * Ctrl+`  (or window.nexiClaudeTerminal.toggle()). Original Nexi code.
 */
(function () {
  "use strict";
  if (typeof eel === "undefined") return; // UI without eel — nothing to wire

  var panel, output, input, statusEl, visible = false, running = false;

  function build() {
    panel = document.createElement("div");
    panel.id = "nexi-claude-terminal";
    panel.style.cssText =
      "position:fixed;right:16px;bottom:16px;width:520px;max-width:92vw;height:360px;" +
      "background:#0b0f14;color:#cfe3ff;border:1px solid #1f2a37;border-radius:10px;" +
      "box-shadow:0 8px 30px rgba(0,0,0,.5);display:none;flex-direction:column;" +
      "font:12px/1.5 Consolas,'Courier New',monospace;z-index:2147483000;overflow:hidden;";

    var head = document.createElement("div");
    head.style.cssText =
      "display:flex;align-items:center;gap:8px;padding:8px 10px;background:#111826;border-bottom:1px solid #1f2a37;";
    // Built via DOM (not innerHTML) — this panel renders untrusted Claude Code output.
    var title = document.createElement("span");
    title.textContent = "Claude Code";
    title.style.cssText = "color:#7fd1ff;font-weight:600;";
    var statusSpan = document.createElement("span");
    statusSpan.id = "nct-status";
    statusSpan.textContent = "idle";
    statusSpan.style.cssText = "color:#6b7c93;font-size:11px;";
    var spacer = document.createElement("span");
    spacer.style.flex = "1";
    head.appendChild(title);
    head.appendChild(statusSpan);
    head.appendChild(spacer);

    var stopBtn = mkBtn("STOP", "#ff6b6b", function () { stopRun(); });
    var closeBtn = mkBtn("✕", "#6b7c93", function () { toggle(false); });
    head.appendChild(stopBtn);
    head.appendChild(closeBtn);

    output = document.createElement("div");
    output.style.cssText = "flex:1;overflow-y:auto;padding:10px;white-space:pre-wrap;word-break:break-word;";

    var bar = document.createElement("div");
    bar.style.cssText = "display:flex;gap:6px;padding:8px;border-top:1px solid #1f2a37;background:#0d131b;";
    input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Ask Claude Code to…  (Enter to send)";
    input.style.cssText =
      "flex:1;background:#0b0f14;border:1px solid #1f2a37;color:#cfe3ff;border-radius:6px;padding:6px 8px;font:inherit;outline:none;";
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") send(); });
    var sendBtn = mkBtn("Send", "#3ba55d", send);
    bar.appendChild(input);
    bar.appendChild(sendBtn);

    panel.appendChild(head);
    panel.appendChild(output);
    panel.appendChild(bar);
    document.body.appendChild(panel);
    statusEl = document.getElementById("nct-status");
  }

  function mkBtn(label, color, onclick) {
    var b = document.createElement("button");
    b.textContent = label;
    b.style.cssText =
      "background:transparent;border:1px solid " + color + ";color:" + color +
      ";border-radius:6px;padding:3px 10px;cursor:pointer;font:inherit;";
    b.addEventListener("click", onclick);
    return b;
  }

  function line(text, color) {
    if (!output) return;
    var el = document.createElement("div");
    if (color) el.style.color = color;
    el.textContent = text;
    output.appendChild(el);
    output.scrollTop = output.scrollHeight;
  }

  function setStatus(s, color) {
    if (statusEl) { statusEl.textContent = s; statusEl.style.color = color || "#6b7c93"; }
  }

  function send() {
    var task = (input.value || "").trim();
    if (!task || running) return;
    input.value = "";
    line("› " + task, "#7fd1ff");
    running = true; setStatus("running…", "#ffd166");
    try { eel.claude_code_start(task, null); } catch (e) { line("[error] " + e, "#ff6b6b"); running = false; }
  }

  function stopRun() {
    try { eel.claude_code_stop(); } catch (e) {}
    running = false; setStatus("stopped", "#ff6b6b");
    line("[stopped]", "#ff6b6b");
  }

  function renderEvent(ev) {
    if (!ev || typeof ev !== "object") { line(String(ev)); return; }
    var t = ev.type;
    if (t === "assistant" && ev.message && ev.message.content) {
      var parts = ev.message.content;
      for (var i = 0; i < parts.length; i++) {
        if (parts[i].type === "text") line(parts[i].text);
        else if (parts[i].type === "tool_use") line("⚙ " + parts[i].name + " " + JSON.stringify(parts[i].input || {}), "#a0e");
      }
    } else if (t === "result") {
      line("✔ " + (ev.result || ""), ev.is_error ? "#ff6b6b" : "#3ba55d");
    } else if (t === "system") {
      line("[system] " + (ev.subtype || ""), "#6b7c93");
    } else if (t === "raw") {
      line(ev.text || "");
    }
  }

  // Python -> JS: streamed payloads {kind:'event'|'done', ...}
  function onPayload(payload) {
    if (!payload) return;
    if (payload.kind === "event") renderEvent(payload.event);
    else if (payload.kind === "done") {
      running = false;
      var r = payload.result || {};
      setStatus(r.on_track ? "done ✓ on-track" : "done — review", r.on_track ? "#3ba55d" : "#ffd166");
      line("── " + (r.message || "done") + " ──", r.on_track ? "#3ba55d" : "#ffd166");
    }
  }
  eel.expose(onPayload, "claude_code_event");

  function toggle(force) {
    visible = typeof force === "boolean" ? force : !visible;
    if (!panel) build();
    panel.style.display = visible ? "flex" : "none";
    if (visible && input) input.focus();
  }

  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey && (e.key === "`" || e.key === "~")) { e.preventDefault(); toggle(); }
  });

  window.nexiClaudeTerminal = { toggle: toggle };
})();
