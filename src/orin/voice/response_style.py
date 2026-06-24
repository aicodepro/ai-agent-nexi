STYLE_TEMPLATES = {
    "acknowledgement": {
        "en": ["{msg}", "Got it. {msg}", "Sure, {msg}"],
        "hi": ["{msg}", "जी, {msg}", "हाँ, {msg}"],
        "mixed": ["{msg}", "जी, {msg}", "Okay, {msg}"],
    },
    "thinking": {
        "en": ["Hmm, {msg}", "Let me think... {msg}", "{msg}"],
        "hi": ["{msg}", "सोचता हूँ... {msg}", "{msg}"],
        "mixed": ["{msg}", "Let me check... {msg}", "{msg}"],
    },
    "executing": {
        "en": ["{msg}", "Doing that now. {msg}", "On it. {msg}"],
        "hi": ["{msg}", "अभी कर रहा हूँ। {msg}", "जी, {msg}"],
        "mixed": ["{msg}", "कर रहा हूँ। {msg}", "On it. {msg}"],
    },
    "success": {
        "en": ["{msg}", "Done! {msg}", "There we go. {msg}"],
        "hi": ["{msg}", "हो गया! {msg}", "जी, {msg}"],
        "mixed": ["{msg}", "Done! {msg}", "हो गया! {msg}"],
    },
    "blocked": {
        "en": ["{msg}", "Sorry, {msg}", "Can't do that. {msg}"],
        "hi": ["{msg}", "माफ़ करें, {msg}", "यह नहीं हो सकता। {msg}"],
        "mixed": ["{msg}", "Sorry, {msg}", "यह नहीं हो सकता। {msg}"],
    },
    "error": {
        "en": ["{msg}", "Oops! {msg}", "Something went wrong. {msg}"],
        "hi": ["{msg}", "दोष! {msg}", "कुछ गड़बड़ हो गई। {msg}"],
        "mixed": ["{msg}", "Oops! {msg}", "कुछ गड़बड़ हो गई। {msg}"],
    },
    "confirmation": {
        "en": ["{msg}", "Just checking — {msg}", "Quick question: {msg}"],
        "hi": ["{msg}", "बस पुष्टि कर रहा हूँ — {msg}", "{msg}"],
        "mixed": ["{msg}", "Just checking — {msg}", "पुष्टि करें — {msg}"],
    },
}


class ResponseStyle:
    @classmethod
    def format(cls, style, message, language="en"):
        lang = language if language in STYLE_TEMPLATES.get(style, {}) else "en"
        templates = STYLE_TEMPLATES.get(style, STYLE_TEMPLATES["acknowledgement"])
        lang_templates = templates.get(lang, templates.get("en", ["{msg}"]))
        template = lang_templates[0]
        return template.replace("{msg}", message)

    @classmethod
    def get_styles(cls):
        return list(STYLE_TEMPLATES.keys())

    @classmethod
    def get_template(cls, style, language="en"):
        templates = STYLE_TEMPLATES.get(style, {})
        return templates.get(language, templates.get("en", ["{msg}"]))
