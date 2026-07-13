import os
import re
import threading
import time

from engine.control.safety import EmergencyStop
from engine.diagnostic_doctors.runtime_doctor import RuntimeDoctor
from engine.memory.preference_store import PreferenceStore
from engine.brain.autonomy_loop import AutonomyLoop
from vision.screen_observer import ScreenObserver
from vision.screen_context import detect_screen_command
from engine.app.runtime_context import get_conversation_buffer


class Phase3CommandBridge:

    _preference_store = None
    _autonomy_loop = None
    _screen_observer = None
    _last_screen_request_id = None
    _last_vision_ts = 0.0

    @classmethod
    def _vision_cooldown_s(cls):
        # Default 0 = OFF. NEXI already has an echo guard (post_tts_cleanup), so this
        # capture-dedupe is opt-in; set NEXI_VISION_COOLDOWN_MS>0 (e.g. 4000) to enable.
        try:
            return max(0.0, int(os.getenv("NEXI_VISION_COOLDOWN_MS", "0")) / 1000.0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _vision_on_cooldown(cls):
        return (time.monotonic() - cls._last_vision_ts) < cls._vision_cooldown_s()

    @classmethod
    def _mark_vision_capture(cls):
        cls._last_vision_ts = time.monotonic()

    @classmethod
    def _vision_ack(cls):
        """Immediate, non-blocking 'looking now' so feedback overlaps capture."""
        def _say():
            try:
                from engine.command import speak
                speak("Looking at your screen now.")
            except Exception:
                pass
        threading.Thread(target=_say, daemon=True).start()

    @classmethod
    def _get_preference_store(cls):
        if cls._preference_store is None:
            cls._preference_store = PreferenceStore()
        return cls._preference_store

    @classmethod
    def _get_autonomy_loop(cls):
        if cls._autonomy_loop is None:
            cls._autonomy_loop = AutonomyLoop()
        return cls._autonomy_loop

    @classmethod
    def _get_screen_observer(cls):
        if cls._screen_observer is None:
            cls._screen_observer = ScreenObserver()
        return cls._screen_observer

    @classmethod
    def try_handle(cls, query):
        if not query or not query.strip():
            return {"handled": False, "result": None}
        q = query.lower().strip()

        result = cls._try_stop_speaking(q, query)
        if result:
            return result

        result = cls._try_emergency_stop(q, query)
        if result:
            return result

        result = cls._try_conversation_buffer(q, query)
        if result:
            return result

        result = cls._try_screen_trust(q, query)
        if result:
            return result

        result = cls._try_owner_mode(q, query)
        if result:
            return result

        result = cls._try_screen_observation(q, query)
        if result:
            return result

        result = cls._try_memory(q, query)
        if result:
            return result

        result = cls._try_diagnose(q, query)
        if result:
            return result

        result = cls._try_autonomy(q, query)
        if result:
            return result

        return {"handled": False, "result": None}

    @classmethod
    def _try_stop_speaking(cls, q, original):
        try:
            from engine.voice.speech_interrupt import is_stop_speaking_command
            from engine.voice.speech_controller import (
                stop_speaking as sc_stop,
                speak as sc_speak,
                get_state as sc_get_state,
            )
            if is_stop_speaking_command(original):
                sc_stop(reason="user_requested")
                sc_speak("Stopped speaking.")
                return {
                    "handled": True,
                    "result": {
                        "ok": True,
                        "message": "Stopped speaking.",
                        "data": {"state": sc_get_state()},
                        "error": None,
                    },
                }
        except ImportError:
            pass
        return None

    @classmethod
    def _try_emergency_stop(cls, q, original):
        patterns = [
            r"^stop everything$",
            r"^emergency stop$",
            r"^sab band karo$",
            r"^sab rok do$",
            r"^freeze everything$",
            r"^halt$",
            r"^abort$",
        ]
        for pat in patterns:
            if re.search(pat, q):
                EmergencyStop.engage(reason="User requested emergency stop via Phase 3 bridge")
                return {
                    "handled": True,
                    "result": {
                        "ok": True,
                        "message": "Emergency stop engaged. All actions blocked.",
                        "data": {"emergency_stop_engaged": True},
                        "error": None,
                    },
                }
        return None

    @classmethod
    def _try_conversation_buffer(cls, q, original):
        recall_patterns = [
            r"what did i (?:just |recently )?ask",
            r"repeat (?:my )?(?:last )?question",
            r"what was my last question",
        ]
        for pat in recall_patterns:
            if re.search(pat, q):
                buf = get_conversation_buffer()
                turns = buf.get_turns()
                if not turns:
                    msg = "No conversation history yet."
                else:
                    last_user = turns[-1]["user"]
                    msg = f"Your last question was: {last_user}"
                return {
                    "handled": True,
                    "result": {
                        "ok": True,
                        "message": msg,
                        "data": {"turns": turns, "count": len(turns)},
                        "error": None,
                    },
                }

        show_patterns = [
            r"show last (?:\d+ )?chats?",
            r"conversation history",
            r"chat history dikhao",
            r"show (?:my )?conversation",
        ]
        for pat in show_patterns:
            if re.search(pat, q):
                buf = get_conversation_buffer()
                turns = buf.get_turns()
                if not turns:
                    msg = "No conversation history yet."
                else:
                    formatted = buf.get_formatted_context()
                    msg = f"Last {len(turns)} conversations:\n{formatted}"
                return {
                    "handled": True,
                    "result": {
                        "ok": True,
                        "message": msg,
                        "data": {"turns": turns, "count": len(turns)},
                        "error": None,
                    },
                }

        clear_patterns = [
            r"clear conversation memory",
            r"clear (?:my )?chat history",
            r"conversation memory clear karo",
            r"chat history clear karo",
        ]
        for pat in clear_patterns:
            if re.search(pat, q):
                buf = get_conversation_buffer()
                buf.clear()
                return {
                    "handled": True,
                    "result": {
                        "ok": True,
                        "message": "Conversation memory cleared.",
                        "data": {"cleared": True},
                        "error": None,
                    },
                }

        return None

    @classmethod
    def _try_screen_trust(cls, q, original):
        allow_patterns = [
            r"allow screen access for this session",
            r"trust screen access for this session",
            r"screen access allow karo",
            r"screen trust enable karo",
            r"screen access (?:on|enable)",
        ]
        for pat in allow_patterns:
            if re.search(pat, q):
                from vision.screen_trust import ScreenTrust
                result = ScreenTrust.set_mode("trusted_session_read_only")
                return {
                    "handled": True,
                    "result": {
                        "ok": result,
                        "message": "Screen access trusted for this session. I can read your screen without asking repeatedly.",
                        "data": ScreenTrust.to_dict(),
                        "error": None,
                    },
                }

        revoke_patterns = [
            r"revoke screen access",
            r"screen access off",
            r"screen trust (?:off|disable)",
            r"screen access disable karo",
            r"screen access hatdo",
        ]
        for pat in revoke_patterns:
            if re.search(pat, q):
                from vision.screen_trust import ScreenTrust
                ScreenTrust.reset_to_ask()
                return {
                    "handled": True,
                    "result": {
                        "ok": True,
                        "message": "Screen access trust revoked. I will ask for permission each time.",
                        "data": ScreenTrust.to_dict(),
                        "error": None,
                    },
                }

        status_patterns = [
            r"screen access status",
            r"screen trust status",
            r"screen access ka status",
        ]
        for pat in status_patterns:
            if re.search(pat, q):
                from vision.screen_trust import ScreenTrust
                info = ScreenTrust.to_dict()
                mode = info["mode"]
                trusted = info["is_trusted"]
                msg = f"Screen trust mode: {mode}. Trusted: {trusted}."
                if info["emergency_stop_active"]:
                    msg += " Emergency stop is active, trust is overridden."
                return {
                    "handled": True,
                    "result": {
                        "ok": True,
                        "message": msg,
                        "data": info,
                        "error": None,
                    },
                }

        return None

    @classmethod
    def _try_owner_mode(cls, q, original):
        enable_patterns = [
            r"owner mode (?:on|enable)",
            r"enable owner mode",
            r"owner mode enable karo",
            r"trusted mode on",
            r"enable trusted mode",
        ]
        for pat in enable_patterns:
            if re.search(pat, q):
                from vision.screen_trust import ScreenTrust
                ScreenTrust.set_owner_trusted(True)
                return {
                    "handled": True,
                    "result": {
                        "ok": True,
                        "message": "Owner trusted mode enabled. Safe actions will not require confirmation.",
                        "data": ScreenTrust.to_dict(),
                        "error": None,
                    },
                }

        disable_patterns = [
            r"owner mode (?:off|disable)",
            r"disable owner mode",
            r"owner mode disable karo",
            r"trusted mode off",
            r"disable trusted mode",
        ]
        for pat in disable_patterns:
            if re.search(pat, q):
                from vision.screen_trust import ScreenTrust
                ScreenTrust.set_owner_trusted(False)
                return {
                    "handled": True,
                    "result": {
                        "ok": True,
                        "message": "Owner trusted mode disabled. All actions will require confirmation.",
                        "data": ScreenTrust.to_dict(),
                        "error": None,
                    },
                }

        status_patterns = [
            r"owner mode status",
            r"owner status",
            r"trusted mode status",
        ]
        for pat in status_patterns:
            if re.search(pat, q):
                from vision.screen_trust import ScreenTrust
                info = ScreenTrust.to_dict()
                owner = info["owner_trusted"]
                msg = f"Owner trusted mode: {'enabled' if owner else 'disabled'}."
                if info["emergency_stop_active"]:
                    msg += " Emergency stop is active, owner trust is overridden."
                return {
                    "handled": True,
                    "result": {
                        "ok": True,
                        "message": msg,
                        "data": info,
                        "error": None,
                    },
                }

        return None

    @classmethod
    def _try_screen_observation(cls, q, original):
        screen_triggers = [
            r"screen dekho",
            r"screen dekhao",
            r"look at this screen",
            r"look at this code",
            r"kya error hai screen pe",
            r"check this terminal error",
            r"see this line",
            r"is code ko dekho",
            r"screen pe kya hai",
            r"screen read karo",
            r"check this error",
        ]
        is_screen = detect_screen_command(original)
        if not is_screen:
            for trig in screen_triggers:
                if trig in q:
                    is_screen = True
                    break
        if not is_screen:
            return None
        if EmergencyStop.is_engaged():
            return {
                "handled": True,
                "result": {
                    "ok": False,
                    "message": "Cannot observe screen while emergency stop is engaged.",
                    "data": {"type": "screen_observation", "requires_permission": False},
                    "error": {"code": "EMERGENCY_STOP", "message": "Emergency stop is engaged"},
                },
            }
        observer = cls._get_screen_observer()

        from vision.screen_trust import ScreenTrust
        if ScreenTrust.is_trusted() or ScreenTrust.is_owner_trusted():
            if cls._vision_on_cooldown():
                return {
                    "handled": True,
                    "result": {
                        "ok": True,
                        "message": "I just looked at your screen — give me a moment before capturing again.",
                        "data": {"type": "screen_observation", "cooldown": True},
                        "error": None,
                    },
                }
            cls._vision_ack()          # immediate "Looking now" (non-blocking)
            cls._mark_vision_capture()
            trusted_result = observer.request_trusted_read_only(original)
            return {
                "handled": True,
                "result": {
                    "ok": trusted_result["ok"],
                    "message": cls._format_trusted_screen_message(trusted_result),
                    "data": trusted_result.get("data", {}),
                    "error": trusted_result.get("error"),
                },
            }

        observation = observer.request_observation(original)
        request_id = observation.get("request_id", "")
        cls._last_screen_request_id = request_id
        if ScreenTrust.is_owner_trusted():
            msg = "Using trusted local read-only access."
        else:
            msg = "I need your permission to capture the screen before I can analyze it."
        return {
            "handled": True,
            "result": {
                "ok": True,
                "message": msg,
                "data": {
                    "type": "screen_observation",
                    "requires_permission": not ScreenTrust.is_owner_trusted(),
                    "request_id": request_id,
                    "observation": observation,
                },
                "error": None,
            },
        }

    @classmethod
    def _format_trusted_screen_message(cls, trusted_result):
        prefix = "Using trusted local read-only access."
        if not isinstance(trusted_result, dict):
            return f"{prefix}\n\nScreen observation could not be completed."

        if not trusted_result.get("ok"):
            detail = "Screen observation could not be completed."
            detail = trusted_result.get("summary") or trusted_result.get("message") or detail
            error = trusted_result.get("error")
            if error and str(error) not in detail:
                detail = f"{detail} {error}"
            return f"{prefix}\n\n{detail}"

        analysis = trusted_result.get("analysis") or {}
        data = trusted_result.get("data") or {}
        observation = data.get("observation") or {}
        summary_candidates = [
            trusted_result.get("summary"),
            trusted_result.get("message"),
            observation.get("summary"),
            analysis.get("summary"),
        ]
        summary_values = []
        for value in summary_candidates:
            if value and value not in summary_values:
                summary_values.append(value)
        summary = summary_values[0] if summary_values else ""
        context = observation.get("detected_context") or analysis.get("detected_context") or "unknown"
        method = observation.get("screenshot_method", "")
        error = trusted_result.get("error")

        details = []
        if method == "mock":
            details.append("Mock screen analysis is active. Real screen capture is not enabled yet.")
        if context == "unknown":
            details.append(
                "The current screen analyzer could not classify this screen yet. "
                "Real screenshot/OCR vision is not enabled in this phase."
            )
            if summary:
                details.append(
                    "I can access the screen in trusted mode, but real screen capture/OCR vision "
                    f"is not enabled in this phase. Current analyzer result: {summary}"
                )
        elif summary:
            details.append(f"Current analyzer result: {summary}")
        for extra_summary in summary_values[1:]:
            details.append(f"Additional analyzer detail: {extra_summary}")
        if context and context != "unknown":
            details.append(f"Detected screen context: {context}.")
        if error:
            details.append(f"Screen observation warning: {error}")
        if not details:
            details.append("Screen observation completed, but no analyzer summary was returned.")

        return f"{prefix}\n\n" + "\n".join(details)

    @classmethod
    def _try_memory(cls, q, original):
        forget_patterns = [
            r"forget (?:my )?(preferred\s+)?(.+)",
            r"remove (?:my )?(preferred\s+)?(.+)",
            r"delete (?:my )?(preferred\s+)?(.+)",
        ]
        for pat in forget_patterns:
            m = re.search(pat, q)
            if m:
                key_part = (m.group(1) or "") + m.group(2)
                key = key_part.strip().replace(" ", "_").lower()
                store = cls._get_preference_store()
                result = store.forget(key)
                if result["ok"]:
                    return {
                        "handled": True,
                        "result": {
                            "ok": True,
                            "message": f"Forgotten: {key}",
                            "data": {"key": key},
                            "error": None,
                        },
                    }
                return {
                    "handled": True,
                    "result": {
                        "ok": False,
                        "message": f"Could not forget: {key}",
                        "data": {"key": key},
                        "error": result.get("error"),
                    },
                }

        memory_query_patterns = [
            r"what do you remember",
            r"memory dikhao",
            r"show memories",
            r"tell me about me",
            r"what do you know about me",
            r"mera memory dikhao",
            r"kya yaad hai",
        ]
        for pat in memory_query_patterns:
            if re.search(pat, q):
                store = cls._get_preference_store()
                summary = store.summarize()
                count = summary["data"].get("count", 0)
                if count == 0:
                    msg = "I don't have any memories stored yet."
                else:
                    keys = []
                    for mem in summary["data"].get("memories", []):
                        key = mem.get("key", mem.get("key", ""))
                        sensitivity = mem.get("sensitivity", "LOW")
                        if sensitivity == "LOW":
                            keys.append(f"{key}")
                        else:
                            keys.append(f"{key} (sensitive)")
                    msg = f"I remember {count} things: {', '.join(keys)}."
                return {
                    "handled": True,
                    "result": {
                        "ok": True,
                        "message": msg,
                        "data": summary["data"],
                        "error": None,
                    },
                }

        remember_patterns = [
            r"remember (?:that\s+)?(?:my\s+)?(preferred\s+)?(\w[\w\s]{1,40}?)\s+is\s+(.+)",
            r"yaad rakho\s+(preferred\s+)?(\w[\w\s]{1,40}?)\s+(.+)",
            r"meri\s+(?:preferred\s+)?(\w[\w\s]{1,40}?)\s+(.+)(?:\s+(?:hai|hain))?",
            r"set\s+(preferred\s+)?(\w[\w\s]{1,40}?)\s+(?:to|as)\s+(.+)",
        ]
        for pat in remember_patterns:
            m = re.search(pat, q)
            if m:
                prefix = m.group(1) or ""
                key = (prefix + m.group(2)).strip().replace(" ", "_").lower()
                value = m.group(3).strip()
                store = cls._get_preference_store()
                result = store.remember(key, value)
                if result["ok"]:
                    sensitive = result["data"].get("item", {}).get("sensitivity", "LOW")
                    msg = result["message"]
                    if sensitive == "MEDIUM" or sensitive == "HIGH":
                        msg += " (requires confirmation before use)"
                    elif sensitive == "REJECTED":
                        msg = "Cannot store this. Sensitive content blocked."
                    return {
                        "handled": True,
                        "result": {
                            "ok": True,
                            "message": msg,
                            "data": result["data"],
                            "error": None,
                        },
                    }
                return {
                    "handled": True,
                    "result": {
                        "ok": False,
                        "message": result["message"],
                        "data": {},
                        "error": result.get("error"),
                    },
                }

        return None

    @classmethod
    def _try_diagnose(cls, q, original):
        specific_checks = {
            "hotword": r"check (?:the )?hotword",
            "memory": r"check (?:the )?memory",
            "computer use harness": r"check (?:the )?(?:computer[- ]use harness|computer harness|os harness)",
            "browser intelligence layer": r"check (?:the )?(?:browser intelligence(?: layer)?|browser layer)",
            "human approval queue": r"check (?:the )?(?:human approval queue|approval queue|human approval)",
            "tool verifier layer": r"check (?:the )?(?:tool verifier(?: layer)?|verifier layer|tool verification)",
            "reflection memory": r"check (?:the )?reflection memory",
            "procedure skill library": r"check (?:the )?(?:procedure skill library|procedure library|skill library|skills library)",
            "proactive monitor": r"check (?:the )?(?:proactive monitor|monitor dashboard|world monitor)",
            "conscious hud": r"check (?:the )?(?:conscious hud|hud)",
            "model router": r"check (?:the )?model (?:router|routing)",
            "bridge": r"check (?:the )?bridge",
            "playwright": r"check (?:the )?playwright",
            "vision": r"check (?:the )?vision",
            "backend": r"check (?:the )?back(?:end|ground)",
        }
        for check_name, pat in specific_checks.items():
            if re.search(pat, q):
                result = RuntimeDoctor.diagnose()
                for c in result["checks"]:
                    name = str(c.get("name", "")).lower().replace("-", " ")
                    key = str(c.get("capability_key", "")).lower().replace("_", " ")
                    if check_name in name or check_name in key:
                        if c["ok"]:
                            msg = f"{c['name']}: OK"
                        else:
                            msg = f"{c['name']}: {c.get('problem', 'Issue found')}"
                        if c.get("role"):
                            msg += f". Role: {c['role']}"
                        if c.get("safety_policy"):
                            msg += f" Safety: {c['safety_policy']}"
                        if c.get("verifier"):
                            msg += f" Verifier: {c['verifier']}"
                        if c.get("memory_rule"):
                            msg += f" Memory: {c['memory_rule']}"
                        return {
                            "handled": True,
                            "result": {"ok": c["ok"], "message": msg, "data": {"check": c}, "error": None},
                        }
                return {
                    "handled": True,
                    "result": {"ok": True, "message": f"Check: {check_name} not found in diagnostics.", "data": {}, "error": None},
                }

        full_diagnose_patterns = [
            r"diagnose (\w+|me|system)",
            r"check (\w+|me|yourself|system)",
            r"(\w+) diagnose karo",
            r"why are (?:you|u) not (?:working|responding)",
            r"health check",
        ]
        for pat in full_diagnose_patterns:
            if re.search(pat, q):
                result = RuntimeDoctor.diagnose()
                summary = result.get("summary", "")
                return {
                    "handled": True,
                    "result": {
                        "ok": result.get("ok", False),
                        "message": summary,
                        "data": {
                            "diagnosis": result,
                            "checks": result.get("checks", []),
                        },
                        "error": None,
                    },
                }

        return None

    @classmethod
    def _try_autonomy(cls, q, original):
        patterns = [
            r"plan this task",
            r"check this project",
            r"analyze this task",
            r"think and plan",
            r"what should (?:you|i) do next",
            r"create a safe plan",
            r"plan (?:a )?task",
            r"project status",
        ]
        is_autonomy = False
        for pat in patterns:
            if re.search(pat, q):
                is_autonomy = True
                break
        if not is_autonomy:
            return None

        loop = cls._get_autonomy_loop()
        if EmergencyStop.is_engaged():
            return {
                "handled": True,
                "result": {
                    "ok": False,
                    "message": "Cannot plan while emergency stop is engaged.",
                    "data": {"blocked": True},
                    "error": {"code": "EMERGENCY_STOP", "message": "Emergency stop is engaged"},
                },
            }

        goal = original
        task = loop.plan_task(goal)
        task_dict = task.to_dict() if hasattr(task, "to_dict") else {}
        risk = task_dict.get("risk_level", "SAFE")
        step_count = len(task_dict.get("steps", []))
        msg = f"Task planned. Risk: {risk}. Steps: {step_count}."
        if risk == "CRITICAL":
            msg += " This task contains critical steps and will be blocked."
        elif risk == "HIGH":
            from vision.screen_trust import ScreenTrust
            if ScreenTrust.is_owner_trusted():
                msg += " Owner trusted mode active. Safe steps will auto-execute."
            else:
                msg += " High-risk steps will require confirmation."

        return {
            "handled": True,
            "result": {
                "ok": True,
                "message": msg,
                "data": {
                    "task": task_dict,
                    "risk_level": risk,
                    "step_count": step_count,
                },
                "error": None,
            },
        }

    @classmethod
    def reset(cls):
        cls._preference_store = None
        cls._autonomy_loop = None
        cls._screen_observer = None
        cls._last_screen_request_id = None
        try:
            from engine.app.runtime_context import get_conversation_buffer
            get_conversation_buffer().clear()
        except Exception:
            pass
        try:
            from vision.screen_trust import ScreenTrust
            ScreenTrust.reset_to_ask()
        except Exception:
            pass
