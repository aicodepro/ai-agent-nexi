import re
from src.orin.brain.bilingual_normalizer import BilingualNormalizer
from src.orin.brain.speech_recovery import SpeechRecovery
from src.orin.brain.action_planner import ActionPlanner
from src.orin.brain.action_verifier import ActionVerifier
from src.orin.control.safety import EmergencyStop

try:
    from engine.intents import match_intent
    LEGACY_INTENTS = True
except ImportError:
    LEGACY_INTENTS = False


_ENGLISH_CONTROL_PATTERNS = {
    "control_open_chrome": ["open chrome", "launch chrome", "start chrome"],
    "control_open_youtube": ["open youtube", "launch youtube", "start youtube"],
    "control_search_google": ["search google for", "google search for", "search on google"],
    "control_search_youtube": ["search youtube for", "youtube search for", "search on youtube"],
    "control_show_apps": ["show running apps", "list apps", "show apps", "running apps"],
    "control_active_window": ["active window", "what window is active", "current window", "show active window"],
    "control_emergency_stop": ["stop everything", "emergency stop", "freeze everything"],
    "control_create_folder": ["create folder", "new folder", "folder banao"],
    "control_open_folder": ["open downloads", "open documents", "open desktop", "open folder"],
}


class IntentBrain:
    def __init__(self):
        self._normalizer = BilingualNormalizer()
        self._recovery = SpeechRecovery()

    def process(self, raw_query):
        if not raw_query or not raw_query.strip():
            return self._empty_result(raw_query)
        corrected_query, corrections = self._recovery.recover(raw_query)
        normalized_query, language, translations = self._normalizer.normalize(corrected_query)
        intent_name, confidence, entities = self._match_intent(corrected_query, normalized_query)
        if not intent_name:
            return {
                "raw_query": raw_query,
                "corrected_query": corrected_query,
                "language": language,
                "intent": "",
                "skill": "",
                "function": "",
                "confidence": 0.0,
                "entities": entities,
                "missing_fields": [],
                "risk_level": "SAFE",
                "privacy_sensitivity": "LOW",
                "requires_confirmation": False,
                "requires_follow_up": True,
                "follow_up_question": "I didn't understand that. Could you repeat?",
                "steps": [],
                "user_facing_summary": "Command not recognized.",
            }
        plan = ActionPlanner.plan(
            intent_name, entities=entities, confidence=confidence,
            corrected_query=corrected_query,
        )
        plan["raw_query"] = raw_query
        plan["corrected_query"] = corrected_query
        plan["language"] = language
        plan["intent"] = intent_name
        plan["user_facing_summary"] = self._make_summary(intent_name, plan)
        plan = ActionVerifier.verify(plan)
        return plan

    def _match_intent(self, corrected_query, normalized_query):
        intent_name, entities = self._match_hindi_patterns(corrected_query)
        if intent_name:
            return intent_name, 0.9, entities
        intent_name, entities = self._match_english_control_patterns(normalized_query)
        if intent_name:
            return intent_name, 0.85, entities
        if LEGACY_INTENTS:
            intent, score = match_intent(normalized_query)
            if intent:
                entities = self._extract_entities(normalized_query, intent.name)
                return intent.name, score, entities
        intent_name, entities = self._match_control_registry(normalized_query)
        if intent_name:
            return intent_name, 0.7, entities
        return None, 0.0, {}

    def _match_english_control_patterns(self, query):
        q = query.lower().strip()
        for intent_name, patterns in _ENGLISH_CONTROL_PATTERNS.items():
            for pattern in patterns:
                if pattern in q:
                    entities = self._extract_entities(q, intent_name)
                    return intent_name, entities
        return None, {}

    def _match_hindi_patterns(self, query):
        all_patterns = BilingualNormalizer.all_hindi_patterns()
        q = query.lower().strip()
        for intent_name, patterns in all_patterns.items():
            for pattern in patterns:
                if pattern in q:
                    entities = self._extract_entities(q, intent_name)
                    return intent_name, entities
        return None, {}

    def _match_control_registry(self, query):
        try:
            from src.orin.control import match_control_action
            func = match_control_action(query)
            if func:
                entities = self._extract_entities(query, func.name)
                return func.name, entities
        except Exception:
            pass
        return None, {}

    def _extract_entities(self, query, intent_name):
        entities = {}
        q = query.lower().strip()
        if intent_name in ("control_search_youtube", "search_youtube"):
            for prefix in ["search youtube for ", "youtube search ", "youtube pe search karo ", "youtube pe dhoondo ", "on youtube "]:
                if prefix in q:
                    entities["query"] = q.split(prefix)[-1].strip()
                    break
        elif intent_name in ("control_search_google", "search_google"):
            for prefix in ["search google for ", "google search ", "google pe search karo ", "google pe dhoondo ", "look up ", "search for "]:
                if prefix in q:
                    entities["query"] = q.split(prefix)[-1].strip()
                    break
        elif intent_name in ("control_open_url",):
            for prefix in ["go to ", "open url ", "navigate to ", "take me to "]:
                if prefix in q:
                    entities["url"] = q.split(prefix)[-1].strip()
                    break
        elif intent_name in ("open_app", "control_focus_app", "close_app", "focus_app"):
            for prefix in ["open ", "launch ", "start ", "focus ", "switch to ", "close ", "kill "]:
                if q.startswith(prefix):
                    entities["app_name"] = q[len(prefix):].strip()
                    break
        elif intent_name in ("control_create_folder", "create_folder"):
            for prefix in ["called ", "named ", "folder banao ", "naya folder "]:
                if prefix in q:
                    entities["folder_name"] = q.split(prefix)[-1].strip()
                    break
            if "location" not in entities:
                if "download" in q:
                    entities["location"] = "downloads"
                elif "document" in q:
                    entities["location"] = "documents"
                else:
                    entities["location"] = "desktop"
        elif intent_name in ("control_open_folder", "open_folder"):
            if "download" in q:
                entities["location"] = "downloads"
            elif "document" in q:
                entities["location"] = "documents"
            else:
                entities["location"] = "desktop"
        return entities

    def _make_summary(self, intent_name, plan):
        function = plan.get("function", "")
        summaries = {
            "open_chrome": "Opening Chrome.",
            "open_url": "Opening the URL.",
            "open_youtube": "Opening YouTube.",
            "search_youtube": "Searching YouTube.",
            "search_google": "Searching Google.",
            "list_apps": "Showing running apps.",
            "get_active_window": "Getting active window.",
            "focus_app": "Switching to the app.",
            "create_folder": "Creating folder.",
            "open_folder": "Opening folder.",
            "open_app": "Opening the app.",
            "close_app": "Closing the app.",
            "emergency_stop": "Stopped. New actions are blocked.",
            "diagnose": "Running diagnostics.",
            "check_hotword": "Checking hotword.",
            "check_bridge": "Checking bridge.",
            "check_playwright": "Checking Playwright.",
            "list_control_actions": "Here's what I can do.",
        }
        return summaries.get(function, f"Executing {function}." if function else "Processing.")

    def _empty_result(self, raw_query):
        return {
            "raw_query": raw_query or "",
            "corrected_query": "",
            "language": "en",
            "intent": "",
            "skill": "",
            "function": "",
            "confidence": 0.0,
            "entities": {},
            "missing_fields": [],
            "risk_level": "SAFE",
            "privacy_sensitivity": "LOW",
            "requires_confirmation": False,
            "requires_follow_up": False,
            "follow_up_question": "",
            "steps": [],
            "user_facing_summary": "",
        }
