from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DiagnosticCapabilitySpec:
    feature_id: int
    key: str
    name: str
    role: str
    safety_policy: str
    verifier: str
    memory_rule: str
    diagnostic_output: str
    modules: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    command: str = ""
    fix: str = ""


@dataclass(frozen=True)
class DiagnosticCapabilityStatus:
    feature_id: int
    key: str
    name: str
    status: str
    ok: bool
    detail: str
    role: str
    safety_policy: str
    verifier: str
    memory_rule: str
    diagnostic_output: str
    command: str = ""
    fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CAPABILITY_SPECS: tuple[DiagnosticCapabilitySpec, ...] = (
    DiagnosticCapabilitySpec(
        feature_id=8,
        key="computer_use_harness",
        name="Computer-Use Harness",
        role="Observe and act on local Windows desktop state through registered tools.",
        safety_policy="Read-only OS awareness is low risk; desktop-changing actions must pass safety_gate and confirmation policy.",
        verifier="Tool results must return verified=true, and OS probes must return observed process/window/system data.",
        memory_rule="Do not store transient window titles or process lists; store only explicit user preferences or verified failures.",
        diagnostic_output="Reports OS-awareness modules, permission gating, and registered computer-use tools.",
        modules=("engine.os_awareness", "engine.safety_gate", "engine.control.permission_manager"),
        tools=("get_active_window", "what_am_i_working_on", "get_system_state", "why_is_pc_slow"),
        command="check computer use harness",
        fix="Restore engine.os_awareness, engine.safety_gate, and permission manager wiring.",
    ),
    DiagnosticCapabilitySpec(
        feature_id=9,
        key="browser_intelligence_layer",
        name="Browser Intelligence Layer",
        role="Route browser intents to safe browser/navigation tools without direct UI focus dependency.",
        safety_policy="Navigation is medium risk; destructive browser actions require registered tool safety metadata.",
        verifier="Browser tools must be registered, selected by aliases, and verified by the tool-result verifier.",
        memory_rule="Do not store browsing contents by default; store only explicit user preferences or failed-route lessons.",
        diagnostic_output="Reports browser tool registration, router visibility, and Playwright availability separately.",
        modules=("engine.tool_registry", "engine.groq_intent_router_v2"),
        tools=("browser_new_tab", "browser_close_tab", "browser_refresh", "browser_back", "browser_forward", "browser_history", "browser_fullscreen"),
        command="check browser intelligence layer",
        fix="Restore browser tool registrations and router capability manifest visibility.",
    ),
    DiagnosticCapabilitySpec(
        feature_id=10,
        key="human_approval_queue_v2",
        name="Human Approval Queue v2",
        role="Hold high-risk actions until explicit user approval is captured and audited.",
        safety_policy="SAFE/MEDIUM may auto-approve; HIGH requires confirmation unless owner-trusted; CRITICAL stays policy-blocked.",
        verifier="PermissionManager must expose high-risk prompts, critical prompts, pending decisions, and audit logging.",
        memory_rule="Store approval audit events, not private prompt content or secrets.",
        diagnostic_output="Reports permission manager importability and presence of high/critical confirmation prompts.",
        modules=("engine.control.permission_manager", "engine.control.safety"),
        command="check human approval queue",
        fix="Restore PermissionManager prompt maps and pending decision handling.",
    ),
    DiagnosticCapabilitySpec(
        feature_id=11,
        key="tool_verifier_layer",
        name="Tool Verifier Layer",
        role="Prevent Nexi from claiming an action completed until the result is independently verified.",
        safety_policy="Unverified successes are downgraded to safe failure language.",
        verifier="verify_tool_result() must normalize raw tool output and preserve raw_success vs verified status.",
        memory_rule="Record failed verification as tool-usage history and reflection lessons, not as user facts.",
        diagnostic_output="Reports verifier function availability and tool registry integration.",
        modules=("engine.tool_result_verifier", "engine.tool_registry", "engine.tool_usage_intelligence"),
        command="check tool verifier layer",
        fix="Restore engine.tool_result_verifier.verify_tool_result and execute_tool integration.",
    ),
    DiagnosticCapabilitySpec(
        feature_id=12,
        key="reflection_memory",
        name="Reflection Memory",
        role="Persist lessons from corrections, low-confidence routes, and failed tool attempts.",
        safety_policy="Reflection writes must redact sensitive text and skip unsafe content.",
        verifier="ReflectionMemory.count(), recall_similar(), and reflection event storage must be importable.",
        memory_rule="Store generalized lessons and next actions; never store credentials, tokens, or raw sensitive text.",
        diagnostic_output="Reports reflection modules and data/memory storage readiness.",
        modules=("engine.reflection_memory", "engine.reflection_engine", "engine.memory_safety"),
        files=("data/memory",),
        command="check reflection memory",
        fix="Restore reflection modules and ensure data/memory exists.",
    ),
    DiagnosticCapabilitySpec(
        feature_id=13,
        key="procedure_skill_library",
        name="Procedure / Skill Library",
        role="Expose repeatable procedures, local skills, and tool cards to the router.",
        safety_policy="Each skill/tool needs explicit risk metadata, required slots, and confirmation requirements.",
        verifier="Registered tools and manifest entries must validate before router exposure.",
        memory_rule="Store skill-selection success/failure statistics, not private user content.",
        diagnostic_output="Reports local skill directory, registry count, and manifest loader availability.",
        modules=("engine.tool_registry", "engine.tool_manifest_loader"),
        files=("agent/skills",),
        command="check procedure skill library",
        fix="Restore agent/skills and tool manifest loader wiring.",
    ),
    DiagnosticCapabilitySpec(
        feature_id=14,
        key="proactive_monitor",
        name="Proactive Monitor",
        role="Summarize runtime, memory, tool, route, brain, and wake state for dashboards.",
        safety_policy="Monitor is read-only and must not trigger autonomous actions without a separate approval path.",
        verifier="WorldMonitorDashboard must return JSON-safe panels with timestamps and counts.",
        memory_rule="Use live runtime summaries; store only aggregated lessons and explicit monitor preferences.",
        diagnostic_output="Reports dashboard aggregator and presence-state readiness.",
        modules=("engine.world_monitor_dashboard", "engine.presence_state", "engine.diagnostics"),
        command="check proactive monitor",
        fix="Restore world monitor dashboard and presence state modules.",
    ),
    DiagnosticCapabilitySpec(
        feature_id=15,
        key="conscious_hud",
        name="Conscious HUD",
        role="Render visible assistant state, diagnostics, and wake/speech activity to the desktop UI.",
        safety_policy="HUD is display-only; Python runtime state remains the source of truth.",
        verifier="Eel bridge and HUD assets must exist, and UI state updates must use canonical backend state.",
        memory_rule="HUD should display current state only; it must not persist screen or transcript content by default.",
        diagnostic_output="Reports HUD assets, UI adapter, state manager, and dashboard bridge availability.",
        modules=("engine.ui_adapter", "engine.ui_state_manager", "engine.runtime_bridge"),
        files=("www_mark/hud_orb.js", "www_mark/controller.js"),
        command="check conscious hud",
        fix="Restore HUD assets and UI state bridge functions.",
    ),
)


def _module_exists(module_name: str) -> bool:
    try:
        return find_spec(module_name) is not None
    except Exception:
        return False


def _file_exists(path: str) -> bool:
    return (ROOT / path).exists()


def _registered_tools() -> set[str]:
    try:
        from engine.tool_registry import registered_tool_names

        return set(registered_tool_names())
    except Exception:
        return set()


def _extra_detail(spec: DiagnosticCapabilitySpec) -> list[str]:
    details: list[str] = []
    if spec.key == "human_approval_queue_v2":
        try:
            permission_manager = importlib.import_module("engine.control.permission_manager")
            high = getattr(permission_manager, "_HIGH_CONFIRMATION_PROMPTS", {})
            critical = getattr(permission_manager, "_CRITICAL_CONFIRMATION_PROMPTS", {})
            details.append(f"approval_prompts high={len(high)} critical={len(critical)}")
        except Exception as exc:
            details.append(f"approval_prompts_error={type(exc).__name__}")
    elif spec.key == "reflection_memory":
        try:
            from engine.reflection_memory import ReflectionMemory

            details.append(f"lessons={ReflectionMemory.count()}")
        except Exception as exc:
            details.append(f"lessons_error={type(exc).__name__}")
    elif spec.key == "procedure_skill_library":
        try:
            from engine.tool_registry import registered_tool_names

            details.append(f"registered_tools={len(registered_tool_names())}")
        except Exception as exc:
            details.append(f"registered_tools_error={type(exc).__name__}")
    elif spec.key == "proactive_monitor":
        try:
            module = importlib.import_module("engine.world_monitor_dashboard")

            has_dashboard = hasattr(module, "WorldMonitorDashboard")
            details.append(f"dashboard_class={str(has_dashboard).lower()}")
        except Exception as exc:
            details.append(f"dashboard_error={type(exc).__name__}")
    return details


def _status_for(spec: DiagnosticCapabilitySpec) -> DiagnosticCapabilityStatus:
    missing_modules = [name for name in spec.modules if not _module_exists(name)]
    missing_files = [path for path in spec.files if not _file_exists(path)]
    registered = _registered_tools() if spec.tools else set()
    missing_tools = [name for name in spec.tools if name not in registered]
    extras = _extra_detail(spec)

    missing_parts = []
    if missing_modules:
        missing_parts.append("modules=" + ",".join(missing_modules))
    if missing_files:
        missing_parts.append("files=" + ",".join(missing_files))
    if missing_tools:
        missing_parts.append("tools=" + ",".join(missing_tools))

    ok = not missing_parts
    status = "ready" if ok else "degraded"
    detail_parts = ["all dependencies present"] if ok else ["missing " + "; ".join(missing_parts)]
    detail_parts.extend(extras)

    return DiagnosticCapabilityStatus(
        feature_id=spec.feature_id,
        key=spec.key,
        name=spec.name,
        status=status,
        ok=ok,
        detail="; ".join(part for part in detail_parts if part),
        role=spec.role,
        safety_policy=spec.safety_policy,
        verifier=spec.verifier,
        memory_rule=spec.memory_rule,
        diagnostic_output=spec.diagnostic_output,
        command=spec.command,
        fix=spec.fix,
    )


def check_diagnostic_capabilities() -> list[dict[str, Any]]:
    return [_status_for(spec).to_dict() for spec in CAPABILITY_SPECS]


def get_diagnostic_capability(name_or_key: str) -> dict[str, Any] | None:
    target = " ".join(str(name_or_key or "").strip().lower().replace("_", " ").replace("-", " ").split())
    if not target:
        return None
    for spec in CAPABILITY_SPECS:
        keys = {
            " ".join(spec.key.replace("_", " ").split()).lower(),
            " ".join(spec.name.replace("-", " ").split()).lower(),
            str(spec.feature_id),
        }
        if target in keys or any(target in key for key in keys):
            return _status_for(spec).to_dict()
    return None


def format_diagnostic_capabilities(name_or_key: str = "") -> str:
    items = [get_diagnostic_capability(name_or_key)] if name_or_key else check_diagnostic_capabilities()
    present = [item for item in items if item]
    if not present:
        return "No matching Nexi diagnostic capability found."
    lines = ["Nexi capability diagnostics:"]
    for item in present:
        lines.append(f"{item['feature_id']}. {item['name']}: {item['status']} - {item['detail']}")
        lines.append(f"Role: {item['role']}")
        lines.append(f"Safety: {item['safety_policy']}")
        lines.append(f"Verifier: {item['verifier']}")
        lines.append(f"Memory: {item['memory_rule']}")
        lines.append(f"Diagnostic: {item['diagnostic_output']}")
    return "\n".join(lines)
