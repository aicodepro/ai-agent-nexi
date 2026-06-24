$(document).ready(function () {

    const STATE_LABELS = {
        sleeping: 'SLEEPING',
        idle: 'SLEEPING',
        online: 'ONLINE',
        listening: 'LISTENING',
        waiting_for_speech: 'LISTENING',
        transcribing: 'RECOGNISING',
        recognising: 'RECOGNISING',
        thinking: 'THINKING',
        speaking: 'SAYING',
        saying: 'SAYING',
        interrupted: 'Interrupted',
        error: 'ERROR'
    };

    function sourceLabel(source) {
        if (source === 'hotword') return 'Hotword';
        if (source === 'clap') return 'Clap';
        if (source === 'hotkey') return 'Hotkey';
        if (source === 'ui_button') return 'UI Button';
        if (source === 'ui') return 'Typed';
        if (source === 'tts') return 'TTS';
        if (source === 'tts_finished') return 'TTS';
        return 'Idle';
    }

    const ALLOWED_STATES = {
        sleeping: 'sleeping',
        idle: 'sleeping',
        sleep: 'sleeping',
        online: 'online',
        listening: 'listening',
        waiting_for_speech: 'listening',
        wake_detected: 'online',
        hearing_speech: 'listening',
        transcribing: 'recognising',
        recognising: 'recognising',
        thinking: 'thinking',
        speaking: 'saying',
        saying: 'saying',
        interrupted: 'interrupted',
        error: 'error'
    };

    function escapeHtml(text) {
        return String(text || '').replace(/[&<>"']/g, function (ch) {
            return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch];
        });
    }

    function renderInlineMarkdown(text) {
        return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    }

    function renderMarkdown(message) {
        const blocks = [];
        let text = String(message || '').replace(/```([\s\S]*?)```/g, function (_, code) {
            blocks.push('<pre><code>' + escapeHtml(code.trim()) + '</code></pre>');
            return '___CODE_BLOCK_' + (blocks.length - 1) + '___';
        });
        const lines = text.split(/\r?\n/);
        let html = '';
        let listOpen = false;
        lines.forEach(function (line) {
            const trimmed = line.trim();
            const item = /^([-*]|\d+[.)])\s+(.+)$/.exec(trimmed);
            if (item) {
                if (!listOpen) {
                    html += '<ul>';
                    listOpen = true;
                }
                html += '<li>' + renderInlineMarkdown(item[2]) + '</li>';
                return;
            }
            if (listOpen) {
                html += '</ul>';
                listOpen = false;
            }
            if (!trimmed) html += '<br>';
            else if (/^___CODE_BLOCK_\d+___$/.test(trimmed)) html += trimmed;
            else html += '<p>' + renderInlineMarkdown(trimmed) + '</p>';
        });
        if (listOpen) html += '</ul>';
        blocks.forEach(function (block, index) {
            html = html.replace('___CODE_BLOCK_' + index + '___', block);
        });
        return html;
    }

    function lastWords(text, count) {
        const words = String(text || '').match(/[\w']+/g) || [];
        return words.slice(-Math.max(1, count || 2)).join(' ');
    }

    eel.expose(updateSpeechCapsule)
    function updateSpeechCapsule(words) {
        const capsule = document.getElementById('SpeechCapsule');
        const value = lastWords(words, 2);
        if (!capsule || !value) return;
        capsule.textContent = value;
        capsule.className = 'speech-capsule';
        console.log('[UI] speech_capsule_updated words=' + value.split(/\s+/).filter(Boolean).length);
    }

    eel.expose(hideSpeechCapsule)
    function hideSpeechCapsule() {
        const capsule = document.getElementById('SpeechCapsule');
        if (capsule) capsule.className = 'speech-capsule hidden';
    }

    eel.expose(setContextIndicator)
    function setContextIndicator(active) {
        const indicator = document.getElementById('ContextIndicator');
        if (indicator) indicator.className = active ? 'context-indicator' : 'context-indicator hidden';
    }

    function updateNexiState(payload) {
        if (typeof payload === 'string') {
            try {
                payload = JSON.parse(payload);
            } catch (e) {
                payload = { state: 'error', text: 'Invalid UI state payload' };
            }
        }
        payload = payload || {};
        const requestedState = payload.state || 'idle';
        const state = ALLOWED_STATES[requestedState] || 'idle';
        const source = payload.source || 'system';
        const text = payload.text || '';
        const label = document.getElementById('StatusLabel');
        const badge = document.getElementById('SourceBadge');
        const preview = document.getElementById('TranscriptPreview');
        const hood = document.getElementById('NexiHood');
        const bars = document.getElementById('WaveformBars');
        const sleepWakeBtn = document.getElementById('SleepWakeBtn');

        if (window.__nexiUiState && window.__nexiUiState !== state) {
            console.log('[UI_STATE] conflict_resolved previous=' + window.__nexiUiState + ' next=' + state);
        }
        window.__nexiUiState = state;
        if (payload.presence) {
            updatePresence(payload.presence);
        }
        if (label) {
            label.textContent = text && state === 'error' ? text : (STATE_LABELS[state] || payload.status || state);
            label.className = 'text-light text-center status-label ' + state;
        }
        if (badge) {
            badge.textContent = state.toUpperCase();
            badge.className = 'source-badge state-' + state;
        }
        if (preview) {
            if (text && state !== 'error') {
                preview.textContent = text;
            } else if (state === 'sleeping') {
                preview.textContent = 'Say Hey Nexi, double clap, or press Win+J';
            } else if (state === 'idle') {
                preview.textContent = 'Waiting for wake word...';
            }
        }
        if (hood) {
            hood.className = 'nexi-state-' + state;
        }
        if (bars) {
            bars.className = 'waveform-bars' + (['listening', 'online', 'recognising', 'transcribing'].includes(state) ? ' active' : '');
        }
        if (state !== 'saying' && state !== 'speaking') {
            hideSpeechCapsule();
        }
        if (sleepWakeBtn) {
            sleepWakeBtn.title = state === 'sleeping' ? 'Wake Nexi' : 'Put Nexi to sleep';
        }
        if (source === 'hotkey' && (state === 'wake_detected' || state === 'listening')) {
            window.focus();
        }
        console.log('[UI_STATE] set=' + state + ' source=' + source);
    }

    window.updateNexiState = updateNexiState;
    eel.expose(updateNexiState)

    function updatePresence(payload) {
        if (typeof payload === 'string') {
            try { payload = JSON.parse(payload); } catch (e) { payload = {}; }
        }
        payload = payload || {};
        var attention = document.getElementById('PresenceAttention');
        var goal = document.getElementById('PresenceGoal');
        var confidence = document.getElementById('PresenceConfidence');
        if (attention) attention.textContent = String(payload.attention || 'none').toUpperCase();
        if (goal) goal.textContent = String(payload.current_goal || 'waiting for wake word').toUpperCase().slice(0, 120);
        if (confidence) confidence.textContent = Math.round(Number(payload.confidence || 0) * 100) + '%';
    }

    window.updatePresence = updatePresence;
    eel.expose(updatePresence)

    function updateTranscript(payload) {
        if (typeof payload === 'string') {
            try { payload = JSON.parse(payload); } catch (e) { payload = {}; }
        }
        payload = payload || {};
        var userText = String(payload.user_text || '');
        var nexiText = String(payload.nexi_text || '');
        var meta = payload.metadata || {};
        if (userText) senderText(userText);
        if (nexiText) receiverText(nexiText);
        var userEl = document.getElementById('UserText');
        var nexiEl = document.getElementById('NexiText');
        var metaEl = document.getElementById('ResponseMeta');
        if (userEl && userText) userEl.textContent = userText.slice(0, 300);
        if (nexiEl && nexiText) nexiEl.textContent = nexiText.slice(0, 400);
        if (metaEl) {
            var parts = [];
            if (meta.route) parts.push('Route: ' + escapeHtml(meta.route));
            if (meta.provider) parts.push('Provider: ' + escapeHtml(meta.provider));
            if (meta.intent) parts.push('Intent: ' + escapeHtml(meta.intent));
            if (meta.latency_ms) parts.push('Latency: ' + (Number(meta.latency_ms) / 1000).toFixed(1) + 's');
            metaEl.innerHTML = parts.join(' | ');
        }
    }

    window.updateTranscript = updateTranscript;
    eel.expose(updateTranscript)

    function renderDashboard(payload) {
        if (typeof payload === 'string') {
            try { payload = JSON.parse(payload); } catch (e) { payload = {}; }
        }
        payload = payload || {};
        var panels = payload.panels || [];
        var summary = document.getElementById('dashboard-summary');
        var target = document.getElementById('dashboard-panels');
        if (summary) summary.textContent = panels.length ? panels.length + ' panels updated' : 'Dashboard unavailable';
        if (target) target.innerHTML = panels.slice(0, 8).map(function (panel) {
            return '<div class="dashboard-panel"><strong>' + escapeHtml(panel.title || panel.id) + '</strong></div>';
        }).join('');
    }

    function updateDashboard(payload) {
        renderDashboard(payload);
    }

    function diagnosticsResult(payload) {
        renderDashboard(payload);
    }

    window.updateDashboard = updateDashboard;
    window.diagnosticsResult = diagnosticsResult;
    eel.expose(updateDashboard)
    eel.expose(diagnosticsResult)

    // Display Speak Message
    eel.expose(DisplayMessage)
    function DisplayMessage(message) {
        updateNexiState({ state: 'speaking', source: 'tts', text: lastWords(message, 2) });
        updateSpeechCapsule(message);
        $(".siri-message li:first").text(lastWords(message, 2));
        $('.siri-message').textillate('start');
        setStatus("Speaking...", "speaking");
    }

    // Display hood
    eel.expose(ShowHood)
    function ShowHood() {
        $("#Oval").attr("hidden", false);
        $("#SiriWave").attr("hidden", true);
        if (!['listening', 'transcribing', 'thinking', 'speaking'].includes(window.__nexiUiState)) {
            updateNexiState({ state: 'idle', source: 'ready' });
        }
    }

    // Functions to handle chat messages
    eel.expose(senderText)
    function senderText(message) {
        var chatBox = document.getElementById("chat-canvas-body");
        if (message.trim() !== "") {
            var hint = chatBox.querySelector('.chat-idle-card');
            if (hint) hint.remove();
            chatBox.innerHTML += `<div class="row justify-content-end mb-4">
            <div class = "width-size">
            <div class="sender_message message user">${escapeHtml(message)}</div>
        </div>`; 
    
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    }

    eel.expose(appendLog)
    function appendLog(level, message) {
        var safeLevel = String(level || 'sys').toLowerCase();
        var safeMessage = String(message || '');
        if (safeLevel === 'you') {
            senderText(safeMessage.replace(/^You:\s*/i, ''));
            return;
        }
        if (safeLevel === 'ai') {
            receiverText(safeMessage.replace(/^NEXI:\s*/i, ''));
            return;
        }
        var chatBox = document.getElementById("chat-canvas-body");
        if (chatBox && safeMessage.trim() !== "") {
            var hint = chatBox.querySelector('.chat-idle-card');
            if (hint) hint.remove();
            chatBox.innerHTML += `<div class="row justify-content-start mb-2"><div class="width-size"><div class="receiver_message message system">${escapeHtml(safeMessage)}</div></div></div>`;
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    }

    eel.expose(receiverText)
    function receiverText(message) {
        var chatBox = document.getElementById("chat-canvas-body");
        if (message.trim() !== "") {
            var hint = chatBox.querySelector('.chat-idle-card');
            if (hint) hint.remove();
            var safeMessage = message;
            var extra = "";
            if (message.length > 1200) {
                safeMessage = message.slice(0, 1200) + "...";
                extra = `<button class="btn btn-sm btn-outline-info mt-2 show-more-response" type="button">Show more</button>`;
            }
            chatBox.innerHTML += `<div class="row justify-content-start mb-4">
            <div class = "width-size">
            <div class="receiver_message message assistant">${renderMarkdown(safeMessage)}</div>${extra}
            </div>
        </div>`; 
            if (extra) {
                var buttons = chatBox.getElementsByClassName("show-more-response");
                var button = buttons[buttons.length - 1];
                var fullMessage = message;
                if (button) {
                    button.addEventListener("click", function () {
                        var expanded = this.getAttribute("data-expanded") === "true";
                        this.previousElementSibling.innerHTML = renderMarkdown(expanded ? fullMessage.slice(0, 1200) + "..." : fullMessage);
                        this.textContent = expanded ? "Show more" : "Show less";
                        this.setAttribute("data-expanded", expanded ? "false" : "true");
                    });
                }
            }
    
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    }

    // Set status label
    eel.expose(setStatus)
    function setStatus(statusText, className) {
        var label = document.getElementById("StatusLabel");
        if (label) {
            label.textContent = statusText;
            label.className = "text-light text-center status-label" + (className ? " " + className : "");
        }
    }

    // Computer Control bridge functions
    eel.expose(displayControlResult)
    function displayControlResult(message) {
        console.log("Control:", message);
        $(".siri-message li:first").text(message);
        $('.siri-message').textillate('start');
    }

    eel.expose(showEmergencyStop)
    function showEmergencyStop(reason) {
        console.warn("EMERGENCY STOP:", reason);
        $("#Oval").attr("hidden", true);
        $("#SiriWave").attr("hidden", false);
        $(".siri-message li:first").text("EMERGENCY STOP: " + reason);
        $('.siri-message').textillate('start');
    }

    window.__nexiRenderMarkdown = renderMarkdown;
    window.__nexiLastWords = lastWords;

    function setWorkspaceStatus(text) {
        const status = document.getElementById('OutputWorkspaceStatus');
        if (status) status.textContent = text || 'Ready';
    }

    eel.expose(showOutputWorkspace)
    function showOutputWorkspace(payload) {
        if (typeof payload === 'string') {
            try { payload = JSON.parse(payload); } catch (e) { payload = {}; }
        }
        payload = payload || {};
        const panel = document.getElementById('NexiOutputWorkspace');
        if (!panel) return;
        const type = document.getElementById('OutputWorkspaceType');
        const summary = document.getElementById('OutputWorkspaceSummary');
        const content = document.getElementById('OutputWorkspaceContent');
        if (type) type.textContent = payload.workspace_type || 'Text';
        if (summary) summary.textContent = payload.workspace_summary || '';
        if (content) content.innerHTML = renderMarkdown(payload.workspace_content || payload.main_ui_text || '');
        panel.className = 'nexi-output-workspace';
        setWorkspaceStatus('Ready');
        localStorage.setItem('nexi_latest_workspace', JSON.stringify(payload));
    }

    eel.expose(closeOutputWorkspace)
    function closeOutputWorkspace() {
        const panel = document.getElementById('NexiOutputWorkspace');
        if (panel) panel.className = 'nexi-output-workspace hidden';
    }

    eel.expose(minimizeOutputWorkspace)
    function minimizeOutputWorkspace() {
        const panel = document.getElementById('NexiOutputWorkspace');
        if (panel) panel.classList.toggle('minimized');
    }

    eel.expose(pinOutputWorkspace)
    function pinOutputWorkspace() {
        const panel = document.getElementById('NexiOutputWorkspace');
        if (panel) panel.classList.toggle('pinned');
        setWorkspaceStatus('Pinned');
    }

    function workspaceText() {
        const content = document.getElementById('OutputWorkspaceContent');
        return content ? content.innerText : '';
    }

    const copyBtn = document.getElementById('WorkspaceCopyBtn');
    if (copyBtn) copyBtn.addEventListener('click', function () {
        navigator.clipboard.writeText(workspaceText()).then(function () { setWorkspaceStatus('Copied'); }).catch(function () { setWorkspaceStatus('Copy failed'); });
    });

    ['WorkspaceCreateFileBtn', 'WorkspaceSaveMdBtn', 'WorkspaceSaveTxtBtn'].forEach(function (id) {
        const btn = document.getElementById(id);
        if (btn) btn.addEventListener('click', function () { setWorkspaceStatus('Ask Nexi: create a file'); });
    });

    const minBtn = document.getElementById('OutputMinimizeBtn');
    if (minBtn) minBtn.addEventListener('click', minimizeOutputWorkspace);
    const pinBtn = document.getElementById('OutputPinBtn');
    if (pinBtn) pinBtn.addEventListener('click', pinOutputWorkspace);
    const closeBtn = document.getElementById('OutputCloseBtn');
    if (closeBtn) closeBtn.addEventListener('click', closeOutputWorkspace);

    (function makeWorkspaceDraggable() {
        const panel = document.getElementById('NexiOutputWorkspace');
        const header = document.getElementById('OutputWorkspaceHeader');
        if (!panel || !header) return;
        const saved = localStorage.getItem('nexi_workspace_position');
        if (saved) {
            try {
                const pos = JSON.parse(saved);
                panel.style.left = pos.left;
                panel.style.top = pos.top;
                panel.style.right = 'auto';
                panel.style.bottom = 'auto';
            } catch (e) {}
        }
        let dragging = false;
        let dx = 0;
        let dy = 0;
        header.addEventListener('mousedown', function (event) {
            dragging = true;
            const rect = panel.getBoundingClientRect();
            dx = event.clientX - rect.left;
            dy = event.clientY - rect.top;
        });
        document.addEventListener('mousemove', function (event) {
            if (!dragging) return;
            panel.style.left = Math.max(8, event.clientX - dx) + 'px';
            panel.style.top = Math.max(8, event.clientY - dy) + 'px';
            panel.style.right = 'auto';
            panel.style.bottom = 'auto';
        });
        document.addEventListener('mouseup', function () {
            if (!dragging) return;
            dragging = false;
            localStorage.setItem('nexi_workspace_position', JSON.stringify({ left: panel.style.left, top: panel.style.top }));
        });
    })();

});
