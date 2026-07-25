"""Generate a signed, fail-closed Paperclip compatibility report."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.integrations.paperclip.compatibility import (  # noqa: E402
    build_report,
    envelope_to_dict,
    parse_report_body_json,
    sign_report,
)
from engine.integrations.paperclip.contracts import (  # noqa: E402
    CompatibilityCapability,
    CompatibilityProbes,
    PaperclipCompatibilityReport,
)
from engine.integrations.paperclip.signing import (  # noqa: E402
    HMACReportSigner,
    ReportSigner,
    canonical_json_bytes,
)


DEFAULT_BASE_URL = "http://127.0.0.1:3100/api"
MAX_RESPONSE_BYTES = 1024 * 1024
FIXTURE_NAMES = ("compatibility_probes.json", "probes.json", "report.json")
_SAFE_PROVENANCE_TEXT = re.compile(r"^[A-Za-z0-9_.:@/+:-]{1,256}$")
_SECRETISH_VALUE = re.compile(
    r"(?i)^(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|"
    r"github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9_-]{8,}|"
    r"AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,})$"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a Paperclip compatibility report without mutation probes."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--fixture-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--disposable-company-id")
    return parser


def _validate_base_url(base_url: str) -> str:
    if not isinstance(base_url, str):
        raise ValueError("base URL must be a loopback API origin")
    parts = urlsplit(base_url)
    try:
        is_loopback = parts.hostname == "localhost" or ipaddress.ip_address(
            parts.hostname or ""
        ).is_loopback
        parts.port
    except ValueError as exc:
        raise ValueError("base URL must be a loopback API origin") from exc
    if (
        parts.scheme != "http"
        or not is_loopback
        or parts.path.rstrip("/") != "/api"
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise ValueError("base URL must be a loopback API origin")
    return base_url.rstrip("/")


class LiveReadProbeClient:
    """The Task 1 live surface: three bounded, read-only JSON requests."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        session: requests.Session | None = None,
        clock=None,
    ) -> None:
        self._base_url = _validate_base_url(base_url)
        if not isinstance(token, str) or not token:
            raise ValueError("live mode requires a token")
        self._token = token
        self._session = session or requests.Session()
        self._session.trust_env = False
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def compatibility_probes(self) -> CompatibilityProbes:
        health = self._get_json("health")
        openapi = self._get_json("openapi.json")
        principal = self._get_json("cli-auth/me")
        now = self._clock().astimezone(timezone.utc)

        paths = openapi.get("paths")
        paths = paths if isinstance(paths, dict) else {}
        principal_capabilities = principal.get("capabilities")
        principal_capabilities = (
            sorted(item for item in principal_capabilities if isinstance(item, str))
            if isinstance(principal_capabilities, list)
            else []
        )
        companies_route = _has_get_route(paths, "/companies")
        issues_route = _has_get_route(paths, "/issues/{issue_id}")
        companies_principal = "companies:read" in principal_capabilities
        issues_principal = "issues:read" in principal_capabilities
        health_supported = health.get("status") in {"ok", "ready", "healthy"}
        authenticated_private = (
            health.get("deployment_mode") == "authenticated"
            and health.get("exposure") == "private"
        )

        capabilities = (
            _capability("health", health_supported),
            _capability("authenticated_private", authenticated_private),
            _capability("companies_read", companies_route and companies_principal),
            _capability("issues_read", issues_route and issues_principal),
            _capability("openapi", True),
            _capability("authenticated_principal", bool(_safe_text(principal, "id"))),
            _capability("synchronous_pre_mutation_hook", False, "baseline_or_unproven"),
            _capability("synchronous_pre_dispatch_hook", False, "baseline_or_unproven"),
        )
        unproven_digest = hashlib.sha256(b"unproven").hexdigest()
        return CompatibilityProbes(
            server_version=_safe_text(health, "server_version", "unknown"),
            plugin_sdk_version=_safe_text(health, "plugin_sdk_version", "unknown"),
            source_revision=_safe_text(health, "source_revision", "unknown"),
            origin=self._base_url,
            server_boot_identity=_safe_text(health, "boot_id", "unknown"),
            principal_id=_safe_text(principal, "id", "unknown"),
            principal_capability_digest=_digest(principal_capabilities),
            openapi_digest=_digest(openapi),
            plugin_id="unproven",
            plugin_version="unproven",
            plugin_digest=unproven_digest,
            sandbox_digest=unproven_digest,
            checked_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=5)).isoformat(),
            capabilities=capabilities,
            provenance_complete=False,
            fixture=False,
        )

    def _get_json(self, route: str) -> dict[str, Any]:
        try:
            response = self._session.get(
                f"{self._base_url}/{route}",
                headers={"Authorization": f"Bearer {self._token}"},
                allow_redirects=False,
                stream=True,
                timeout=(2.0, 10.0),
            )
        except requests.RequestException as exc:
            raise RuntimeError("live read probe request failed") from exc
        try:
            if 300 <= response.status_code < 400:
                raise RuntimeError("live read probe rejected a redirect")
            if response.status_code < 200 or response.status_code >= 300:
                raise RuntimeError("live read probe returned a non-success status")
            body = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise RuntimeError("live read probe response exceeded 1 MiB")
            try:
                parsed = json.loads(bytes(body), object_pairs_hook=_unique_json_object)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("live read probe returned malformed JSON") from exc
            if not isinstance(parsed, dict):
                raise RuntimeError("live read probe returned a non-object JSON value")
            return parsed
        finally:
            response.close()


def _capability(
    name: str, supported: bool, reason: str | None = None
) -> CompatibilityCapability:
    result = "supported" if supported else "unsupported"
    evidence = f"probe={name} result={result}"
    if reason:
        evidence += f" reason={reason}"
    return CompatibilityCapability(name, supported, evidence)


def _has_get_route(paths: Mapping[str, Any], suffix: str) -> bool:
    for path, methods in paths.items():
        if isinstance(path, str) and path.endswith(suffix) and isinstance(methods, dict):
            if any(isinstance(method, str) and method.lower() == "get" for method in methods):
                return True
    return False


def _safe_text(payload: Mapping[str, Any], field: str, default: str = "") -> str:
    value = payload.get(field)
    if (
        isinstance(value, str)
        and _SAFE_PROVENANCE_TEXT.fullmatch(value)
        and not _SECRETISH_VALUE.fullmatch(value)
    ):
        return value
    return default


def _digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeError("live read probe returned duplicate JSON fields")
        result[key] = value
    return result


def _load_fixture(fixture_dir: Path, base_url: str) -> PaperclipCompatibilityReport:
    if not fixture_dir.is_dir():
        raise ValueError("fixture directory does not exist")
    candidates = [
        fixture_dir / name
        for name in FIXTURE_NAMES
        if (fixture_dir / name).is_file()
    ]
    if len(candidates) != 1:
        raise ValueError("fixture directory must contain exactly one supported fixture file")
    fixture_path = candidates[0]
    if fixture_path.stat().st_size > MAX_RESPONSE_BYTES:
        raise ValueError("fixture input exceeds 1 MiB")
    report = parse_report_body_json(fixture_path.read_text(encoding="utf-8"))
    if report.origin != _validate_base_url(base_url):
        raise ValueError("fixture origin does not match --base-url")
    return replace(report, fixture=True)


def _resolve_live_signer(
    signer: ReportSigner | None, environment: Mapping[str, str]
) -> ReportSigner:
    if signer is not None:
        return signer
    key = environment.get("PAPERCLIP_COMPATIBILITY_SIGNING_KEY", "")
    if not key:
        raise RuntimeError("live mode requires PAPERCLIP_COMPATIBILITY_SIGNING_KEY")
    key_id = environment.get("PAPERCLIP_COMPATIBILITY_SIGNING_KEY_ID", "paperclip-local")
    return HMACReportSigner(key_id, key.encode("utf-8"))


def _write_report(
    output: Path, report: PaperclipCompatibilityReport, signer: ReportSigner
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    envelope = sign_report(report, signer)
    try:
        temporary.write_text(
            json.dumps(envelope_to_dict(envelope), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    signer: ReportSigner | None = None,
    session: requests.Session | None = None,
) -> int:
    args = _parser().parse_args(argv)
    environment = os.environ if environ is None else environ
    try:
        if args.fixture_dir is not None:
            if signer is None:
                raise RuntimeError("fixture mode requires an injected signing test signer")
            report = _load_fixture(args.fixture_dir, args.base_url)
            report_signer = signer
        else:
            token = environment.get("PAPERCLIP_API_TOKEN", "")
            if not token:
                raise RuntimeError("live mode requires PAPERCLIP_API_TOKEN")
            report_signer = _resolve_live_signer(signer, environment)
            client = LiveReadProbeClient(args.base_url, token, session=session)
            report = build_report(client.compatibility_probes())
        _write_report(args.output, report, report_signer)
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(f"paperclip compatibility check failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
