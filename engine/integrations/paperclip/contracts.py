"""Immutable compatibility contracts owned by Nexi."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import ipaddress
import re
from typing import Callable
from urllib.parse import urlsplit

from .signing import HMAC_SHA256


_CAPABILITY_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_HMAC_SIGNATURE = re.compile(r"^[0-9a-f]{64}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_PROVENANCE_TEXT = re.compile(r"^[A-Za-z0-9_.:@/+:-]{1,256}$")
_EVIDENCE_VALUE = re.compile(r"^[A-Za-z0-9_.:/-]{1,256}$")
_VENDOR_SECRET = re.compile(
    r"(?i)^(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|"
    r"github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9_-]{8,}|"
    r"AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,})$"
)
_EVIDENCE_KEYS = frozenset({"probe", "result", "reason"})
_EVIDENCE_RESULTS = frozenset({"supported", "unsupported", "passed", "failed", "unknown"})
_EVIDENCE_REASONS = frozenset(
    {"baseline_0.3.1_sdk_1.0.0", "baseline_or_unproven"}
)


def _timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_provenance(value: object) -> None:
    string_fields = (
        "server_version",
        "plugin_sdk_version",
        "source_revision",
        "server_boot_identity",
        "principal_id",
        "plugin_id",
        "plugin_version",
    )
    for field_name in string_fields:
        field_value = getattr(value, field_name)
        if (
            not isinstance(field_value, str)
            or not _PROVENANCE_TEXT.fullmatch(field_value)
            or _VENDOR_SECRET.fullmatch(field_value)
        ):
            raise ValueError(f"{field_name} must be a bounded safe identifier")

    if not isinstance(value.origin, str):
        raise ValueError("origin must be an HTTP loopback API origin")
    parts = urlsplit(value.origin)
    try:
        host_is_loopback = parts.hostname == "localhost" or ipaddress.ip_address(
            parts.hostname or ""
        ).is_loopback
    except ValueError:
        host_is_loopback = False
    if (
        parts.scheme != "http"
        or not host_is_loopback
        or parts.path.rstrip("/") != "/api"
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise ValueError("origin must be an HTTP loopback API origin")
    try:
        parts.port
    except ValueError as exc:
        raise ValueError("origin must contain a valid loopback port") from exc

    for field_name in (
        "principal_capability_digest",
        "openapi_digest",
        "plugin_digest",
        "sandbox_digest",
    ):
        if not isinstance(getattr(value, field_name), str) or not _SHA256.fullmatch(
            getattr(value, field_name)
        ):
            raise ValueError(f"{field_name} must be a SHA-256 hex digest")

    checked_at = _timestamp(value.checked_at, "checked_at")
    expires_at = _timestamp(value.expires_at, "expires_at")
    if expires_at <= checked_at:
        raise ValueError("expires_at must be later than checked_at")

    if not isinstance(value.capabilities, tuple):
        raise ValueError("capabilities must be a tuple")
    names: set[str] = set()
    for capability in value.capabilities:
        if not isinstance(capability, CompatibilityCapability):
            raise ValueError("capabilities must contain CompatibilityCapability values")
        if capability.name in names:
            raise ValueError(f"duplicate capability: {capability.name}")
        names.add(capability.name)

    for field_name in ("provenance_complete", "fixture"):
        if not isinstance(getattr(value, field_name), bool):
            raise ValueError(f"{field_name} must be a boolean")


@dataclass(frozen=True)
class CompatibilityCapability:
    name: str
    supported: bool
    evidence: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _CAPABILITY_NAME.fullmatch(self.name):
            raise ValueError("capability name must use a bounded safe identifier")
        if not isinstance(self.supported, bool):
            raise ValueError("capability supported must be a boolean")
        if (
            not isinstance(self.evidence, str)
            or not self.evidence
            or len(self.evidence) > 1024
        ):
            raise ValueError("capability evidence must use structured allowlisted fields")
        fields: dict[str, str] = {}
        for item in self.evidence.split(" "):
            if item.count("=") != 1:
                raise ValueError("capability evidence must use structured allowlisted fields")
            key, value = item.split("=", 1)
            if (
                key not in _EVIDENCE_KEYS
                or key in fields
                or not _EVIDENCE_VALUE.fullmatch(value)
                or _VENDOR_SECRET.fullmatch(value)
            ):
                raise ValueError("capability evidence must use structured allowlisted fields")
            fields[key] = value
        if (
            fields.get("probe") != self.name
            or fields.get("result") not in _EVIDENCE_RESULTS
            or (
                "reason" in fields
                and fields["reason"] not in _EVIDENCE_REASONS
            )
        ):
            raise ValueError("capability evidence must use structured allowlisted fields")


@dataclass(frozen=True)
class CompatibilityProbes:
    server_version: str
    plugin_sdk_version: str
    source_revision: str
    origin: str
    server_boot_identity: str
    principal_id: str
    principal_capability_digest: str
    openapi_digest: str
    plugin_id: str
    plugin_version: str
    plugin_digest: str
    sandbox_digest: str
    checked_at: str
    expires_at: str
    capabilities: tuple[CompatibilityCapability, ...]
    provenance_complete: bool
    fixture: bool = False

    def __post_init__(self) -> None:
        _validate_provenance(self)


@dataclass(frozen=True)
class PaperclipCompatibilityReport:
    server_version: str
    plugin_sdk_version: str
    source_revision: str
    origin: str
    server_boot_identity: str
    principal_id: str
    principal_capability_digest: str
    openapi_digest: str
    plugin_id: str
    plugin_version: str
    plugin_digest: str
    sandbox_digest: str
    checked_at: str
    expires_at: str
    capabilities: tuple[CompatibilityCapability, ...]
    provenance_complete: bool
    fixture: bool
    _signature_verified: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_provenance(self)
        supported = {item.name for item in self.capabilities if item.supported}
        unavailable_hooks = {
            "synchronous_pre_mutation_hook",
            "synchronous_pre_dispatch_hook",
        }
        if (
            self.server_version == "0.3.1"
            and self.plugin_sdk_version == "1.0.0"
            and supported.intersection(unavailable_hooks)
        ):
            raise ValueError("baseline cannot claim unavailable synchronous hooks")

    @property
    def activatable(self) -> bool:
        return (
            self._signature_verified
            and self.provenance_complete
            and not self.fixture
            and self._is_current()
        )

    def allows(self, mode: str) -> bool:
        from .compatibility import MODE_REQUIREMENTS

        requirements = MODE_REQUIREMENTS.get(mode)
        if requirements is None or not self._can_activate():
            return False
        supported = {item.name for item in self.capabilities if item.supported}
        return requirements <= supported

    def allows_operation(self, operation: str) -> bool:
        from .compatibility import OPERATION_REQUIREMENTS

        operation_requirements = OPERATION_REQUIREMENTS.get(operation)
        if operation_requirements is None or not self._can_activate():
            return False
        supported = {item.name for item in self.capabilities if item.supported}
        return operation_requirements <= supported

    def _can_activate(self) -> bool:
        return self.activatable

    def _is_current(self) -> bool:
        try:
            checked_at = datetime.fromisoformat(self.checked_at.replace("Z", "+00:00"))
            expires_at = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        if checked_at.tzinfo is None or expires_at.tzinfo is None:
            return False
        now = datetime.now(timezone.utc)
        age_seconds = (now - checked_at.astimezone(timezone.utc)).total_seconds()
        return 0 <= age_seconds <= 300 and now < expires_at.astimezone(timezone.utc)


@dataclass(frozen=True)
class SignedCompatibilityEnvelope:
    key_id: str
    report: PaperclipCompatibilityReport
    signature: str
    algorithm: str = HMAC_SHA256
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1 or isinstance(self.schema_version, bool):
            raise ValueError("unsupported signed envelope schema version")
        if self.algorithm != HMAC_SHA256:
            raise ValueError("unsupported signed envelope algorithm")
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("signed envelope key ID is malformed")
        if not isinstance(self.report, PaperclipCompatibilityReport):
            raise ValueError("signed envelope report is malformed")
        if not isinstance(self.signature, str) or not _HMAC_SIGNATURE.fullmatch(
            self.signature
        ):
            raise ValueError("signed envelope signature is malformed")


@dataclass(frozen=True)
class VerifiedCompatibility:
    report: PaperclipCompatibilityReport
    verified_at: str
    expires_at: str
    valid: bool
    failures: tuple[str, ...] = ()
    _clock: Callable[[], datetime] = field(
        default=lambda: datetime.now(timezone.utc), repr=False, compare=False
    )

    @property
    def activatable(self) -> bool:
        try:
            expires_at = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            now = self._clock()
        except (TypeError, ValueError):
            return False
        if expires_at.tzinfo is None or now.tzinfo is None:
            return False
        return self.valid and self.report.activatable and now < expires_at

    def allows(self, mode: str) -> bool:
        return self.valid and self.activatable and self.report.allows(mode)

    def allows_operation(self, operation: str) -> bool:
        return (
            self.valid
            and self.activatable
            and self.report.allows_operation(operation)
        )
