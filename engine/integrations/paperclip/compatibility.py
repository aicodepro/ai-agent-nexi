"""Fail-closed capability matrix for an installed Paperclip deployment."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Callable

from .contracts import (
    CompatibilityCapability,
    CompatibilityProbes,
    PaperclipCompatibilityReport,
    SignedCompatibilityEnvelope,
    VerifiedCompatibility,
)
from .signing import (
    HMAC_SHA256,
    ReportSignatureVerifier,
    ReportSigner,
    canonical_json_bytes,
)


READ_REQUIREMENTS = frozenset(
    {"health", "authenticated_private", "companies_read", "issues_read"}
)
MUTATION_BASE_REQUIREMENTS = frozenset(
    {
        "metadata_correlation",
        "write_ahead_recovery",
        "backup_restore_probe",
        "migration_rollback_probe",
    }
)
FULL_AUTO_REQUIREMENTS = frozenset(
    {
        "governance_plugin_digest",
        "actor_restrictions",
        "policy_digest_enforcement",
        "synchronous_pre_mutation_hook",
        "synchronous_pre_dispatch_hook",
        "sandbox_driver",
        "lease_expiry_cancellation",
        "atomic_budget_reservation",
        "worker_capability_drift_gate",
    }
)
RELEASE_REQUIREMENTS = frozenset(
    {"verified_evidence", "release_gateway", "rollback_probe"}
)
MODE_REQUIREMENTS = {
    "read": READ_REQUIREMENTS,
    "full_auto": READ_REQUIREMENTS | MUTATION_BASE_REQUIREMENTS | FULL_AUTO_REQUIREMENTS,
    "release": READ_REQUIREMENTS | MUTATION_BASE_REQUIREMENTS | RELEASE_REQUIREMENTS,
}

OPERATION_SPECIFIC_REQUIREMENTS = {
    "pause_mission": frozenset(
        {
            "route:tree_hold_pause",
            "principal:tree_hold_pause",
            "reconcile:tree_hold_pause",
        }
    ),
    "cancel_mission": frozenset(
        {
            "route:tree_hold_cancel",
            "principal:tree_hold_cancel",
            "reconcile:tree_hold_cancel",
        }
    ),
}
OPERATION_REQUIREMENTS = {
    operation: READ_REQUIREMENTS | MUTATION_BASE_REQUIREMENTS | requirements
    for operation, requirements in OPERATION_SPECIFIC_REQUIREMENTS.items()
}

_BASELINE_SERVER_VERSION = "0.3.1"
_BASELINE_PLUGIN_SDK_VERSION = "1.0.0"
_BASELINE_UNAVAILABLE_HOOKS = (
    "synchronous_pre_mutation_hook",
    "synchronous_pre_dispatch_hook",
)
_PROVENANCE_FIELDS = (
    "origin",
    "server_boot_identity",
    "server_version",
    "source_revision",
    "plugin_sdk_version",
    "principal_id",
    "principal_capability_digest",
    "openapi_digest",
    "plugin_id",
    "plugin_version",
    "plugin_digest",
    "sandbox_digest",
)
_VERIFICATION_CACHE_SECONDS = 30
MAX_REPORT_AGE_SECONDS = 300
_KEY_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_HMAC_SIGNATURE = re.compile(r"^[0-9a-f]{64}$")


def build_report(probes: CompatibilityProbes) -> PaperclipCompatibilityReport:
    capabilities = {item.name: item for item in probes.capabilities}
    if (
        probes.server_version == _BASELINE_SERVER_VERSION
        and probes.plugin_sdk_version == _BASELINE_PLUGIN_SDK_VERSION
    ):
        for name in _BASELINE_UNAVAILABLE_HOOKS:
            evidence = (
                f"probe={name} result=unsupported "
                "reason=baseline_0.3.1_sdk_1.0.0"
            )
            capabilities[name] = CompatibilityCapability(name, False, evidence)

    return PaperclipCompatibilityReport(
        server_version=probes.server_version,
        plugin_sdk_version=probes.plugin_sdk_version,
        source_revision=probes.source_revision,
        origin=probes.origin,
        server_boot_identity=probes.server_boot_identity,
        principal_id=probes.principal_id,
        principal_capability_digest=probes.principal_capability_digest,
        openapi_digest=probes.openapi_digest,
        plugin_id=probes.plugin_id,
        plugin_version=probes.plugin_version,
        plugin_digest=probes.plugin_digest,
        sandbox_digest=probes.sandbox_digest,
        checked_at=probes.checked_at,
        expires_at=probes.expires_at,
        capabilities=tuple(capabilities[name] for name in sorted(capabilities)),
        provenance_complete=probes.provenance_complete,
        fixture=probes.fixture,
    )
_REPORT_FIELDS = frozenset(
    {
        "schema_version",
        "server_version",
        "plugin_sdk_version",
        "source_revision",
        "origin",
        "server_boot_identity",
        "principal_id",
        "principal_capability_digest",
        "openapi_digest",
        "plugin_id",
        "plugin_version",
        "plugin_digest",
        "sandbox_digest",
        "checked_at",
        "expires_at",
        "capabilities",
        "provenance_complete",
        "fixture",
    }
)
_CAPABILITY_FIELDS = frozenset({"name", "supported", "evidence"})
_ENVELOPE_FIELDS = frozenset(
    {"schema_version", "algorithm", "key_id", "report", "signature"}
)
def report_to_dict(report: PaperclipCompatibilityReport) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "server_version": report.server_version,
        "plugin_sdk_version": report.plugin_sdk_version,
        "source_revision": report.source_revision,
        "origin": report.origin,
        "server_boot_identity": report.server_boot_identity,
        "principal_id": report.principal_id,
        "principal_capability_digest": report.principal_capability_digest,
        "openapi_digest": report.openapi_digest,
        "plugin_id": report.plugin_id,
        "plugin_version": report.plugin_version,
        "plugin_digest": report.plugin_digest,
        "sandbox_digest": report.sandbox_digest,
        "checked_at": report.checked_at,
        "expires_at": report.expires_at,
        "capabilities": [
            {
                "name": item.name,
                "supported": item.supported,
                "evidence": item.evidence,
            }
            for item in sorted(report.capabilities, key=lambda capability: capability.name)
        ],
        "provenance_complete": report.provenance_complete,
        "fixture": report.fixture,
    }


def sign_report(
    report: PaperclipCompatibilityReport, signer: ReportSigner
) -> SignedCompatibilityEnvelope:
    unsigned = _unsigned_envelope(report, signer.key_id, signer.algorithm)
    return SignedCompatibilityEnvelope(
        key_id=signer.key_id,
        algorithm=signer.algorithm,
        report=report,
        signature=signer.sign(canonical_json_bytes(unsigned)),
    )


def envelope_to_dict(envelope: SignedCompatibilityEnvelope) -> dict[str, Any]:
    return {
        **_unsigned_envelope(envelope.report, envelope.key_id, envelope.algorithm),
        "signature": envelope.signature,
    }


def _unsigned_envelope(
    report: PaperclipCompatibilityReport, key_id: str, algorithm: str
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "algorithm": algorithm,
        "key_id": key_id,
        "report": report_to_dict(report),
    }


def parse_report(
    payload: Mapping[str, Any],
    *,
    verifier: ReportSignatureVerifier,
    now: datetime | None = None,
    max_age_seconds: float = MAX_REPORT_AGE_SECONDS,
) -> PaperclipCompatibilityReport:
    if not isinstance(payload, Mapping):
        raise ValueError("compatibility report envelope must be a JSON object")
    if set(payload) != _ENVELOPE_FIELDS:
        raise ValueError("malformed compatibility report envelope fields")
    if payload["schema_version"] != 1 or isinstance(payload["schema_version"], bool):
        raise ValueError("unsupported compatibility report schema_version")
    if payload["algorithm"] != HMAC_SHA256:
        raise ValueError("unsupported compatibility report signature algorithm")
    if not isinstance(payload["key_id"], str) or not _KEY_ID.fullmatch(payload["key_id"]):
        raise ValueError("compatibility report key_id is malformed")
    if not isinstance(payload["signature"], str) or not _HMAC_SIGNATURE.fullmatch(
        payload["signature"]
    ):
        raise ValueError("compatibility report signature is malformed")

    unsigned = {
        "schema_version": payload["schema_version"],
        "algorithm": payload["algorithm"],
        "key_id": payload["key_id"],
        "report": payload["report"],
    }
    try:
        signature_valid = verifier.verify(
            payload["key_id"], canonical_json_bytes(unsigned), payload["signature"]
        )
    except Exception as exc:
        raise ValueError("compatibility report signature verification failed") from exc
    if not signature_valid:
        raise ValueError("compatibility report signature verification failed")
    report = parse_report_body(
        payload["report"], now=now, max_age_seconds=max_age_seconds
    )
    object.__setattr__(report, "_signature_verified", True)
    return report


def parse_report_body(
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
    max_age_seconds: float = MAX_REPORT_AGE_SECONDS,
) -> PaperclipCompatibilityReport:
    if not isinstance(payload, Mapping):
        raise ValueError("compatibility report must be a JSON object")
    if set(payload) != _REPORT_FIELDS:
        raise ValueError("malformed compatibility report fields")
    if payload["schema_version"] != 1 or isinstance(payload["schema_version"], bool):
        raise ValueError("unsupported compatibility report body schema_version")

    raw_capabilities = payload["capabilities"]
    if not isinstance(raw_capabilities, list):
        raise ValueError("capabilities must be a JSON array")
    capabilities: list[CompatibilityCapability] = []
    for raw in raw_capabilities:
        if not isinstance(raw, Mapping) or set(raw) != _CAPABILITY_FIELDS:
            raise ValueError("malformed capability fields")
        capabilities.append(
            CompatibilityCapability(
                name=raw["name"],
                supported=raw["supported"],
                evidence=raw["evidence"],
            )
        )

    report = PaperclipCompatibilityReport(
        server_version=payload["server_version"],
        plugin_sdk_version=payload["plugin_sdk_version"],
        source_revision=payload["source_revision"],
        origin=payload["origin"],
        server_boot_identity=payload["server_boot_identity"],
        principal_id=payload["principal_id"],
        principal_capability_digest=payload["principal_capability_digest"],
        openapi_digest=payload["openapi_digest"],
        plugin_id=payload["plugin_id"],
        plugin_version=payload["plugin_version"],
        plugin_digest=payload["plugin_digest"],
        sandbox_digest=payload["sandbox_digest"],
        checked_at=payload["checked_at"],
        expires_at=payload["expires_at"],
        capabilities=tuple(capabilities),
        provenance_complete=payload["provenance_complete"],
        fixture=payload["fixture"],
    )
    supported = {item.name for item in report.capabilities if item.supported}
    if (
        report.server_version == _BASELINE_SERVER_VERSION
        and report.plugin_sdk_version == _BASELINE_PLUGIN_SDK_VERSION
        and supported.intersection(_BASELINE_UNAVAILABLE_HOOKS)
    ):
        raise ValueError("baseline report cannot claim unavailable synchronous hooks")

    reference_time = _utc_time(now or datetime.now(timezone.utc), "now")
    checked_at = _utc_time(report.checked_at, "checked_at")
    expires_at = _utc_time(report.expires_at, "expires_at")
    if expires_at <= reference_time:
        raise ValueError("compatibility report is expired")
    if checked_at > reference_time:
        raise ValueError("compatibility report checked_at is in the future")
    if isinstance(max_age_seconds, bool) or max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")
    if (reference_time - checked_at).total_seconds() > max_age_seconds:
        raise ValueError("compatibility report is stale")
    return report


def parse_report_json(
    raw: str,
    *,
    verifier: ReportSignatureVerifier,
    now: datetime | None = None,
    max_age_seconds: float = MAX_REPORT_AGE_SECONDS,
) -> PaperclipCompatibilityReport:
    if not isinstance(raw, str):
        raise ValueError("compatibility report JSON must be text")
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise ValueError("malformed compatibility report JSON") from exc
    return parse_report(
        payload, verifier=verifier, now=now, max_age_seconds=max_age_seconds
    )


def parse_report_body_json(
    raw: str,
    *,
    now: datetime | None = None,
    max_age_seconds: float = MAX_REPORT_AGE_SECONDS,
) -> PaperclipCompatibilityReport:
    if not isinstance(raw, str):
        raise ValueError("compatibility report JSON must be text")
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise ValueError("malformed compatibility report JSON") from exc
    return parse_report_body(payload, now=now, max_age_seconds=max_age_seconds)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate field: {name}")
        result[name] = value
    return result


def _utc_time(value: datetime | str, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a valid timestamp") from exc
    else:
        raise ValueError(f"{field_name} must be a valid timestamp")
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


class CompatibilityReportVerifier:
    """Rebind a persisted report to current live, non-secret probe provenance."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cached_report: PaperclipCompatibilityReport | None = None
        self._cached_result: VerifiedCompatibility | None = None
        self._cached_client: object | None = None

    def verify_against_live_server(
        self,
        report: PaperclipCompatibilityReport,
        client: object,
    ) -> VerifiedCompatibility:
        now = _utc_time(self._clock(), "verification clock")
        if (
            self._cached_report == report
            and self._cached_result is not None
            and self._cached_client is client
            and self._cached_result.valid
            and now < _utc_time(self._cached_result.expires_at, "verification expiry")
        ):
            return self._cached_result

        failures: list[str] = []
        if report.fixture:
            failures.append("fixture")
        if not report._signature_verified:
            failures.append("signature")
        if not report.provenance_complete:
            failures.append("provenance_complete")
        if not report.activatable:
            failures.append("activatable")
        failures.extend(
            _temporal_failures(
                "report", report.checked_at, report.expires_at, now
            )
        )

        live: CompatibilityProbes | None = None
        if isinstance(client, CompatibilityProbes):
            failures.append("live_client_required")
        else:
            try:
                probe_method = getattr(client, "compatibility_probes")
                live = probe_method()
                if not isinstance(live, CompatibilityProbes):
                    raise TypeError("live probe provider returned an invalid contract")
            except Exception:
                failures.append("live_probe_unavailable")

        if live is not None:
            for field_name in _PROVENANCE_FIELDS:
                if getattr(report, field_name) != getattr(live, field_name):
                    failures.append(field_name)
            if _canonical_capability_support(report) != _canonical_capability_support(
                build_report(live)
            ):
                failures.append("capabilities")
            if not live.provenance_complete:
                failures.append("live_provenance_complete")
            if live.fixture:
                failures.append("live_fixture")
            failures.extend(
                _temporal_failures("live", live.checked_at, live.expires_at, now)
            )

        expiries = [
            _utc_time(report.expires_at, "expires_at"),
            _utc_time(report.checked_at, "checked_at")
            + timedelta(seconds=MAX_REPORT_AGE_SECONDS),
            now + timedelta(seconds=_VERIFICATION_CACHE_SECONDS),
        ]
        if live is not None:
            expiries.append(_utc_time(live.expires_at, "live expires_at"))
            expiries.append(
                _utc_time(live.checked_at, "live checked_at")
                + timedelta(seconds=MAX_REPORT_AGE_SECONDS)
            )
        cache_expiry = min(expiries)
        valid = not failures
        result = VerifiedCompatibility(
            report=report,
            verified_at=now.isoformat(),
            expires_at=cache_expiry.isoformat(),
            valid=valid,
            failures=tuple(dict.fromkeys(failures)),
            _clock=self._clock,
        )
        self._cached_report = report if valid else None
        self._cached_result = result if valid else None
        self._cached_client = client if valid else None
        return result


def _canonical_capability_support(
    report: PaperclipCompatibilityReport,
) -> tuple[tuple[str, bool], ...]:
    return tuple(sorted((item.name, item.supported) for item in report.capabilities))


def _temporal_failures(
    prefix: str,
    checked_at_value: str,
    expires_at_value: str,
    now: datetime,
) -> tuple[str, ...]:
    checked_at = _utc_time(checked_at_value, f"{prefix} checked_at")
    expires_at = _utc_time(expires_at_value, f"{prefix} expires_at")
    failures: list[str] = []
    if expires_at <= now:
        failures.append(f"{prefix}_expired")
    if checked_at > now:
        failures.append(f"{prefix}_checked_at_future")
    elif (now - checked_at).total_seconds() > MAX_REPORT_AGE_SECONDS:
        failures.append(f"{prefix}_stale")
    return tuple(failures)
