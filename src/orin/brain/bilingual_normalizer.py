HINDI_MAP = {
    "kholo": "open",
    "band karo": "close",
    "band kar do": "close",
    "chalu karo": "start",
    "shuru karo": "start",
    "rok do": "stop",
    "band karo": "stop",
    "dhoondo": "search",
    "khojo": "search",
    "dhundho": "search",
    "dekhao": "show",
    "dikhao": "show",
    "batao": "tell",
    "sunao": "play",
    "bhejo": "send",
    "likho": "write",
    "padho": "read",
    "badlo": "change",
    "badha do": "increase",
    "kam karo": "decrease",
    "check karo": "check",
    "janch karo": "check",
    "diagnose karo": "diagnose",
    "kya chal raha hai": "what is happening",
    "kya kar sakte ho": "what can you do",
    "status do": "give status",
}

MIXED_PHRASES = {
    "chrome kholo": "open chrome",
    "browser kholo": "open browser",
    "youtube kholo": "open youtube",
    "notepad kholo": "open notepad",
    "vscode kholo": "open vscode",
    "code kholo": "open vscode",
    "file explorer kholo": "open file explorer",
    "calculator kholo": "open calculator",
    "google pe search karo": "search google for",
    "google pe dhoondo": "search google for",
    "youtube pe search karo": "search youtube for",
    "youtube pe dhoondo": "search youtube for",
    "google pe ai news search karo": "search google for ai news",
    "folder banao": "create folder",
    "file banao": "create file",
    "downloads kholo": "open downloads",
    "documents kholo": "open documents",
    "desktop kholo": "open desktop",
    "apps dikhao": "show running apps",
    "running apps dikhao": "show running apps",
    "window dikhao": "show active window",
    "active window dikhao": "show active window",
    "sab band karo": "stop everything",
    "sab rok do": "stop everything",
    "emergency stop": "emergency stop",
    "jarvi check karo": "diagnose jarvi",
    "jarvi diagnose karo": "diagnose jarvi",
    "apne aap ko check karo": "diagnose jarvi",
    "hotword check karo": "check hotword",
    "bridge check karo": "check bridge",
    "playwright check karo": "check playwright",
}

HINDI_INTENT_PATTERNS = {
    "control_open_chrome": ["chrome kholo", "browser kholo", "krom kholo", "browzer kholo"],
    "control_open_youtube": ["youtube kholo", "yutub kholo", "you tube kholo"],
    "control_search_google": [
        "google pe search karo", "google pe dhoondo", "google pe khojo",
        "google search karo", "google pe dhundho",
    ],
    "control_search_youtube": [
        "youtube pe search karo", "youtube pe dhoondo", "youtube pe khojo",
        "youtube search karo", "youtube pe dhundho",
    ],
    "control_show_apps": ["apps dikhao", "running apps dikhao", "chalti apps dikhao"],
    "control_active_window": ["active window dikhao", "window dikhao", "kaunsi window chal rahi hai"],
    "control_focus_app": ["focus karo", "window lao", "front me lao"],
    "control_create_folder": ["folder banao", "naya folder banao", "folder create karo"],
    "control_open_folder": ["downloads kholo", "documents kholo", "desktop kholo", "folder kholo"],
    "control_emergency_stop": ["sab band karo", "sab rok do", "emergency stop", "sab freeze karo"],
    "control_status": ["kya kar sakte ho", "tumhari capabilities kya hain", "status do"],
    "open_app": ["kholo", "chalu karo", "shuru karo"],
    "close_app": ["band karo", "band kar do", "close karo"],
}


class BilingualNormalizer:
    @classmethod
    def normalize(cls, text):
        if not text or not text.strip():
            return text, "en", []
        t = text.lower().strip()
        translations = []
        for hi_phrase, en_phrase in MIXED_PHRASES.items():
            if hi_phrase in t:
                t = t.replace(hi_phrase, en_phrase)
                translations.append((hi_phrase, en_phrase))
        lang = "mixed" if translations else "en"
        for hi_word in t.split():
            if hi_word in HINDI_MAP:
                lang = "mixed"
                break
        return t, lang, translations

    @classmethod
    def get_hindi_patterns(cls, intent_name):
        return HINDI_INTENT_PATTERNS.get(intent_name, [])

    @classmethod
    def detect_language(cls, text):
        if not text:
            return "en"
        t = text.lower().strip()
        for hi_phrase in MIXED_PHRASES:
            if hi_phrase in t:
                return "mixed"
        for word in t.split():
            if word in HINDI_MAP:
                return "mixed"
        return "en"

    @classmethod
    def all_hindi_patterns(cls):
        result = {}
        for intent_name, patterns in HINDI_INTENT_PATTERNS.items():
            result[intent_name] = list(patterns)
        return result
