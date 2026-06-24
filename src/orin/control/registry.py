from difflib import SequenceMatcher


class ControlRegistry:
    def __init__(self):
        self._functions = {}
        self._intent_map = {}
        self._keyword_map = {}

    def register(self, func, extra_keywords=None):
        self._functions[func.name] = func
        intent_lower = func.intent.lower().strip()
        self._intent_map[intent_lower] = func.name
        for kw in func.intent.lower().split():
            if len(kw) > 2:
                self._keyword_map.setdefault(kw, []).append(func.name)
        if extra_keywords:
            for kw in extra_keywords:
                kl = kw.lower().strip()
                self._keyword_map.setdefault(kl, []).append(func.name)

    def get(self, name):
        return self._functions.get(name)

    def match_by_text(self, text):
        t = text.lower().strip()
        if not t:
            return None
        for name, func in self._functions.items():
            if name.lower() in t or func.intent.lower() in t:
                return func
        candidates = set()
        for word in t.split():
            if word in self._keyword_map:
                for fn_name in self._keyword_map[word]:
                    candidates.add(fn_name)
        if len(candidates) == 1:
            return self._functions[list(candidates)[0]]
        best_func = None
        best_score = 0.0
        for name, func in self._functions.items():
            score = SequenceMatcher(None, t, func.intent.lower(), autojunk=False).ratio()
            if score > best_score:
                best_score = score
                best_func = func
        if best_score >= 0.3:
            return best_func
        return None

    def list_functions(self):
        return list(self._functions.values())

    def has_function(self, name):
        return name in self._functions
