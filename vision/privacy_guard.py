import re


# Each labelled secret is "the word, plus its value if one follows". The old guard
# redacted only the LABEL ("password"), leaving the value: "password=hunter2" became
# "[REDACTED:password]=hunter2" — worse than no guard, it looks safe while leaking the
# secret. `_VAL` optionally consumes a trailing `= value` / `: value` so the value is
# redacted too, while bare "password" (no value) is still flagged. Per-label (not one
# merged pattern) so the reason names the KIND of secret — "password", "api_key".
_VAL = r"(?:\s*[:=]\s*\S+)?"
_SENSITIVE_PATTERNS = [
    (re.compile(rf"\b(?:password|passwd|pwd)\b{_VAL}", re.IGNORECASE), "password"),
    (re.compile(rf"\b(?:api[_-]?key|apikey)\b{_VAL}", re.IGNORECASE), "api_key"),
    (re.compile(rf"\bprivate[_-]?key\b{_VAL}", re.IGNORECASE), "private_key"),
    (re.compile(rf"\bsecret\b{_VAL}", re.IGNORECASE), "secret"),
    (re.compile(rf"\btoken\b{_VAL}", re.IGNORECASE), "token"),
    (re.compile(rf"\bcookies?\b{_VAL}", re.IGNORECASE), "cookie"),
    (re.compile(r"\botp\b(?:\s*[:=]?\s*\d{4,8})?", re.IGNORECASE), "otp"),
    # bare vendor keys (no label needed). Short threshold on purpose: a privacy guard
    # over on-screen text should over-redact, so it catches short test-shaped tokens
    # ("sk-mykey123") as well as full-length ones.
    (re.compile(r"\b(?:sk-ant-|sk-|gsk_|AIza|ghp_|xox[baprs]-|AKIA|hf_)[A-Za-z0-9._\-]{4,}"), "vendor_key"),
    (re.compile(r"\bBearer\s+\S{4,}", re.IGNORECASE), "bearer"),
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
        # Apply ALL patterns, not just the first match: a screen can show a password
        # AND a card number, and the old first-match-wins loop redacted only one. Run
        # substitution on the real text (patterns are case-insensitive themselves — the
        # old code searched a lowercased copy but substituted on the original, so a
        # match near case boundaries could slip through).
        redacted = text
        found = []
        for pattern, label in _SENSITIVE_PATTERNS:
            new = pattern.sub(f"[REDACTED:{label}]", redacted)
            if new != redacted:
                found.append(label)
                redacted = new
        if found:
            return {
                "sensitive_content_detected": True,
                "reason": "Sensitive content detected: " + ", ".join(dict.fromkeys(found)),
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
