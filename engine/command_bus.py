from __future__ import annotations

import re
import threading

_local = threading.local()

_SYSTEM_CONTROL_COMMANDS = {
    "sleep",
    "go to sleep",
    "stop listening",
    "wake up",
    "activate nexi",
}


def normalize_command(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def is_dispatching() -> bool:
    return bool(getattr(_local, "dispatching", False))


def current_source() -> str:
    return getattr(_local, "source", "ui")


def _is_system_control_command(text: str) -> bool:
    return (text or "").strip().lower().rstrip(".?!") in _SYSTEM_CONTROL_COMMANDS


def submit_user_command(text: str, source: str = "ui", mode: str = "typed") -> bool:
    source = (source or "ui").strip() or "ui"
    mode = (mode or "typed").strip() or "typed"
    preview = normalize_command(text)[:80]
    print(f"[COMMAND_BUS] received source={source} text={preview}", flush=True)

    # ── Voice command gate ──────────────────────────────────────────────────
    # Full voice commands are accepted only in LISTENING / RECORDING_UTTERANCE.
    # During SPEAKING, only interrupt words (stop/pause/cancel/sleep) pass — and
    # they trigger a TTS interrupt rather than a new command. Typed UI commands
    # are never gated. This prevents recognition/thinking/speaking from spawning
    # accidental second commands and stops Nexi hearing its own voice.
    if mode == "voice":
        try:
            from engine.voice_state_machine import get_voice_state_machine
            import engine.voice_state_machine as _vsm_mod
            vsm = get_voice_state_machine()
            state = vsm.get_state()
            if state == _vsm_mod.SPEAKING:
                try:
                    from engine.interrupt_controller import is_speaking as _is_tts_speaking
                    from engine.wake_session_manager import is_session_active
                    if (not _is_tts_speaking()) or (not is_session_active()):
                        vsm.transition("session_finish", source="stale_speaking_gate")
                        state = vsm.get_state()
                except Exception:
                    pass
            if state == _vsm_mod.SPEAKING:
                if vsm.is_hotword_text(text):
                    print(f"[VOICE_STATE] hotword_barge_in_accepted source={source}", flush=True)
                    from engine.barge_in_manager import interrupt
                    result = interrupt(source=source, reason="hotword_barge_in")
                    vsm.record_interruption("hotword_barge_in")
                    try:
                        from engine.post_tts_cleanup import flush_audio_buffers, reset_cooldown
                        flush_audio_buffers()
                        reset_cooldown()
                    except Exception:
                        pass
                    try:
                        from engine.ui_state_manager import emit_state
                        emit_state("listening", source=source, text="Interrupted — Listening", status="interrupted", force=True)
                    except Exception:
                        pass
                    try:
                        vsm.transition(_vsm_mod.TTS_INTERRUPTED_BY_HOTWORD, source=source)
                        vsm.transition(_vsm_mod.BARGE_IN_LISTENING_STARTED, source=source)
                    except Exception:
                        pass
                    return bool(getattr(result, "interrupted", True))
                if vsm.is_interrupt_word(text):
                    print(f"[VOICE_STATE] interrupt_word_accepted source={source}", flush=True)
                    from engine.interrupt_controller import request_interrupt, clear_interrupt
                    reason = "sleep" if normalize_command(text).lower().rstrip(".?!") == "sleep" else "interrupt_word"
                    request_interrupt(source=source, reason=reason)
                    vsm.record_interruption(reason)
                    try:
                        from engine.post_tts_cleanup import flush_audio_buffers
                        flush_audio_buffers()
                    except Exception:
                        pass
                    if reason == "sleep":
                        try:
                            from engine.nexi_wake_controller import sleep_nexi
                            sleep_nexi(reason="interrupt_word")
                        except Exception:
                            pass
                        vsm.transition("sleep", source=source)
                    else:
                        vsm.transition("interrupted", source=source)
                    clear_interrupt()
                    return True
                vsm.record_ignored_voice_event("speaking_without_hotword_or_interrupt")
                print(f"[VOICE_STATE] command_ignored state=SPEAKING source={source}", flush=True)
                return False
            if state == _vsm_mod.COOLDOWN:
                active_cooldown = False
                try:
                    from engine.post_tts_cleanup import is_in_cooldown
                    active_cooldown = bool(is_in_cooldown())
                except Exception:
                    active_cooldown = False
                try:
                    from engine.wake_session_manager import is_session_active
                    active_cooldown = active_cooldown or bool(is_session_active())
                except Exception:
                    pass
                if not active_cooldown:
                    vsm.transition("session_finish", source="stale_cooldown_gate")
                    state = vsm.get_state()
                else:
                    vsm.record_ignored_voice_event(f"state={state}")
                    print(f"[VOICE_STATE] command_ignored state={state} source={source}", flush=True)
                    return False
            if state == _vsm_mod.COOLDOWN:
                vsm.record_ignored_voice_event(f"state={state}")
                print(f"[VOICE_STATE] command_ignored state={state} source={source}", flush=True)
                return False
        except Exception:
            pass

    try:
        from engine.turn_manager import mark_user_turn_started
        mark_user_turn_started(source)
    except Exception:
        pass
    try:
        from engine.conversation_context import add_user_turn
        add_user_turn(text, source)
    except Exception:
        pass
    try:
        # Autonomous short-term memory — final user transcript only (no partials).
        from engine.autonomous_memory import add_user_message
        add_user_message(text, source=source)
    except Exception:
        pass
    try:
        from engine.memory.session_memory import add_user_turn as add_session_user_turn
        add_session_user_turn(text, source)
    except Exception:
        pass
    try:
        from engine.adaptive_memory import learn_from_user_text
        learn_from_user_text(text, source=source)
    except Exception:
        pass
    try:
        from engine.voice_state_machine import get_voice_state_machine
        get_voice_state_machine().record_transcript(text)
    except Exception:
        pass

    # ── Post‑TTS cooldown & audio flush ────────────────────────────────────────
    try:
        from engine.post_tts_cleanup import post_tts_cleanup
        # post_tts_cleanup() is called by tts_provider_manager after each TTS,
        # but we can invoke it here as well to ensure the state machine is
        # synchronized after a voice command ends.
        if source in {"hotword", "clap", "double_clap", "hotkey"} and not source.startswith("ui"):
            # For voice commands, trigger a cleanup after the command bus
            # processes the command (it runs synchronously here, but this ensures
            # the cooldown starts after any TTS from the previous interaction).
            # We add this to the pending queue to avoid blocking command dispatch.
            import threading
            def _start_cooldown():
                try:
                    post_tts_cleanup()
                except Exception:
                    pass
            threading.Thread(target=_start_cooldown, daemon=True, name="post-tts-trigger").start()
    except Exception:
        pass

    from engine.interrupt_controller import is_speaking, request_interrupt, clear_interrupt
    if is_speaking():
        print(f"[COMMAND_BUS] interrupt_before_new_command source={source}", flush=True)
        request_interrupt(source=source, reason="new_command")
        try:
            from engine.turn_manager import request_interrupt as turn_interrupt
            turn_interrupt(source=source, reason="new_command")
        except Exception:
            pass
        clear_interrupt()

    normalized = normalize_command(text)
    original_normalized = normalized
    system_control_command = _is_system_control_command(normalized)
    pending_clarification = False
    pending_followup = False
    pending_short_answer = False
    try:
        from engine.clarification_manager import has_pending_clarification
        pending_clarification = has_pending_clarification()
    except Exception:
        pending_clarification = False
    try:
        from engine.followup_manager import has_pending_followup
        pending_followup = has_pending_followup()
    except Exception:
        pending_followup = False
    if pending_clarification:
        print("[CLARIFY] pending=true bypass_transcript_filter=true", flush=True)
    if pending_followup:
        print("[FOLLOWUP] pending=true bypass_transcript_filter=true", flush=True)
    if system_control_command and (pending_clarification or pending_followup):
        try:
            from engine.clarification_manager import clear_clarification
            clear_clarification("system_command")
        except Exception:
            pass
        try:
            from engine.followup_manager import clear_followup
            clear_followup("system_command")
        except Exception:
            pass
        pending_clarification = False
        pending_followup = False
        print("[COMMAND_BUS] pending_cleared reason=system_command", flush=True)
    if pending_clarification or pending_followup:
        try:
            from engine.transcript_filter import accepts_pending_followup_answer
            pending_short_answer = accepts_pending_followup_answer(original_normalized)
            if pending_short_answer:
                print("[TRANSCRIPT] accepted reason=pending_followup_short_answer", flush=True)
        except Exception:
            pending_short_answer = bool(original_normalized)
    try:
        from engine.followup_manager import consume_followup_answer
        followup = consume_followup_answer(normalized, source)
        if pending_clarification and (followup.get("handled") or followup.get("cancelled")):
            try:
                from engine.clarification_manager import receive_answer
                receive_answer(original_normalized, followup.get("followup_type"))
            except Exception:
                pass
        if followup.get("cancelled"):
            normalized = "cancel"
        elif followup.get("handled"):
            normalized = normalize_command(followup.get("text", normalized))
    except Exception:
        pass
    print(f"[COMMAND_BUS] normalized={normalized[:80]}", flush=True)
    if not normalized:
        return False

    try:
        from engine.realtime_cognitive_engine import analyze_input
        analyze_input(normalized, source=source, metadata={"mode": mode})
    except Exception as e:
        print(f"[COGNITIVE] analysis_failed reason={type(e).__name__}", flush=True)
    try:
        from engine.user_model import infer_user_preference, update_user_model
        preference = infer_user_preference(original_normalized or normalized)
        if preference:
            update_user_model(preference)
    except Exception:
        pass

    try:
        if _try_output_action(normalized):
            return True
    except Exception as e:
        print(f"[COMMAND_BUS] output_action_failed reason={type(e).__name__}", flush=True)

    active_workflow = False
    try:
        from engine.workflow_state import has_active_workflow
        active_workflow = has_active_workflow()
    except Exception:
        active_workflow = False
    if (mode == "voice" or source in {"hotword", "clap", "double_clap", "hotkey", "ui_button", "mic_button", "voice"}) and not active_workflow:
        from engine.transcript_filter import clean_transcript, is_gibberish_or_wrong_language
        normalized = clean_transcript(normalized)
        if not pending_short_answer and is_gibberish_or_wrong_language(normalized):
            print(f"[TRANSCRIPT] rejected reason=non_english_or_gibberish preview={normalized[:40]}", flush=True)
            print("[VOICE] clarification_requested", flush=True)
            from engine.clarification_manager import ask_clarification
            from engine.command import speak
            response = ask_clarification(normalized, reason="clarification")
            speak(response["display_text"])
            return False

    dispatch_unified_command(normalized, source=source)
    return True


def _try_output_action(text: str) -> bool:
    q = (text or "").strip().lower().rstrip(".?!")
    if q not in {"copy it", "copy this", "create a file", "create file", "open the box", "show it again", "close the box", "minimize the box", "pin the box", "make it shorter", "regenerate it"} and not q.startswith("save it as "):
        return False
    if q in {"create a file", "create file"}:
        try:
            from engine.output_actions import get_latest_output
            if not get_latest_output().get("content"):
                return False
        except Exception:
            return False
    from engine.command import _handle_output_command
    return bool(_handle_output_command(text))


def dispatch_unified_command(text: str, source: str) -> None:
    print(f"[COMMAND_BUS] dispatch_started source={source}", flush=True)
    previous_dispatching = is_dispatching()
    previous_source = current_source()
    _local.dispatching = True
    _local.source = source
    try:
        from engine.command import allCommands
        allCommands(text)
    finally:
        _local.dispatching = previous_dispatching
        _local.source = previous_source
        print(f"[COMMAND_BUS] dispatch_finished source={source}", flush=True)
