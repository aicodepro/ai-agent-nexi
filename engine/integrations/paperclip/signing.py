"""Canonical HMAC signing primitives for compatibility reports."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re
from typing import Any, Protocol


HMAC_SHA256 = "HMAC-SHA256"
_KEY_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SIGNATURE = re.compile(r"^[0-9a-f]{64}$")


class ReportSigner(Protocol):
    key_id: str
    algorithm: str

    def sign(self, payload: bytes) -> str: ...


class ReportSignatureVerifier(Protocol):
    def verify(self, key_id: str, payload: bytes, signature: str) -> bool: ...


@dataclass(frozen=True)
class HMACReportSigner:
    key_id: str
    _key: bytes = field(repr=False)
    algorithm: str = field(default=HMAC_SHA256, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("signing key ID must be a bounded safe identifier")
        if not isinstance(self._key, bytes) or len(self._key) < 32:
            raise ValueError("HMAC signing key must contain at least 32 bytes")

    def sign(self, payload: bytes) -> str:
        if not isinstance(payload, bytes):
            raise ValueError("signing payload must be bytes")
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def verify(self, key_id: str, payload: bytes, signature: str) -> bool:
        if key_id != self.key_id or not isinstance(signature, str):
            return False
        if not _SIGNATURE.fullmatch(signature):
            return False
        return hmac.compare_digest(self.sign(payload), signature)


def canonical_json_bytes(payload: Any) -> bytes:
    try:
        text = json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("report payload is not canonical JSON data") from exc
    return text.encode("ascii")
