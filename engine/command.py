# command.py
import sys
import os
import json
_src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from dotenv import load_dotenv
load_dotenv()

import keyboard
import pyperclip as pi
import threading
import webbrowser
import pyttsx3
import speech_recognition as sr
import eel
import time
import requests
import pyautogui
import tempfile
import uuid
from bs4 import BeautifulSoup
from typing import Union
from os import getcwd
from engine.keyboard import (
    volumeup, volumedown, open_new_tab, close_tab, open_browser_menu, zoom_in, zoom_out, refresh_page,
    switch_to_next_tab, switch_to_previous_tab, open_history, open_bookmarks, go_back, go_forward,
    open_dev_tools, toggle_full_screen, open_private_window, minimize_window, chrome_task_manager, search_google
)
from engine.SendEmail import send_email  # Ensure this is correctly imported
from engine.GoogleMaps import get_places_info  # Import your function
from engine.file_operations import create_folder_and_files  # Import from file_operations

def is_online(url="https://www.google.com", timeout=5):
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code >= 200 and response.status_code < 300
    except requests.ConnectionError:
        return False
    except requests.Timeout:
        return False
    except Exception as e:
        print(f"Error in is_online function: {e}")
        return False

def generate_audio(message: str, voice: str = "Aditi"):
    url = "https://api.streamelements.com/kappa/v2/speech"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}
    try:
        result = requests.get(url=url, headers=headers, params={"voice": voice, "text": message}, timeout=10)
        result.raise_for_status()
        content_type = result.headers.get("content-type", "").lower()
        if not result.content or "audio" not in content_type:
            raise ValueError(f"Unexpected TTS response: {content_type or 'unknown content type'}")
        return result.content
    except Exception as e:
        print(f"Error generating audio: {e}")
        return None


def safe_eel_call(function_name, *args):
    try:
        fn = getattr(eel, function_name)
    except AttributeError:
        print(f"[EEL] missing_js_function name={function_name}")
        return False
    try:
        fn(*args)
        return True
    except Exception as e:
        print(f"[EEL] js_call_failed name={function_name} reason={type(e).__name__}")
        return False

def _env_bool(key: str, default: bool = False) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


_current_ui_state = "idle"


def _set_ui_state(state: str, source: str = "system", text: str = "") -> None:
    global _current_ui_state
    try:
        from engine.ui_state_manager import canonical_state, emit_state
        from engine.runtime_bridge import current_bridge_session_epoch, current_bridge_session_id
        normalized_state = canonical_state(state)
        emit_state(
            normalized_state,
            source=source,
            text=text,
            status=state,
            session_id=current_bridge_session_id(),
            session_epoch=current_bridge_session_epoch(),
        )
    except Exception:
        allowed = {"sleep", "listening", "recognising", "thinking", "saying", "error"}
        normalized_state = state if state in allowed else ("listening" if state in {"wake_detected", "hearing_speech"} else "sleep")
        payload = {"state": normalized_state, "source": source, "text": (text or "")[:120], "status": normalized_state}
        safe_eel_call("updateNexiState", json.dumps(payload))
    if _current_ui_state and _current_ui_state != normalized_state:
        print(f"[UI_STATE] conflict_resolved previous={_current_ui_state} next={normalized_state}", flush=True)
    _current_ui_state = normalized_state
    print(f"[UI_STATE] set={normalized_state} source={source}", flush=True)


_last_handler_reason: str = ""


def _split_tts_chunks(text: str, max_chars: int = 260) -> list[str]:
    from engine.tts_response_manager import split_tts_chunks
    return split_tts_chunks(text, max_chars=max_chars)


def _short_voice_summary(text: str, limit: int = 700) -> str:
    from engine.tts_response_manager import build_spoken_text
    return build_spoken_text(text, max_chars=limit)


def _prepare_tts_texts(text: str) -> tuple[str, str]:
    original_text = str(text or "")
    display_text = original_text
    max_chars = _env_int("TTS_SUMMARY_MAX_CHARS", 700)
    voice_text = _short_voice_summary(display_text, max_chars)
    try:
        from engine.output_router import route_assistant_output
        from engine.output_actions import set_latest_output
        route = route_assistant_output(display_text, voice_text)
        if route.get("show_workspace"):
            output = set_latest_output(
                route.get("workspace_content", display_text),
                route.get("workspace_title", "Nexi Output"),
                route.get("workspace_type", "text"),
                route.get("workspace_summary", ""),
            )
            safe_eel_call("showOutputWorkspace", json.dumps({**route, "output_id": output.get("id", "")}))
            display_text = route.get("main_ui_text", display_text)
            voice_text = route.get("spoken_text", voice_text)
            print("[TTS] workspace_summary_mode=true", flush=True)
    except Exception as e:
        print(f"[OUTPUT] route_failed reason={type(e).__name__}", flush=True)
    print(f"[TTS] display_len={len(display_text)}", flush=True)
    print(f"[TTS] spoken_len={len(voice_text)}", flush=True)
    print(f"[TTS] summary_mode={str(len(original_text) > max_chars).lower()}", flush=True)
    return display_text, voice_text


def _update_speech_capsule(text: str) -> None:
    try:
        from engine.speech_progress import get_last_spoken_words
        words = get_last_spoken_words(text, 2)
        print(f'[SPEECH] progress last_words="{words}"', flush=True)
        safe_eel_call("updateSpeechCapsule", words)
    except Exception:
        pass


def _followup_source() -> str:
    try:
        from engine.command_bus import current_source
        return current_source()
    except Exception:
        return "assistant"


def _mark_question_response(text: str, source: str | None = None, handler_reason: str = "") -> bool:
    global _last_handler_reason
    if handler_reason:
        _last_handler_reason = handler_reason
    try:
        from engine.demo_mode import DemoMode
        if DemoMode.should_suppress_followup():
            print("[DEMO] auto_followup_suppressed=true", flush=True)
            return False
    except Exception:
        pass
    if _last_handler_reason in {"tool", "output", "system", "react"}:
        return False
    try:
        from engine.assistant_response import make_response
        response = make_response(text, source=source or _followup_source())
        if not response["expects_user_reply"]:
            return False
        try:
            from engine.followup_manager import has_pending_followup, set_pending_followup
            if not has_pending_followup():
                set_pending_followup(
                    response["followup_question"],
                    response["followup_type"],
                    response["source"],
                )
        except Exception:
            pass
        print(f"[ASSISTANT] question_detected source={response['source']}", flush=True)
        try:
            from engine.turn_manager import mark_waiting_for_user
            mark_waiting_for_user(
                response["followup_question"],
                reason="assistant_question",
                workflow_id=response["followup_type"],
            )
        except Exception:
            pass
        return True
    except Exception:
        return False


def speak_streamelements(message: str, voice: str = "Aditi", folder: str = "", extension: str = ".mp3", display_message: str | None = None) -> Union[None, str]:
    file_path = None
    try:
        shown = display_message if display_message is not None else message
        safe_eel_call("DisplayMessage", shown)
        
        result_content = generate_audio(message, voice)
        if result_content is None:
            raise ValueError("Failed to generate audio from the API.")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension, dir=folder or None) as file:
            file_path = file.name
            file.write(result_content)
        from playsound import playsound as ps
        ps(file_path)
        
        safe_eel_call("receiverText", shown)
        return None
    except Exception as e:
        print(f"Error in speak_streamelements: {e}")
        return str(e)
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass

def speak_pyttsx3(text, display_text=None, start_generation=None):
    text = str(text)
    shown = str(display_text if display_text is not None else text)
    try:
        import ctypes
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass
    engine = pyttsx3.init('sapi5')
    try:
        from engine.interrupt_controller import set_tts_engine
        set_tts_engine(engine)
    except Exception:
        pass
    voices = engine.getProperty('voices')
    voice_id = voices[0].id
    for v in voices:
        vl = (v.name or "").lower()
        if "zira" in vl or "natural" in vl or "neural" in vl:
            voice_id = v.id
            break
    engine.setProperty('voice', voice_id)
    engine.setProperty('rate', 160)
    safe_eel_call("DisplayMessage", shown)
    safe_eel_call("receiverText", shown)
    try:
        from engine.interrupt_controller import should_interrupt, get_interrupt_generation, get_interrupt_source
        chunks = _split_tts_chunks(text) if _env_bool("TTS_CHUNKED_SPEAKING", True) else [text]
        generation = get_interrupt_generation() if start_generation is None else start_generation
        for chunk in chunks:
            if should_interrupt() or get_interrupt_generation() != generation:
                print(f"[TTS] interrupted source={get_interrupt_source() or 'unknown'}", flush=True)
                break
            _update_speech_capsule(chunk)
            engine.say(chunk)
            engine.runAndWait()
            if should_interrupt() or get_interrupt_generation() != generation:
                print(f"[TTS] interrupted source={get_interrupt_source() or 'unknown'}", flush=True)
                break
    finally:
        try:
            from engine.interrupt_controller import set_tts_engine
            set_tts_engine(None)
        except Exception:
            pass

def speak(text, voice="Matthew", *, handler_reason: str = ""):
    global _last_spoken
    spoken_override = None
    if isinstance(text, dict):
        spoken_override = text.get("spoken_text")
        text = text.get("display_text", "")
    display_text, voice_text = _prepare_tts_texts(text)
    if spoken_override:
        voice_text = str(spoken_override)
    try:
        from engine.command_bus import current_request_id, current_source

        request_id = current_request_id()
        if request_id:
            from engine.response_coordinator import get_response_coordinator
            from engine.runtime_bridge import current_bridge_session_epoch, current_bridge_session_id

            receipt = get_response_coordinator().accept(
                display_text,
                spoken_text=voice_text,
                request_id=request_id,
                session_id=current_bridge_session_id(),
                session_epoch=current_bridge_session_epoch(),
                source=current_source(),
                metadata={"handler_reason": handler_reason},
            )
            if not receipt.accepted:
                print(f"[RESPONSE] suppressed reason={receipt.reason} request={request_id}", flush=True)
                return
            display_text = str(receipt.response.get("display_text") or "")
            voice_text = str(receipt.response.get("spoken_text") or display_text)
    except Exception as exc:
        print(f"[RESPONSE] coordinator_failed reason={type(exc).__name__}", flush=True)
    tone_config = None
    try:
        from engine.tone_manager import ToneManager, tone_for_reason
        tone_config = tone_for_reason(handler_reason)
        display_text = ToneManager.wrap_response(display_text, tone_config)
        voice_text = ToneManager.apply_tts_style(ToneManager.wrap_response(voice_text, tone_config), tone_config)
    except Exception:
        pass
    _last_spoken = display_text
    try:
        safe_eel_call("updateTranscript", json.dumps({
            "nexi_text": display_text[:300],
            "metadata": {
                "route": (handler_reason or "unknown").strip()[:60],
                "intent": "response",
                "provider": "nexi",
            }
        }))
    except Exception:
        pass
    print(f"[TTS] requested text_len={len(display_text)}", flush=True)
    enabled = _env_bool("TTS_ENABLED", True)
    print(f"[TTS] enabled={str(enabled).lower()}", flush=True)
    expects_followup = _mark_question_response(display_text, handler_reason=handler_reason)
    try:
        from engine.turn_manager import should_auto_listen
        expects_followup = expects_followup or should_auto_listen()
    except Exception:
        pass
    from engine.interrupt_controller import set_speaking, should_interrupt, clear_interrupt, get_interrupt_source, get_interrupt_generation
    if should_interrupt():
        print(f"[TTS] interrupted source={get_interrupt_source() or 'unknown'}", flush=True)
        clear_interrupt()
        return
    if not enabled:
        print("[TTS] disabled", flush=True)
        safe_eel_call("receiverText", display_text)
        try:
            from engine.runtime_bridge import current_bridge_session_id
            disabled_voice_session = current_bridge_session_id()
        except Exception:
            disabled_voice_session = ""
        if expects_followup:
            _maybe_start_auto_followup()
        elif not disabled_voice_session:
            _set_ui_state("sleep", source="ready")
        return
    lifecycle_session_id = ""
    lifecycle_producer_id = uuid.uuid4().hex
    lifecycle_global_lease_id = ""
    lifecycle_started = False
    lifecycle_heartbeat_stop = threading.Event()
    lifecycle_heartbeat_thread = None
    try:
        from engine.runtime_bridge import current_bridge_session_id, notify_tts_started
        lifecycle_session_id = current_bridge_session_id()
        if lifecycle_session_id:
            lifecycle_started = notify_tts_started(lifecycle_session_id, lifecycle_producer_id)
        else:
            from engine.runtime_bridge import notify_global_tts_started
            lifecycle_global_lease_id = notify_global_tts_started()
            lifecycle_started = bool(lifecycle_global_lease_id)
        if lifecycle_started:
            heartbeat_seconds = max(0.01, _env_float("NEXI_TTS_HEARTBEAT_SECONDS", 5.0))

            def _heartbeat_tts_lease():
                from engine.runtime_bridge import notify_global_tts_heartbeat, notify_tts_heartbeat
                while not lifecycle_heartbeat_stop.wait(heartbeat_seconds):
                    posted = (
                        notify_tts_heartbeat(lifecycle_session_id, lifecycle_producer_id)
                        if lifecycle_session_id
                        else notify_global_tts_heartbeat(lifecycle_global_lease_id)
                    )
                    if not posted:
                        print(f"[TTS] heartbeat_enqueue_failed session={lifecycle_session_id} lease={lifecycle_global_lease_id}", flush=True)
                        return

            lifecycle_heartbeat_thread = threading.Thread(
                target=_heartbeat_tts_lease,
                daemon=True,
                name="tts-lifecycle-heartbeat",
            )
            lifecycle_heartbeat_thread.start()
    except Exception:
        lifecycle_session_id = ""
        lifecycle_started = False
    set_speaking(True)
    try:
        from engine.turn_manager import mark_assistant_speaking
        mark_assistant_speaking(text)
    except Exception:
        pass
    print("[TTS] speak_started", flush=True)
    print(f"[TTS] audio_output_started", flush=True)
    _set_ui_state("saying", source="tts", text=display_text)
    start_generation = get_interrupt_generation()
    try:
        try:
            _update_speech_capsule(voice_text)
            if os.getenv("NEXI_ONLINE_TTS") == "1" and is_online():
                error = speak_streamelements(voice_text, voice, display_message=display_text)
                if error is None:
                    return
            from engine.tts_provider_manager import speak_with_provider
            speak_with_provider(
                voice_text,
                display_text=display_text,
                fallback_speaker=lambda spoken: speak_pyttsx3(spoken, display_text=display_text, start_generation=start_generation),
                on_display=lambda shown: (safe_eel_call("DisplayMessage", shown), safe_eel_call("receiverText", shown)),
            )
        except Exception as e:
            safe_eel_call("receiverText", display_text)
            print(f"[TTS] error={type(e).__name__}", flush=True)
    finally:
        was_interrupted = should_interrupt()
        if was_interrupted:
            print(f"[TTS] interrupted source={get_interrupt_source() or 'unknown'}", flush=True)
            clear_interrupt()
        set_speaking(False)
        try:
            from engine.turn_manager import mark_assistant_done
            mark_assistant_done(text)
        except Exception:
            pass
        try:
            from engine.voice_state_machine import get_voice_state_machine
            get_voice_state_machine().transition("tts_finished", source="tts")
        except Exception:
            pass
        lifecycle_order_lock = threading.Lock()
        lifecycle_finish_posted = False
        lifecycle_cooldown_pending = False

        def _notify_cooldown_in_order():
            nonlocal lifecycle_cooldown_pending
            with lifecycle_order_lock:
                if not lifecycle_finish_posted:
                    lifecycle_cooldown_pending = True
                    return
            if lifecycle_session_id:
                from engine.runtime_bridge import notify_cooldown_complete
                notify_cooldown_complete(lifecycle_session_id, lifecycle_producer_id)
            else:
                from engine.runtime_bridge import notify_global_cooldown_complete
                notify_global_cooldown_complete(lifecycle_global_lease_id)

        try:
            from engine.post_tts_cleanup import post_tts_cleanup
            if lifecycle_started:
                post_tts_cleanup(on_complete=_notify_cooldown_in_order)
            else:
                post_tts_cleanup()
        except Exception:
            pass
        if lifecycle_started:
            try:
                lifecycle_heartbeat_stop.set()
                if lifecycle_heartbeat_thread is not None:
                    lifecycle_heartbeat_thread.join(timeout=0.25)
                if was_interrupted:
                    if lifecycle_session_id:
                        from engine.runtime_bridge import notify_tts_interrupted
                        finish_posted = notify_tts_interrupted(lifecycle_session_id, lifecycle_producer_id)
                    else:
                        from engine.runtime_bridge import notify_global_tts_interrupted
                        finish_posted = notify_global_tts_interrupted(lifecycle_global_lease_id)
                else:
                    if lifecycle_session_id:
                        from engine.runtime_bridge import notify_tts_finished
                        finish_posted = notify_tts_finished(lifecycle_session_id, lifecycle_producer_id)
                    else:
                        from engine.runtime_bridge import notify_global_tts_finished
                        finish_posted = notify_global_tts_finished(lifecycle_global_lease_id)
                with lifecycle_order_lock:
                    lifecycle_finish_posted = finish_posted
                    notify_pending_cooldown = finish_posted and lifecycle_cooldown_pending
                if notify_pending_cooldown:
                    _notify_cooldown_in_order()
                if not finish_posted:
                    print(f"[TTS] terminal_enqueue_failed session={lifecycle_session_id} lease={lifecycle_global_lease_id}", flush=True)
                    if lifecycle_session_id:
                        from engine.runtime_bridge import current_control_queue, post_session_finish
                        if not post_session_finish(
                            current_control_queue(),
                            lifecycle_session_id,
                            reason="tts_terminal_enqueue_failed",
                            force=True,
                        ):
                            print(f"[TTS] finish_fallback_failed session={lifecycle_session_id} lease_expiry_pending=true", flush=True)
            except Exception:
                pass
        if not expects_followup and not lifecycle_session_id:
            _set_ui_state("sleep", source="ready")
        safe_eel_call("hideSpeechCapsule")
        print("[TTS] speak_finished", flush=True)
        print(f"[TTS] audio_output_finished", flush=True)
        if expects_followup:
            _maybe_start_auto_followup()

import re

from engine.intents import match_intent

_last_spoken = ""


from engine.intent_router import route_intent, IntentResult


def should_use_lightning_query(query: str) -> bool:
    """Backward-compat wrapper. Returns True if router classifies as lightning."""
    return route_intent(query).route == "lightning"


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _clarification_message() -> str:
    return "I didn't catch that. Please say it again in English."


def _should_clarify_unknown(query: str) -> bool:
    from engine.transcript_filter import is_gibberish_or_wrong_language
    if is_gibberish_or_wrong_language(query):
        return True
    words = re.findall(r"[a-zA-Z]+", query or "")
    return len(words) <= 3


def _safe_chatbot(query: str):
    from engine.features import chatBot
    return chatBot(query)


_GREETING_RESPONSES = (
    "Hello sir, how can I help you?",
    "Hi, I am Nexi. What can I do for you?",
)
_IDENTITY_RESPONSE = (
    "I am Nexi, your desktop assistant. I can open apps, create folders, "
    "answer questions, and more."
)


def _speak_greeting():
    speak(_GREETING_RESPONSES[0])


def _speak_identity():
    speak(_IDENTITY_RESPONSE)


def _store_conversation_turn(query, response, result=None):
    """`result` is this turn's actual tool result, when there was one.

    Reflection used to be handed a hardcoded {}, so it learned from turns with no
    observed outcome. Passing it explicitly (rather than via a module global) keeps
    a previous turn's result from leaking into a later, unrelated turn.
    """
    try:
        from engine.app.runtime_context import get_conversation_buffer
        get_conversation_buffer().append_turn(query, response)
    except Exception:
        pass
    try:
        from engine.conversation_context import add_assistant_turn
        add_assistant_turn(response or "")
    except Exception:
        pass
    try:
        # Autonomous short-term memory — final assistant response, pairs with the
        # user turn recorded in command_bus to form one exchange.
        from engine.autonomous_memory import add_assistant_message
        add_assistant_message(response or "")
    except Exception:
        pass
    try:
        from engine.memory.session_memory import add_assistant_turn as add_session_assistant_turn
        add_session_assistant_turn(response or "")
    except Exception:
        pass
    try:
        from engine.adaptive_memory import learn_from_exchange
        learn_from_exchange(query or "", response or "")
    except Exception:
        pass
    try:
        from engine.memory.semantic_memory import maybe_extract_semantic_memory
        maybe_extract_semantic_memory(query or "", response or "")
    except Exception:
        pass
    try:
        if query or response:
            from engine.memory.episodic_memory import Episode, store_episode
            store_episode(Episode(
                user_input=query or "",
                intent="conversation_turn",
                route=_last_handler_reason or "conversation",
                outcome="success" if response else "partial",
                steps_taken=["command_response_stored"],
                metadata={"source": "command_store"},
            ))
    except Exception:
        pass
    try:
        from engine.cognitive_context import get_last_strategy
        from engine.reflection_engine import reflect_after_turn
        reflect_after_turn(query or "", get_last_strategy(), result or {}, response or "")
    except Exception:
        pass


# "ui" is a typed command. It was missing here, so a clarification raised by a
# typed request logged "auto_listen requested" and then returned silently - the
# mic never opened and the question was a dead end. NEXI is hands-free first:
# once it has ASKED something, the user must be able to answer by voice however
# the request started.
_FOLLOWUP_SOURCES = {"hotword", "clap", "double_clap", "hotkey", "ui", "ui_button", "mic_button", "voice"}


def _active_workflow_id() -> str:
    try:
        from engine.workflow_state import get_workflow
        wf = get_workflow() or {}
        return str(wf.get("name") or "")
    except Exception:
        return ""


def _response_expects_user_reply(response: str) -> bool:
    try:
        from engine.assistant_response import response_asks_question
        return response_asks_question(response) or (bool(_active_workflow_id()) and str(response or "").strip().endswith("?"))
    except Exception:
        return str(response or "").strip().endswith("?")


def _maybe_start_auto_followup() -> None:
    try:
        from engine.turn_manager import should_auto_listen, consume_auto_listen_request, get_turn_state
        if not should_auto_listen():
            return
        turn_state = get_turn_state()
        listen_source = turn_state.get("reason") or "assistant_question"
        try:
            from engine.command_bus import current_source
            source = current_source()
        except Exception:
            source = "legacy"
        if source not in _FOLLOWUP_SOURCES:
            # Never fail silently here: a swallowed auto-listen looks exactly
            # like a broken assistant from the outside.
            print(f"[LISTEN] auto_followup_skipped source={source or 'unknown'}", flush=True)
            return
        from engine.runtime_bridge import request_followup_capture
        if not request_followup_capture(source=source, reason=listen_source):
            print("[LISTEN] auto_followup_deferred reason=audio_bridge_unavailable", flush=True)
            return
        consume_auto_listen_request()
        print(f"[LISTEN] auto_followup_requested source={listen_source}", flush=True)
    except Exception as e:
        print(f"[LISTEN] auto_followup_failed reason={type(e).__name__}", flush=True)


def ask_user(question: str, *, reason: str, workflow_id: str | None = None) -> str:
    workflow = workflow_id or _active_workflow_id() or None
    print(f"[ASSISTANT] ask_user reason={reason} workflow={workflow or ''}", flush=True)
    try:
        from engine.turn_manager import mark_waiting_for_user
        mark_waiting_for_user(question, reason=reason, workflow_id=workflow)
    except Exception:
        pass
    try:
        from engine.assistant_response import infer_followup_type
        from engine.followup_manager import set_pending_followup
        set_pending_followup(question, infer_followup_type(question), reason or "assistant")
    except Exception:
        pass
    speak(question, handler_reason=reason)
    _maybe_start_auto_followup()
    return question


def _respond_to_user(response: str, *, reason: str = "assistant_response", workflow_id: str | None = None) -> None:
    if _response_expects_user_reply(response):
        ask_user(response, reason=reason, workflow_id=workflow_id)
    else:
        speak(response, handler_reason=reason)


def _try_clarification(query: str) -> bool:
    q = (query or "").strip().lower().rstrip(".?!")
    if q not in {"open", "search", "google", "write essay", "write an essay", "essay", "start camera control", "start hand gesture control", "start eye mouse"}:
        return False
    from engine.clarification_manager import ask_clarification
    response = ask_clarification(query, reason="clarification")
    speak(response["display_text"])
    return True


def _ask_for_clarification(query: str, reason: str = "clarification") -> None:
    from engine.clarification_manager import ask_clarification
    response = ask_clarification(query, reason=reason)
    speak(response["display_text"])


def _handle_wake_sleep_command(query: str) -> bool:
    from engine.intent_pre_router import normalize_immediate_command
    q = normalize_immediate_command(query)
    sleep_commands = {"sleep", "go to sleep", "stop listening"}
    wake_commands = {"wake", "wake up", "activate nexi"}
    if q in sleep_commands:
        from engine.interrupt_controller import interrupt_and_wait
        interrupt_and_wait(source="command", reason="sleep")
        from engine.nexi_wake_controller import sleep_nexi
        sleep_nexi(reason="command")
        speak("Sleeping.")
        _store_conversation_turn(query, "Sleeping.")
        return True
    if q in wake_commands:
        from engine.interrupt_controller import interrupt_and_wait
        interrupt_and_wait(source="command", reason="wake")
        from engine.nexi_wake_controller import wake_nexi
        wake_nexi("command")
        speak("I am awake.")
        _store_conversation_turn(query, "I am awake.")
        return True
    return False


def _handle_voice_diagnostic_command(query: str) -> bool:
    from engine.intent_pre_router import normalize_immediate_command
    q = normalize_immediate_command(query)
    diagnostic_commands = {
        "what voice state are you in",
        "show voice diagnostics",
        "show capability diagnostics",
        "show agent diagnostics",
        "show nexi capability diagnostics",
        "check hotword barge in",
        "check tts lock",
        "check memory system",
        "show last voice transition",
        "show last interruption reason",
    }
    if q == "check last ten exchanges":
        from engine.voice_diagnostics import format_last_ten_exchanges
        response = format_last_ten_exchanges()
        speak(response, handler_reason="system")
        _store_conversation_turn(query, response)
        return True
    if q not in diagnostic_commands:
        return False
    if q in {"show capability diagnostics", "show agent diagnostics", "show nexi capability diagnostics"}:
        from engine.diagnostic_capabilities import format_diagnostic_capabilities

        response = format_diagnostic_capabilities()
        speak(response, handler_reason="system")
        _store_conversation_turn(query, response)
        return True
    from engine.voice_diagnostics import format_voice_diagnostics, get_voice_diagnostics
    payload = get_voice_diagnostics()
    if q == "show last voice transition":
        transition = payload.get("last_transition") or {}
        response = (
            f"Last voice transition: {transition.get('state_before', 'none')} "
            f"to {transition.get('state_after', 'none')} on {transition.get('event', 'none')}."
        )
    elif q == "show last interruption reason":
        response = f"Last interruption reason: {payload.get('last_interruption_reason') or 'none'}."
    elif q == "check hotword barge in":
        response = (
            "Hotword barge-in: "
            f"interrupt listening active is {payload.get('interrupt_listening_active')}; "
            f"hotword detector active is {payload.get('hotword_detector_active')}."
        )
    elif q == "check tts lock":
        response = (
            f"TTS active: {payload.get('tts_active')}. "
            f"Full command listening active: {payload.get('full_command_listening_active')}. "
            f"Cooldown remaining: {payload.get('cooldown_remaining_ms')} milliseconds."
        )
    elif q == "check memory system":
        response = (
            f"Memory exchanges: {payload.get('memory_exchange_count')}. "
            f"Rolling summary: {payload.get('rolling_summary_status')}."
        )
    else:
        response = format_voice_diagnostics(payload)
    speak(response, handler_reason="system")
    _store_conversation_turn(query, response)
    return True


def _handle_memory_command(query: str) -> bool:
    from engine.memory_store import parse_memory_command
    response = parse_memory_command(query)
    if response is None:
        return False
    speak(response)
    _store_conversation_turn(query, response)
    return True


def _handle_cognitive_command(query: str) -> bool:
    q = (query or "").strip()
    low = q.lower().rstrip(".?!")
    try:
        from engine.train_mode import handle_training_command
        response = handle_training_command(q)
        if response:
            speak(response)
            _store_conversation_turn(query, response)
            return True
    except Exception as e:
        print(f"Cognitive training command error: {e}")

    response = ""
    if low.startswith("forget training rule about "):
        try:
            from engine.training_rules import disable_training_rule
            result = disable_training_rule(q[27:].strip())
            count = int(result.get("disabled", 0))
            response = "Training rule disabled." if count else "I did not find a matching training rule."
        except Exception:
            response = "I could not update that training rule."
    elif low == "show training rules":
        from engine.training_rules import format_rule_summary
        response = format_rule_summary()
    elif low in {"what have you learned", "what have you learned?"}:
        from engine.training_rules import format_rule_summary
        try:
            from engine.user_model import get_user_model_context
            user_context = get_user_model_context(max_chars=600)
        except Exception:
            user_context = ""
        response = format_rule_summary()
        try:
            from engine.need_training_manager import format_need_profiles
            profiles = format_need_profiles()
            if profiles and "No active" not in profiles:
                response += " " + profiles
        except Exception:
            pass
        if user_context:
            response += " Preferences: " + user_context.replace("\n", "; ")
    elif low == "cognitive status":
        from engine.cognitive_context import cognitive_status
        response = cognitive_status()
    elif low in {"what did you understand", "what did you understand?", "why did you do that", "why did you do that?", "what rule did you use", "what tool did you choose"}:
        if low.startswith("why"):
            from engine.cognitive_context import explain_last_route
            response = explain_last_route()
        elif low.startswith("what did you understand"):
            from engine.cognitive_context import describe_last_understanding
            response = describe_last_understanding()
        else:
            try:
                from engine.intent_explainer import explain_last_intent
                response = explain_last_intent()
                if response.startswith("I have not routed"):
                    raise ValueError("no_phase4_intent")
            except Exception:
                from engine.cognitive_context import explain_last_route
                response = explain_last_route()
    elif low in {"learn from this", "correct that", "correct this"}:
        response = "Tell me the correction as: when I say X, do Y."

    if not response:
        return False
    speak(response)
    _store_conversation_turn(query, response)
    return True


def _handle_output_command(query: str) -> bool:
    q = (query or "").strip().lower().rstrip(".?!")
    if not q:
        return False
    from engine.output_actions import copy_latest_output, create_output_file, save_latest_output_as, reopen_latest_output, get_latest_output, summarize_latest_output
    response = None
    if q in {"copy it", "copy this", "copy latest", "copy latest output"}:
        response = copy_latest_output().get("message", "Copied.")
    elif q in {"create a file", "create file"}:
        result = create_output_file()
        response = result.get("message", "What should I name the file?")
    elif q.startswith("save it as "):
        response = save_latest_output_as(query[11:].strip()).get("message", "Saved.")
    elif q in {"open the box", "show it again", "show latest output", "show the box"}:
        result = reopen_latest_output()
        if result.get("ok"):
            safe_eel_call("showOutputWorkspace", json.dumps({"show_workspace": True, "workspace_content": result["output"].get("content", ""), "workspace_summary": result["output"].get("summary", ""), "workspace_type": result["output"].get("content_type", "text"), "workspace_title": result["output"].get("title", "Nexi Output")}))
        response = result.get("message", "Showing the latest output.")
    elif q in {"close the box", "close output workspace"}:
        safe_eel_call("closeOutputWorkspace")
        response = "Closed."
    elif q in {"minimize the box", "minimize output workspace"}:
        safe_eel_call("minimizeOutputWorkspace")
        response = "Minimized."
    elif q in {"pin the box", "pin output workspace"}:
        safe_eel_call("pinOutputWorkspace")
        response = "Pinned."
    elif q in {"make it shorter", "shorten it", "shorten latest output"}:
        latest = get_latest_output()
        if latest.get("content"):
            response = summarize_latest_output(420)
        else:
            try:
                from engine.conversation_context import find_recent_reference
                ref = find_recent_reference(query)
                response = (ref or {}).get("text", "")[:420] or "I don't have anything to shorten yet."
            except Exception:
                response = "I don't have anything to shorten yet."
    elif q in {"regenerate it", "regenerate latest output"}:
        response = "I can regenerate it if you tell me what to change."
    if response is None:
        return False
    speak(response)
    _store_conversation_turn(query, response)
    return True


def _should_try_output_command(query: str) -> bool:
    q = (query or "").strip().lower().rstrip(".?!")
    if q in {"create a file", "create file"}:
        try:
            from engine.output_actions import get_latest_output
            return bool(get_latest_output().get("content"))
        except Exception:
            return False
    return True


def _handle_product_intelligence_v2(query: str, command_source: str) -> bool:
    """Compatibility name for the live Router V3 dispatch boundary."""
    if (os.getenv("NEXI_INTENT_V2_ENABLED", "true") or "").strip().lower() in {"0", "false", "no", "off"}:
        return False
    try:
        from engine.router_v3 import route_intent_v3

        decision = route_intent_v3(query, source=command_source)
    except ImportError:
        return False
    except Exception as e:
        print(f"[INTENT_V3] failed reason={type(e).__name__}", flush=True)
        try:
            from engine.demo_mode import DemoMode
            if DemoMode.is_active():
                response = DemoMode.safe_response("router_fail")
                speak(response, handler_reason="system")
                _store_conversation_turn(query, response)
                return True
        except Exception:
            pass
        response = "I couldn't route that request safely. Please rephrase it."
        speak(response, handler_reason="clarification")
        _store_conversation_turn(query, response)
        return True

    route = str(decision.get("route") or "")
    intent = str(decision.get("intent") or "")
    slots = decision.get("slots") if isinstance(decision.get("slots"), dict) else {}
    print(f"[INTENT_V3] dispatch route={route} intent={intent}", flush=True)

    if route in {"workflow", "system", "memory", "feature_gap"}:
        from engine.tool_registry import get_tool
        routed_intent = "request_feature" if route == "feature_gap" else intent
        if get_tool(routed_intent):
            route = "tool"
            intent = routed_intent

    if route == "clarify":
        if intent == "create_folder":
            from engine.create_folder_workflow import start_create_folder

            response = start_create_folder(query, pre_slots=slots)
            _respond_to_user(response, reason="missing_slot", workflow_id="create_folder")
            _store_conversation_turn(query, response)
            return True
        question = decision.get("clarification_question") or "I didn't catch that. Please say it again in English."
        followup_type = intent if intent not in {"unknown", "clarify"} else "generic"
        try:
            from engine.clarification_manager import ask_custom_clarification

            response = ask_custom_clarification(question, followup_type=followup_type, reason=decision.get("reason", "intent_v2"))
            speak(response["display_text"])
        except Exception:
            speak(question)
        _store_conversation_turn(query, question)
        return True

    if route == "tool":
        from engine.tool_registry import execute_tool
        from engine.assistant_response import guard_unverified_action_message, verified_action

        tool_result = execute_tool(intent, slots, confirmed=False)
        if isinstance(tool_result, dict) and tool_result.get("missing_slot"):
            response_text = str(tool_result.get("message") or "What information is missing?")
            _respond_to_user(response_text, reason="missing_slot", workflow_id="create_folder" if intent == "create_folder" else None)
            _store_conversation_turn(query, response_text)
            return True
        action_verified = verified_action(tool_result)
        print(f"[ACTION] verified={str(action_verified).lower()}", flush=True)
        response_text = str(tool_result.get("message", "") if isinstance(tool_result, dict) else "")
        if not action_verified and not (isinstance(tool_result, dict) and tool_result.get("expects_user_reply")):
            response_text = guard_unverified_action_message(response_text or "I couldn't verify that action.", tool_result)
        _respond_to_user(response_text or "I couldn't verify that action.", reason="tool")
        _store_conversation_turn(query, response_text or "", tool_result)
        return True

    if route == "output":
        from engine.tool_registry import execute_tool
        from engine.assistant_response import guard_unverified_action_message, verified_action

        result = execute_tool(intent, slots)
        if result.get("output"):
            safe_eel_call("showOutputWorkspace", json.dumps({
                "show_workspace": True,
                "workspace_content": result["output"].get("content", ""),
                "workspace_summary": result["output"].get("summary", ""),
                "workspace_type": result["output"].get("content_type", "text"),
                "workspace_title": result["output"].get("title", "Nexi Output"),
            }))
        response_text = str(result.get("message") or "I couldn't run that output action safely.")
        if not verified_action(result) and not result.get("expects_user_reply"):
            response_text = guard_unverified_action_message(response_text, result)
        _respond_to_user(response_text, reason="output")
        _store_conversation_turn(query, response_text, result)
        return True

    if route == "brain":
        response = _safe_chatbot(query)
        _store_conversation_turn(query, response or "")
        return True

    if route == "react":
        from engine.react_planner import ReActPlanner

        planner = ReActPlanner()
        plan = planner.plan(query, context=decision)
        response = planner.finalize(plan)
        _respond_to_user(response, reason="react")
        _store_conversation_turn(query, response)
        try:
            from engine.memory.episodic_memory import Episode, store_episode
            store_episode(Episode(user_input=query, intent=intent or "react_multi_step", route="react", outcome="success" if plan.status == "done" else "failure", steps_taken=[step.tool_name or step.action for step in plan.steps], error=plan.error or ""))
        except Exception:
            pass
        return True

    if route == "memory":
        if _handle_memory_command(query) or _handle_cognitive_command(query):
            return True

    if route == "training":
        if intent == "correction":
            from engine.correction_learner import record_correction_from_text

            result = record_correction_from_text(query)
            response = "Correction learned." if result.get("stored") else "Tell me the correction as: wrong, when I say X, do Y."
            speak(response)
            _store_conversation_turn(query, response)
            return True
        if _handle_cognitive_command(query):
            return True

    if route == "workflow":
        if intent == "create_folder":
            from engine.create_folder_workflow import start_create_folder

            response = start_create_folder(query, pre_slots=slots)
            _respond_to_user(response, reason="missing_slot", workflow_id="create_folder")
            _store_conversation_turn(query, response)
            return True
        pass

    if route == "followup":
        answer = slots.get("answer")
        if intent == "confirmation":
            response = "Okay." if answer is True else "Cancelled."
        else:
            response = "Got it."
        speak(response)
        _store_conversation_turn(query, response)
        return True

    if route == "system":
        if intent == "greeting":
            response = _GREETING_RESPONSES[0]
            _speak_greeting()
        elif intent == "identity":
            response = _IDENTITY_RESPONSE
            _speak_identity()
        elif intent == "repeat_last":
            from engine.conversation_context import get_last_assistant_response

            response = get_last_assistant_response() or "I don't have anything to repeat yet."
            speak(response)
        elif intent in {"what_did_you_understand", "why_did_you_do_that"}:
            from engine.intent_explainer import explain_last_intent

            response = explain_last_intent()
            speak(response)
        else:
            response = ""
        if response:
            _store_conversation_turn(query, response)
            return True

    if route == "cancel":
        try:
            from engine.workflow_state import clear_workflow
            clear_workflow()
        except Exception:
            pass
        try:
            from engine.followup_manager import clear_followup
            clear_followup("cancel")
        except Exception:
            pass
        try:
            from engine.clarification_manager import clear_clarification
            clear_clarification("cancel")
        except Exception:
            pass
        response = "Cancelled."
        speak(response)
        _store_conversation_turn(query, response)
        return True

    if route in {"sleep", "wake"}:
        if _handle_wake_sleep_command(query):
            return True

    if route == "interrupt":
        try:
            from engine.voice.speech_controller import stop_speaking as sc_stop, speak as sc_speak
            sc_stop(reason="intent_v2")
            sc_speak("Stopped speaking.")
            _store_conversation_turn(query, "Stopped speaking.")
            return True
        except ImportError:
            speak("Stopped.")
            _store_conversation_turn(query, "Stopped.")
            return True

    if route == "reject":
        response = "I can't help with that."
        speak(response)
        _store_conversation_turn(query, response)
        return True

    response = decision.get("clarification_question") or "I couldn't safely complete that request. Could you clarify what you want me to do?"
    speak(response, handler_reason="clarification")
    _store_conversation_turn(query, response)
    return True

try:
    from engine.control import (
        execute_control_action, match_control_action, list_control_actions,
        EmergencyStop, ControlResult, registry as control_registry
    )
    CONTROL_AVAILABLE = True
except ImportError as e:
    print(f"Control layer not available: {e}")
    CONTROL_AVAILABLE = False


def _extract_entity(text, prefixes):
    t = text.lower()
    for prefix in prefixes:
        if prefix in t:
            idx = t.index(prefix) + len(prefix)
            return t[idx:].strip()
    return text.strip()


def handle_control_action(query, action_name):
    if not CONTROL_AVAILABLE:
        return ControlResult.failure(
            message="Control layer not initialized",
            code="CONTROL_UNAVAILABLE"
        )
    entities = {}
    if action_name in ("open_app", "close_app", "focus_app"):
        app_name = _extract_entity(query, ["open ", "launch ", "start ", "close ", "kill ", "focus ", "switch to ", "bring to front "])
        if not app_name or app_name == query.lower():
            app_name = query.strip()
        entities["app_name"] = app_name.strip()
    elif action_name in ("search_google",):
        search = _extract_entity(query, ["search google for ", "google search ", "search the web for ", "google "])
        if not search or search == query.lower():
            search = query.strip()
        entities["query"] = search
    elif action_name in ("search_youtube",):
        search = _extract_entity(query, ["search youtube for ", "search you tube for ", "youtube search ", "on youtube "])
        if not search or search == query.lower():
            search = query.strip()
        entities["query"] = search
    elif action_name in ("open_url",):
        url = _extract_entity(query, ["go to ", "open url ", "navigate to ", "take me to "])
        entities["url"] = url
    elif action_name in ("create_folder",):
        folder_name = _extract_entity(query, ["called ", "named "])
        location = "desktop"
        if "download" in query:
            location = "downloads"
        elif "document" in query:
            location = "documents"
        entities["folder_name"] = folder_name
        entities["location"] = location
    elif action_name in ("open_folder",):
        loc = "desktop"
        if "download" in query:
            loc = "downloads"
        elif "document" in query:
            loc = "documents"
        entities["location"] = loc
    elif action_name == "emergency_stop":
        return EmergencyStop.engage(reason="User requested emergency stop")
    result = execute_control_action(action_name, entities)
    return result


def extract_email(query):
    email_regex = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    email = re.search(email_regex, query)
    return email.group(0) if email else None


def provide_directions(location_link):
    webbrowser.open(location_link)
    speak("Here are the directions to your selected location.")


def takecommand():
    r = sr.Recognizer()
    r.energy_threshold = 300
    r.dynamic_energy_threshold = True
    is_followup = False
    try:
        from engine.clarification_manager import has_pending_clarification
        from engine.followup_manager import has_pending_followup
        is_followup = has_pending_clarification() or has_pending_followup()
    except Exception:
        is_followup = False
    max_seconds_key = "ASR_FOLLOWUP_MAX_RECORD_SECONDS" if is_followup else "ASR_MAX_RECORD_SECONDS"
    silence_key = "ASR_FOLLOWUP_SILENCE_TIMEOUT_MS" if is_followup else "ASR_SILENCE_TIMEOUT_MS"
    max_record_seconds = _env_float(max_seconds_key, _env_float("ASR_MAX_RECORD_SECONDS", 6.0))
    silence_timeout_ms = _env_int(silence_key, _env_int("ASR_SILENCE_TIMEOUT_MS", 900))
    max_retries = int(os.getenv("NEXI_ASR_RETRIES", "1"))

    for retry in range(max_retries + 1):
        with sr.Microphone() as source:
            if retry > 0:
                from engine.command import speak
                speak("Say that again")
                print('listening (retry)...')
                r.adjust_for_ambient_noise(source, duration=0.3)
            else:
                print('listening....')
            _set_ui_state("listening", source="wake")
            safe_eel_call("setStatus", "Listening...", "listening")
            r.pause_threshold = max(0.2, silence_timeout_ms / 1000.0)
            if retry == 0:
                r.adjust_for_ambient_noise(source, duration=0.7)
            audio = r.listen(source, 10, max_record_seconds)

        try:
            print('recognizing')
            _set_ui_state("transcribing", source="wake")
            safe_eel_call("setStatus", "Understanding...", "transcribing")
            query = ""
            if (os.getenv("ASR_PROVIDER", "") or "").strip().lower() == "groq":
                try:
                    from engine.groq_asr import transcribe_audio_bytes
                    query = transcribe_audio_bytes(audio.get_wav_data())
                except Exception as e:
                    print(f"[ASR] followup_groq_failed reason={type(e).__name__}", flush=True)
            if not query:
                query = r.recognize_google(audio, language='en-in')
            if query:
                print(f"user said: {query}")
                _set_ui_state("thinking", source="wake", text=query)
                time.sleep(0.05)
                return query.lower()
            print(f"[ASR] empty_transcript retry={retry}/{max_retries}", flush=True)
        except Exception as e:
            print(f"[ASR] failed reason={type(e).__name__} retry={retry}/{max_retries}", flush=True)
            if retry >= max_retries:
                return ""

    return ""
def handle_read_selected():
    speak("Sure sir, reading your selected data")
    keyboard.press_and_release("ctrl + c")
    time.sleep(1)
    clipboard_data = pi.paste()
    speak(clipboard_data)


def handle_contact_message(query, call_type):
    from engine.features import findContact, whatsApp
    contact_no, name = findContact(query)
    if contact_no == 0:
        return
    flag = 'message' if call_type == 'message' else ('call' if call_type == 'phone_call' else 'video call')
    if flag == 'message':
        speak("What message to send")
        msg = takecommand()
        whatsApp(contact_no, msg, flag, name)
    else:
        whatsApp(contact_no, query, flag, name)


def handle_weather_search(query):
    speak("Fetching the weather information.")
    from urllib.parse import quote_plus
    # encode: a raw query with spaces/&/# breaks the URL or injects extra params
    url = f"https://www.google.com/search?q={quote_plus(str(query or ''))}"
    try:
        r = requests.get(url, timeout=8)
        data = BeautifulSoup(r.text, "html.parser")
        temp = data.find("div", class_="BNeawe").text
        speak(f"The weather is {temp}")
    except Exception as e:
        print(f"Weather error: {e}")
        speak("Sorry, I couldn't fetch the weather information.")


def handle_music():
    speak("What song should I play?")
    song = takecommand()
    if not song:
        speak("I didn't catch the song name.")
        return
    webbrowser.open(f"https://open.spotify.com/search/{song}")
    target_tab = 35
    pyautogui.hotkey("tab")
    for _ in range(1, target_tab):
        pyautogui.hotkey('tab')
    pyautogui.hotkey('enter')
    speak("Sure sir, here is your music!")


def handle_time():
    import datetime
    try:
        current_time = datetime.datetime.now().strftime("%I:%M %p")
        speak(f"The time is {current_time}")
    except Exception as e:
        error_message = f"An error occurred: {e}"
        print(error_message)
        speak(error_message)


def handle_google_search(query):
    search_term = query
    for prefix in ["search google for", "google search", "search the web", "look up", "search for"]:
        if prefix in query.lower():
            search_term = query.lower().split(prefix)[-1].strip()
            break
    if not search_term:
        search_term = query
    speak(f"Searching Google for {search_term}")
    search_google(search_term)


def handle_close_app(query):
    from engine.features import closeappweb
    closeappweb(query)


def dispatch_intent(query):
    if EmergencyStop.is_engaged():
        return True
    intent, confidence = match_intent(query)
    if intent is None:
        return False
    threshold = _env_float("INTENT_LOCAL_ACTION_THRESHOLD", 0.75)
    if confidence < threshold:
        print(f"[INTENT] blocked low_confidence intent={intent.name} confidence={confidence:.2f} threshold={threshold:.2f}")
        return False

    name = intent.name
    print(f"[ROUTER] route: local_action intent={name} confidence={confidence:.2f}")

    if name == "open_app":
        from engine.features import openCommand
        openCommand(query)

    elif name == "youtube":
        from engine.features import PlayYoutube
        PlayYoutube(query)

    elif name == "create_folder":
        if " and add " in query.lower():
            create_folder_and_files(query)
        else:
            from engine.create_folder_workflow import start_create_folder
            _respond_to_user(start_create_folder(query), reason="missing_slot", workflow_id="create_folder")

    elif name == "create_file":
        from engine.file_operations import create_file_in_existing_folder
        create_file_in_existing_folder(query)

    elif name == "read_selected":
        handle_read_selected()

    elif name == "image_to_text":
        from vision.Vbrain import main
        main()

    elif name in ("message", "phone_call", "video_call"):
        handle_contact_message(query, name)

    elif name == "weather":
        handle_weather_search(query)

    elif name == "music":
        handle_music()

    elif name == "auto_type":
        from engine.automaticTyping import automaticTyping
        automaticTyping()

    elif name == "joke":
        speak("Why don't scientists trust atoms? Because they make up everything!")

    elif name == "time":
        handle_time()

    elif name == "eye_mouse":
        try:
            from engine.camera_control import start_camera_control
            speak("Starting eye mouse control")
            start_camera_control(mode="eye")
        except Exception as e:
            print(f"[CAMERA] eye start error: {e}")
            from engine.Eye_mouse_Controller import Eye_mouse_Controller
            speak("Starting eye mouse control")
            Eye_mouse_Controller()
            speak("Eye mouse control stopped")

    elif name == "camera_stop":
        try:
            from engine.camera_control import stop_camera_control
            stop_camera_control()
            speak("Camera control stopped")
        except Exception as e:
            print(f"[CAMERA] stop error: {e}")
            speak("Could not stop camera control")

    elif name == "camera_hybrid":
        try:
            from engine.camera_control import start_camera_control
            speak("Starting hybrid camera control")
            start_camera_control(mode="hybrid")
        except Exception as e:
            print(f"[CAMERA] hybrid start error: {e}")
            speak("Could not start hybrid camera control")

    elif name == "camera_hand":
        try:
            from engine.camera_control import start_camera_control, stop_camera_control
            stop_camera_control()
            speak("Switching to hand gesture mode")
            start_camera_control(mode="hand")
        except Exception as e:
            print(f"[CAMERA] hand mode error: {e}")
            speak("Could not start hand mode")

    elif name == "camera_eye":
        try:
            from engine.camera_control import start_camera_control, stop_camera_control
            stop_camera_control()
            speak("Switching to eye tracking mode")
            start_camera_control(mode="eye")
        except Exception as e:
            print(f"[CAMERA] eye mode error: {e}")
            speak("Could not start eye mode")

    elif name == "camera_status":
        try:
            from engine.camera_control import get_status
            status = get_status()
            if status["running"]:
                msg = f"Camera control is running in {status['mode']} mode"
                gpu = status["gpu"]
                if gpu["nvidia"]:
                    msg += f" with NVIDIA {gpu['gpu_model']}"
                elif gpu["xnnpack"]:
                    msg += " with optimized CPU inference"
                else:
                    msg += " on CPU"
                speak(msg)
            else:
                speak("Camera control is not running")
        except Exception as e:
            print(f"[CAMERA] status error: {e}")
            speak("Could not get camera status")

    elif name == "camera_pause":
        try:
            from engine.camera_control import pause_camera_control
            if pause_camera_control():
                speak("Camera control paused")
            else:
                speak("Camera control is not running")
        except Exception as e:
            print(f"[CAMERA] pause error: {e}")
            speak("Could not pause camera control")

    elif name == "camera_resume":
        try:
            from engine.camera_control import resume_camera_control
            if resume_camera_control():
                speak("Camera control resumed")
            else:
                speak("Camera control is not running")
        except Exception as e:
            print(f"[CAMERA] resume error: {e}")
            speak("Could not resume camera control")

    elif name == "volume_up":
        from engine.keyboard import volumeup
        speak("Turning volume up, sir")
        volumeup()

    elif name == "volume_down":
        from engine.keyboard import volumedown
        speak("Turning volume down, sir")
        volumedown()

    elif name == "game":
        from engine.Game import game_play
        game_play()

    elif name == "chess":
        from Chess.src import main as chess_main
        speak("Starting chess")
        chess_main()

    elif name == "hand_gesture":
        try:
            from engine.camera_control import start_camera_control
            speak("Starting hand gesture control")
            start_camera_control(mode="hand")
        except Exception as e:
            print(f"[CAMERA] hand gesture error: {e}")
            from engine.HandGesture import HandGesture
            HandGesture()

    elif name == "face_recognition":
        try:
            from engine.camera_control import start_face_recognition, is_face_recognition_running, stop_face_recognition
            if is_face_recognition_running():
                speak("Face recognition is already running")
            else:
                speak("Starting face recognition")
                start_face_recognition()
        except Exception as e:
            print(f"[FACE] start error: {e}")
            speak("Could not start face recognition")

    elif name == "face_register":
        speak("Look at the camera to register your face")
        try:
            from engine.camera_control import register_face
            ok = register_face(name="User")
            if ok:
                speak("Face registered successfully")
            else:
                speak("Face registration failed")
        except Exception as e:
            print(f"[FACE] register error: {e}")
            speak("Could not register face")

    elif name == "alarm":
        from Time_operation.brain import input_manage_alarm
        input_manage_alarm()

    elif name == "schedule":
        from Time_operation.brain import input_manage_schedule
        input_manage_schedule(query)

    elif name == "pause_media":
        pyautogui.press("k")
        speak("Video paused")

    elif name == "resume_media":
        pyautogui.press("k")
        speak("Video played")

    elif name == "mute_media":
        pyautogui.press("m")
        speak("Video muted")

    elif name == "internet_speed":
        from engine.features import check_internet_speed
        check_internet_speed()

    elif name == "object_detection":
        from app import main as obj_detect
        speak("Starting object detection")

    elif name == "generate_image":
        from engine.text_to_image import generate_image
        tts_query = query
        speak("Generating an image")
        generate_image(query)

    elif name == "search_google":
        handle_google_search(query)

    elif name == "close_app":
        handle_close_app(query)

    elif name == "browser_task_manager":
        speak("Opening Chrome Task Manager")
        chrome_task_manager()
    elif name == "minimize_window":
        speak("Minimizing the current window")
        minimize_window()
    elif name == "new_tab":
        speak("Opening a new tab")
        open_new_tab()
    elif name == "close_tab":
        speak("Closing the tab")
        close_tab()
    elif name == "browser_menu":
        speak("Opening the browser menu")
        open_browser_menu()
    elif name == "zoom_in":
        speak("Zooming in")
        zoom_in()
    elif name == "zoom_out":
        speak("Zooming out")
        zoom_out()
    elif name == "refresh":
        speak("Refreshing the page")
        refresh_page()
    elif name == "next_tab":
        speak("Switching to the next tab")
        switch_to_next_tab()
    elif name == "prev_tab":
        speak("Switching to the previous tab")
        switch_to_previous_tab()
    elif name == "history":
        speak("Opening history")
        open_history()
    elif name == "bookmarks":
        speak("Opening bookmarks")
        open_bookmarks()
    elif name == "go_back":
        speak("Going back")
        go_back()
    elif name == "go_forward":
        speak("Going forward")
        go_forward()
    elif name == "dev_tools":
        speak("Opening developer tools")
        open_dev_tools()
    elif name == "fullscreen":
        speak("Toggling full screen")
        toggle_full_screen()
    elif name == "private_window":
        speak("Opening private window")
        open_private_window()

    elif name == "stop_speaking":
        try:
            from engine.voice.speech_controller import stop_speaking, speak as sc_speak
            stop_speaking(reason="user_requested")
            sc_speak("Stopped speaking.")
        except ImportError:
            speak("Stopped.")
        return True

    elif name == "control_open_chrome":
        if CONTROL_AVAILABLE:
            result = execute_control_action("open_chrome")
            speak(result.message)
        else:
            from engine.features import openCommand
            openCommand("chrome")

    elif name == "control_open_youtube":
        if CONTROL_AVAILABLE:
            result = execute_control_action("open_youtube")
            speak(result.message)
        else:
            webbrowser.open("https://www.youtube.com")
            speak("Opening YouTube")

    elif name == "control_search_youtube":
        if CONTROL_AVAILABLE:
            result = execute_control_action("search_youtube", {"query": query})
            speak(result.message)
        else:
            speak("Searching YouTube")
            from engine.features import PlayYoutube
            PlayYoutube(query)

    elif name == "control_search_google":
        if CONTROL_AVAILABLE:
            result = execute_control_action("search_google", {"query": query})
            speak(result.message)
        else:
            handle_google_search(query)

    elif name == "control_open_url":
        if CONTROL_AVAILABLE:
            url = query.replace("go to", "").replace("navigate to", "").replace("take me to", "").strip()
            result = execute_control_action("open_url", {"url": url})
            speak(result.message)
        else:
            speak("Opening URL")

    elif name == "control_new_tab":
        if CONTROL_AVAILABLE:
            result = execute_control_action("new_tab")
            speak(result.message)
        else:
            open_new_tab()
            speak("Opening new tab")

    elif name == "control_close_tab":
        if CONTROL_AVAILABLE:
            result = execute_control_action("close_tab")
            speak(result.message)
        else:
            close_tab()
            speak("Closing tab")

    elif name == "control_tab_info":
        if CONTROL_AVAILABLE:
            result = execute_control_action("get_tab_info")
            speak(result.message)
        else:
            speak("Tab info not available")

    elif name == "control_show_apps":
        if CONTROL_AVAILABLE:
            result = execute_control_action("list_apps")
            data = result.data
            apps = data.get("apps", [])
            names = [a["name"] for a in apps[:20]]
            msg = f"Running apps: {', '.join(names)}" if names else "No apps found"
            speak(msg)

    elif name == "control_focus_app":
        if CONTROL_AVAILABLE:
            result = handle_control_action(query, "focus_app")
            speak(result.message)
        else:
            speak("Focus not available")

    elif name == "control_active_window":
        if CONTROL_AVAILABLE:
            result = execute_control_action("get_active_window")
            speak(result.message)
        else:
            speak("Window info not available")

    elif name == "control_create_folder":
        if CONTROL_AVAILABLE:
            result = handle_control_action(query, "create_folder")
            speak(result.message)
        else:
            create_folder_and_files(query)

    elif name == "control_create_file":
        if CONTROL_AVAILABLE:
            result = handle_control_action(query, "create_text_file")
            speak(result.message)
        else:
            from engine.file_operations import create_file_in_existing_folder
            create_file_in_existing_folder(query)

    elif name == "control_open_folder":
        if CONTROL_AVAILABLE:
            result = handle_control_action(query, "open_folder")
            speak(result.message)
        else:
            speak("Opening folder")

    elif name == "control_search_files":
        if CONTROL_AVAILABLE:
            result = handle_control_action(query, "search_files")
            speak(result.message)

    elif name == "control_emergency_stop":
        if CONTROL_AVAILABLE:
            EmergencyStop.engage(reason="User requested stop")
            speak("Emergency stop engaged. All actions blocked.")
        else:
            speak("Stop acknowledged")

    elif name == "control_status":
        if CONTROL_AVAILABLE:
            actions = list_control_actions()
            names = [a["name"] for a in actions]
            speak(f"I can control: {', '.join(names)}")
        else:
            speak("Control layer is not initialized")

    elif name == "diagnose_jarvi":
        try:
            from engine.diagnostic_doctors import diagnose, format_diagnosis
            result = diagnose()
            report = format_diagnosis(result)
            speak(report)
        except ImportError:
            speak("Diagnostics module not available")

    elif name == "check_hotword":
        try:
            from engine.diagnostic_doctors import check_hotword
            result = check_hotword()
            speak(f"Hotword check: {'OK' if result.get('ok') else result.get('problem', 'Issue found')}")
        except ImportError:
            speak("Diagnostics module not available")

    elif name == "check_bridge":
        try:
            from engine.diagnostic_doctors import check_bridge
            result = check_bridge()
            speak(f"Bridge check: {'OK' if result.get('ok') else result.get('problem', 'Issue found')}")
        except ImportError:
            speak("Diagnostics module not available")

    elif name == "check_playwright":
        try:
            from engine.diagnostic_doctors import check_playwright
            result = check_playwright()
            speak(f"Playwright check: {'OK' if result.get('ok') else result.get('problem', 'Issue found')}")
        except ImportError:
            speak("Diagnostics module not available")

    elif name == "control_open_chrome_hi":
        if CONTROL_AVAILABLE:
            result = execute_control_action("open_chrome")
            speak(result.message)
        else:
            from engine.features import openCommand
            openCommand("chrome")

    elif name == "control_open_youtube_hi":
        if CONTROL_AVAILABLE:
            result = execute_control_action("open_youtube")
            speak(result.message)
        else:
            webbrowser.open("https://www.youtube.com")
            speak("Opening YouTube")

    elif name == "control_search_google_hi":
        if CONTROL_AVAILABLE:
            search = _extract_entity(query, ["google pe search karo ", "google pe dhoondo ", "google search karo ", "google pe dhundho "])
            if not search:
                search = query.strip()
            result = execute_control_action("search_google", {"query": search})
            speak(result.message)
        else:
            handle_google_search(query)

    elif name == "control_search_youtube_hi":
        if CONTROL_AVAILABLE:
            search = _extract_entity(query, ["youtube pe search karo ", "youtube pe dhoondo ", "youtube search karo ", "youtube pe dhundho "])
            if not search:
                search = query.strip()
            result = execute_control_action("search_youtube", {"query": search})
            speak(result.message)
        else:
            from engine.features import PlayYoutube
            PlayYoutube(query)

    elif name in ("control_show_apps_hi",):
        if CONTROL_AVAILABLE:
            result = execute_control_action("list_apps")
            data = result.data
            apps = data.get("apps", []) if result.ok else []
            names = [a["name"] for a in apps[:20]] if apps else []
            msg = f"Running apps: {', '.join(names)}" if names else "No apps found"
            speak(msg)
        else:
            speak("Control layer not available")

    elif name in ("control_active_window_hi",):
        if CONTROL_AVAILABLE:
            result = execute_control_action("get_active_window")
            speak(result.message)
        else:
            speak("Window info not available")

    elif name in ("control_focus_app_hi",):
        if CONTROL_AVAILABLE:
            result = handle_control_action(query, "focus_app")
            speak(result.message)
        else:
            speak("Focus not available")

    elif name in ("control_create_folder_hi",):
        if CONTROL_AVAILABLE:
            result = handle_control_action(query, "create_folder")
            speak(result.message)
        else:
            create_folder_and_files(query)

    elif name in ("control_open_folder_hi",):
        if CONTROL_AVAILABLE:
            result = handle_control_action(query, "open_folder")
            speak(result.message)
        else:
            speak("Opening folder")

    elif name in ("control_emergency_stop_hi",):
        if CONTROL_AVAILABLE:
            EmergencyStop.engage(reason="User requested stop")
            speak("Emergency stop engaged. All actions blocked.")
        else:
            speak("Stop acknowledged")

    elif name in ("control_status_hi",):
        if CONTROL_AVAILABLE:
            actions = list_control_actions()
            names = [a["name"] for a in actions]
            speak(f"I can control: {', '.join(names)}")
        else:
            speak("Control layer is not initialized")

    else:
        return False

    return True


@eel.expose
def allCommands(message=1):
    try:
        try:
            from engine.command_bus import is_dispatching, submit_user_command, current_source
            if not is_dispatching():
                if message == 1:
                    query = takecommand()
                    submit_user_command(query, source="mic_button", mode="voice")
                else:
                    submit_user_command(str(message), source="typed", mode="typed")
                return
            command_source = current_source()
        except ImportError:
            command_source = "legacy"

        if message == 1:
            query = takecommand()
            print(query)
            safe_eel_call("senderText", query)
        else:
            query = message
            print(f"[ROUTER] received: {query}")
            safe_eel_call("senderText", query)

        try:
            from engine.voice.speech_interrupt import (
                classify_stop_command, is_emergency_stop_command,
            )
            if is_emergency_stop_command(query):
                if CONTROL_AVAILABLE:
                    EmergencyStop.engage(reason="User requested emergency stop")
                from engine.voice.speech_controller import stop_speaking as sc_stop
                sc_stop(reason="emergency_stop")
                speak("Emergency stop engaged. All actions blocked.")
                _store_conversation_turn(query, "Emergency stop engaged. All actions blocked.")
                safe_eel_call("ShowHood")
                return
            stop_type = classify_stop_command(query)
            if stop_type == "stop_speaking":
                from engine.voice.speech_controller import stop_speaking as sc_stop, speak as sc_speak
                sc_stop(reason="user_requested")
                sc_speak("Stopped speaking.")
                _store_conversation_turn(query, "Stopped speaking.")
                safe_eel_call("ShowHood")
                return
        except ImportError:
            pass
        except Exception as e:
            print(f"Stop command check error: {e}")

        try:
            if _handle_wake_sleep_command(query):
                return
        except Exception as e:
            print(f"Wake/sleep command error: {e}")

        try:
            if _handle_voice_diagnostic_command(query):
                safe_eel_call("ShowHood")
                return
        except Exception as e:
            print(f"Voice diagnostics command error: {e}")

        try:
            if _handle_cognitive_command(query):
                safe_eel_call("ShowHood")
                return
        except Exception as e:
            print(f"Cognitive command error: {e}")

        # Explicit Studio commands must not become answers to an active local workflow.
        try:
            from engine.studio.commands import is_explicit_studio_command
            if is_explicit_studio_command(query) and _handle_product_intelligence_v2(query, command_source):
                safe_eel_call("ShowHood")
                return
        except Exception as e:
            print(f"Studio command handling error: {e}")

        try:
            if _try_clarification(query):
                safe_eel_call("ShowHood")
                return
        except Exception as e:
            print(f"Clarification error: {e}")

        # --- Local Workflow Lite (Batch 3): continue only after immediate commands ---
        try:
            from engine.workflow_dialog_manager import handle_workflow_turn
            workflow_result = handle_workflow_turn(query, source=command_source)
            if workflow_result.get("switch"):
                pause_msg = workflow_result.get("response", "")
                if pause_msg:
                    speak(pause_msg)
                    _store_conversation_turn(query, pause_msg)
            elif workflow_result.get("handled"):
                response = workflow_result.get("response", "")
                _respond_to_user(response, reason="missing_slot", workflow_id=workflow_result.get("workflow_id") or None)
                _store_conversation_turn(query, response)
                safe_eel_call("ShowHood")
                return
        except Exception as e:
            print(f"Workflow handling error: {e}")

        try:
            if _handle_memory_command(query):
                safe_eel_call("ShowHood")
                return
        except Exception as e:
            print(f"Memory command error: {e}")

        try:
            if _should_try_output_command(query) and _handle_output_command(query):
                safe_eel_call("ShowHood")
                return
        except Exception as e:
            print(f"Output command error: {e}")

        try:
            if _handle_product_intelligence_v2(query, command_source):
                safe_eel_call("ShowHood")
                return
        except Exception as e:
            print(f"Product intelligence v2 error: {e}")

        try:
            from engine.tool_registry import select_tool, execute_tool
            selected_tool = select_tool(query)
            if selected_tool.get("handled"):
                tool_result = execute_tool(selected_tool["name"], selected_tool.get("slots") or {})
                from engine.assistant_response import verified_action as _is_verified_action
                verified_action = _is_verified_action(tool_result)
                print(f"[ACTION] verified={str(verified_action).lower()}", flush=True)
                response_text = tool_result.get("message", "")
                if not verified_action and not tool_result.get("expects_user_reply"):
                    from engine.assistant_response import guard_unverified_action_message
                    response_text = guard_unverified_action_message(response_text or "I couldn't verify that action.", tool_result)
                _respond_to_user(response_text or "I couldn't verify that action.", reason="tool")
                _store_conversation_turn(query, response_text or "")
                safe_eel_call("ShowHood")
                return
        except Exception as e:
            print(f"Tool registry error: {e}")

        try:
            from engine.local_skills import handle_local_skill
            skill_result = handle_local_skill(query)
            if skill_result.handled:
                _respond_to_user(skill_result.message, reason="missing_slot")
                _store_conversation_turn(query, skill_result.message)
                safe_eel_call("ShowHood")
                return
        except Exception as e:
            print(f"Local skill error: {e}")

        try:
            from engine.conversation_context import get_last_assistant_response
            if (query or "").strip().lower().rstrip(".?!") in {"repeat", "repeat that", "can you repeat", "say that again", "can you repeat that"}:
                last = get_last_assistant_response()
                print(f"[CONTEXT] repeat_last found={str(bool(last)).lower()}", flush=True)
                response = last or "I don't have anything to repeat yet."
                speak(response)
                _store_conversation_turn(query, response)
                safe_eel_call("ShowHood")
                return
        except Exception as e:
            print(f"Repeat-last error: {e}")

        try:
            from engine.app.phase3_command_bridge import Phase3CommandBridge
            bridge_result = Phase3CommandBridge.try_handle(query)
            if bridge_result.get("handled"):
                msg = bridge_result["result"].get("message", "")
                if msg:
                    speak(msg)
                _store_conversation_turn(query, msg)
                safe_eel_call("ShowHood")
                return
        except ImportError:
            pass
        except Exception as e:
            print(f"Phase 3 bridge error: {e}")

        result = route_intent(query, workflow_active=False)
        print(f"[INTENT] route={result.route} intent={result.intent} reason={result.reason}")
        brain_threshold = _env_float("INTENT_BRAIN_THRESHOLD", 0.45)

        if result.route == "greeting":
            _speak_greeting()
        elif result.route == "identity":
            _speak_identity()
        elif result.route == "brain":
            if result.confidence < brain_threshold:
                _ask_for_clarification(query, reason="low_confidence")
            else:
                _safe_chatbot(query)
        elif result.route == "local_action":
            handled = dispatch_intent(query)
            if not handled:
                _ask_for_clarification(query, reason="local_action_unclear")
        else:  # unknown
            handled = dispatch_intent(query)
            if not handled:
                if _should_clarify_unknown(query):
                    _ask_for_clarification(query, reason="unknown")
                else:
                    _safe_chatbot(query)
        _store_conversation_turn(query, _last_spoken or "")
    except Exception as e:
        print(f"Error in allCommands: {e}")
        try:
            safe_query = str(locals().get("query", message))[:200]
        except Exception:
            safe_query = str(message)[:200]
        try:
            from engine.reflection_memory import ReflectionMemory
            ReflectionMemory.store_lesson(
                failure=f"allCommands raised {type(e).__name__}: {str(e)[:160]}",
                lesson=f"When processing user input, handle {type(e).__name__} gracefully.",
                context=f"input={safe_query}",
                intent="allCommands",
                tool_name="command_dispatcher",
            )
        except Exception:
            pass

    safe_eel_call("ShowHood")


@eel.expose
def executeControlAction(action_name, entities_json=None):
    try:
        import json
        entities = json.loads(entities_json) if entities_json else {}
        if not CONTROL_AVAILABLE:
            return json.dumps({"ok": False, "message": "Control layer not available", "data": {}, "error": {"code": "CONTROL_UNAVAILABLE", "message": ""}})
        result = execute_control_action(action_name, entities)
        return json.dumps(result.to_dict())
    except Exception as e:
        import json
        return json.dumps({"ok": False, "message": "Control error", "data": {}, "error": {"code": "BRIDGE_ERROR", "message": str(e)}})


@eel.expose
def getControlStatus():
    import json
    if not CONTROL_AVAILABLE:
        return json.dumps({"available": False, "message": "Control layer not available"})
    actions = list_control_actions()
    return json.dumps({
        "available": True,
        "emergency_stop": EmergencyStop.is_engaged(),
        "actions": actions
    })


@eel.expose
def emergencyStop(reason=""):
    if CONTROL_AVAILABLE:
        EmergencyStop.engage(reason=reason or "User requested stop")
        return "Emergency stop engaged"


@eel.expose
def clearEmergencyStop():
    if CONTROL_AVAILABLE:
        EmergencyStop.clear()
        return "Emergency stop cleared"


# --- Phase 3 Backend API ---

@eel.expose
def getMemorySummary():
    try:
        from engine.memory.preference_store import PreferenceStore
        store = PreferenceStore()
        result = store.summarize()
        import json
        return json.dumps(result)
    except Exception as e:
        import json
        return json.dumps({"ok": False, "message": str(e), "data": {}, "error": {"code": "BRIDGE_ERROR", "message": str(e)}})


@eel.expose
def rememberPreference(text):
    try:
        from engine.app.phase3_command_bridge import Phase3CommandBridge
        result = Phase3CommandBridge.try_handle(text)
        import json
        if result.get("handled"):
            return json.dumps(result["result"])
        return json.dumps({"ok": False, "message": "Could not parse preference", "data": {}, "error": {"code": "NOT_HANDLED"}})
    except Exception as e:
        import json
        return json.dumps({"ok": False, "message": str(e), "data": {}, "error": {"code": "BRIDGE_ERROR", "message": str(e)}})


@eel.expose
def forgetMemory(key):
    try:
        from engine.memory.preference_store import PreferenceStore
        store = PreferenceStore()
        result = store.forget(key)
        import json
        return json.dumps(result)
    except Exception as e:
        import json
        return json.dumps({"ok": False, "message": str(e), "data": {}, "error": {"code": "BRIDGE_ERROR", "message": str(e)}})


@eel.expose
def diagnoseNexi():
    try:
        from engine.diagnostic_doctors.runtime_doctor import RuntimeDoctor
        result = RuntimeDoctor.diagnose()
        import json
        return json.dumps(result)
    except Exception as e:
        import json
        return json.dumps({"ok": False, "summary": str(e), "checks": [], "timestamp": "", "error": {"code": "BRIDGE_ERROR", "message": str(e)}})


@eel.expose
def getDashboardState():
    try:
        from engine.world_monitor_dashboard import get_dashboard_state
        import json
        return json.dumps(get_dashboard_state())
    except Exception as e:
        import json
        return json.dumps({"version": 1, "updated_at": 0, "panels": [], "error": {"code": "BRIDGE_ERROR", "message": str(e)}})


@eel.expose
def requestScreenObservation(reason):
    try:
        from engine.app.phase3_command_bridge import Phase3CommandBridge
        result = Phase3CommandBridge.try_handle(reason)
        import json
        return json.dumps(result.get("result", {}))
    except Exception as e:
        import json
        return json.dumps({"ok": False, "message": str(e), "data": {}, "error": {"code": "BRIDGE_ERROR", "message": str(e)}})


@eel.expose
def setStatus(status_text="", class_name=""):
    return safe_eel_call("setStatus", status_text, class_name)


@eel.expose
def submitUserCommand(message="", source="typed"):
    from engine.command_bus import submit_user_command
    return submit_user_command(message, source=source or "typed", mode="typed")


@eel.expose
def wakeNexiFromUi(source="ui_button"):
    from engine.nexi_wake_controller import wake_nexi
    wake_nexi(source or "ui_button")
    return "awake"


@eel.expose
def toggleNexiSleepWake():
    from engine.nexi_wake_controller import is_nexi_awake, sleep_nexi, wake_nexi
    if is_nexi_awake():
        sleep_nexi(reason="ui_button")
        return "sleeping"
    wake_nexi("ui_button")
    return "awake"


try:
    from engine.ui_state_ack import on_ui_state_ack as _on_ui_state_ack
except Exception:
    _on_ui_state_ack = None


@eel.expose
def ui_state_ack(session_id="", state="", sequence=0, label="", created_at=0.0):
    """
    Called by Mark/legacy UI JavaScript after DOM state is actually updated.

    This closes the UI connector loop:
    Python UI_SEND -> JS DOM update -> Python UI_ACK.
    """
    session_id = session_id or ""
    state = state or ""
    try:
        sequence = int(sequence or 0)
    except (TypeError, ValueError):
        sequence = 0
    label = label or ""

    try:
        if _on_ui_state_ack is not None:
            import time
            _on_ui_state_ack(
                session_id=session_id,
                state=state,
                sequence=sequence,
                created_at=float(created_at or time.time()),
                label=label,
            )

        print(f"[UI_ACK] session={session_id} state={state} sequence={sequence} label={label}")
        return {
            "ok": True,
            "session_id": session_id,
            "state": state,
            "sequence": sequence,
            "label": label,
        }

    except Exception as exc:
        print(f"[UI_ACK_ERROR] session={session_id} state={state} label={label} error={type(exc).__name__}:{exc}")
        return {
            "ok": False,
            "session_id": session_id,
            "state": state,
            "sequence": sequence,
            "label": label,
            "error": f"{type(exc).__name__}:{exc}",
        }
