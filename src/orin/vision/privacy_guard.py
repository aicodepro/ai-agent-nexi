import re


_SENSITIVE_PATTERNS = [
    (re.compile(r"password", re.IGNORECASE), "password"),
    (re.compile(r"api[_-]?key", re.IGNORECASE), "api_key"),
    (re.compile(r"\btoken\b", re.IGNORECASE), "token"),
    (re.compile(r"\bcookie[s]?\b", re.IGNORECASE), "cookie"),
    (re.compile(r"\bsecret\b", re.IGNORECASE), "secret"),
    (re.compile(r"\bsk-\w+", re.IGNORECASE), "sk-"),
    (re.compile(r"\bbearer\b", re.IGNORECASE), "bearer"),
    (re.compile(r"private[_-]?key", re.IGNORECASE), "private_key"),
    (re.compile(r"\botp\b|\bone[_-]?time[_-]?p(asswor)?d\b", re.IGNORECASE), "otp"),
    (re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"), "card_number"),
]


class PrivacyGuard:

    @staticmethod
    def analyze_text(text):
        if not text or not isinstance(text, str):
            return {
                "sensitive_content_detected": False,
                "reason": "",
                "redacted_text": text,
            }
        lower_text = text.lower()
        for pattern, label in _SENSITIVE_PATTERNS:
            if pattern.search(lower_text):
                redacted = pattern.sub(f"[REDACTED:{label}]", text)
                return {
                    "sensitive_content_detected": True,
                    "reason": f"Sensitive content detected: {label}",
                    "redacted_text": redacted,
                }
        return {
            "sensitive_content_detected": False,
            "reason": "",
            "redacted_text": text,
        }

    @staticmethod
    def check_payload(payload):
        if not payload:
            return {
                "sensitive_content_detected": False,
                "reason": "",
            }
        if isinstance(payload, dict):
            visible_text = payload.get("visible_text", "")
        else:
            visible_text = str(payload)
        return PrivacyGuard.analyze_text(visible_text)
