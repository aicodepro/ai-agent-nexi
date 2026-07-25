"""Provider-neutral contracts for agent runtimes supervised by Nexi."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class RuntimeCapabilities:
    provider_id: str
    transport: str
    structured_events: bool
    native_sessions: bool
    native_cancel: bool
    project_scoping: str
    agent_injection: str
    isolation: str
    enforced_read_only: bool = False
    enforced_tool_policy: bool = False
    studio_eligible: bool = False
    limitations: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentRunRequest:
    task: str
    project_dir: str
    owner_id: str
    permission_mode: str = "acceptEdits"
    agent_name: str | None = None
    agents_json: str | None = None
    resume_session_id: str | None = None
    fork_session: bool = False
    control_cwd: str | None = None
    extra_args: tuple[str, ...] = ()
    provider_options: dict[str, Any] = field(default_factory=dict)
    # What KIND of work this is ("architecture", "implementation", "docs", ...). The
    # adapter uses it to size the model to the job: heavy reasoning/coding gets a strong
    # model, light stages get a cheap free one. Empty = unspecified (free-first default).
    # Without this the adapters had nothing to read and every stage ran on one model.
    task_kind: str = ""


@dataclass(frozen=True)
class AgentEvent:
    provider_id: str
    owner_id: str
    sequence: int
    kind: str
    payload: dict[str, Any]
    native_type: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "provider_id": self.provider_id,
            "owner_id": self.owner_id,
            "sequence": self.sequence,
            "kind": self.kind,
            "native_type": self.native_type,
            "payload": self.payload,
        }


class AgentRuntimeAdapter(Protocol):
    provider_id: str
    capabilities: RuntimeCapabilities

    def available(self) -> bool: ...

    def validate_session_id(self, value: str | None) -> str: ...

    def execute(
        self,
        request: AgentRunRequest,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]: ...

    def stop(self, owner_id: str | None = None) -> bool: ...
