import re

PHONETIC_CORRECTIONS = {
    "male": "mail",
    "send male": "send mail",
    "roll": "rohit",
    "sent male": "send mail",
    "gmale": "gmail",
    "g male": "gmail",
    "you tube": "youtube",
    "yutub": "youtube",
    "youtub": "youtube",
    "utube": "youtube",
    "chrom": "chrome",
    "krom": "chrome",
    "browzer": "browser",
    "not pad": "notepad",
    "note pad": "notepad",
    "vs code": "vscode",
    "v s code": "vscode",
    "explorer": "file explorer",
    "calc": "calculator",
    "kalkulator": "calculator",
    "gugal": "google",
    "googl": "google",
    "foulder": "folder",
    "foldar": "folder",
    "serch": "search",
    "sarch": "search",
    "opn": "open",
    "opean": "open",
    "opan": "open",
    "cloz": "close",
    "clsoe": "close",
    "diagnos": "diagnose",
    "diagnoz": "diagnose",
    "jervis": "jarvi",
    "nexi": "jarvi",
    "ervis": "jarvi",
    "stop everthing": "stop everything",
    "stop every thing": "stop everything",
}

CONTEXT_CORRECTIONS = {
    "send": {"male": "mail", "gmale": "gmail", "g male": "gmail"},
    "open": {"male": "mail", "krom": "chrome"},
    "search": {"gugal": "google", "googl": "google"},
}

_MULTI_WORD_KEYS = [k for k in PHONETIC_CORRECTIONS if " " in k]
_SINGLE_WORD_KEYS = [k for k in PHONETIC_CORRECTIONS if " " not in k]


class SpeechRecovery:
    @classmethod
    def recover(cls, text):
        if not text or not text.strip():
            return text, []
        t = text.lower().strip()
        corrections = []
        for wrong in _MULTI_WORD_KEYS:
            right = PHONETIC_CORRECTIONS[wrong]
            if wrong in t:
                t = t.replace(wrong, right)
                corrections.append((wrong, right))
        words = t.split()
        for i, word in enumerate(words):
            if i > 0:
                prev = words[i - 1]
                if prev in CONTEXT_CORRECTIONS:
                    ctx_map = CONTEXT_CORRECTIONS[prev]
                    if word in ctx_map:
                        words[i] = ctx_map[word]
                        corrections.append((word, ctx_map[word]))
                for wrong in _SINGLE_WORD_KEYS:
                    right = PHONETIC_CORRECTIONS[wrong]
                    if word == wrong:
                        words[i] = right
                        corrections.append((wrong, right))
                        break
        t = " ".join(words)
        return t, corrections

    @classmethod
    def recover_query(cls, text):
        corrected, corrections = cls.recover(text)
        return corrected
