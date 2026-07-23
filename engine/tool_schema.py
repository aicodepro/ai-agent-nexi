from __future__ import annotations

import json
from typing import Any, Callable, Optional
from dataclasses import dataclass, field, asdict

ToolHandler = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = False
    enum: Optional[list[str]] = None
    default: Any = None


@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    returns: str = "dict"
    category: str = "general"
    safety: str = "low"
    requires_confirmation: bool = False
    handler: Optional[str] = None
    aliases: tuple[str, ...] = ()
    examples: list[str] = field(default_factory=list)
    enabled: bool = True

    def to_openai_tool(self) -> dict[str, Any]:
        properties = {}
        required = []
        for p in self.parameters:
            prop = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def to_anthropic_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self._input_schema(),
        }

    def _input_schema(self) -> dict[str, Any]:
        properties = {}
        required = []
        for p in self.parameters:
            prop = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    tool: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def ok(data: Any = None, tool: str = "", **kw) -> ToolResult:
        return ToolResult(success=True, data=data, tool=tool, **kw)

    @staticmethod
    def fail(error: str, tool: str = "", **kw) -> ToolResult:
        return ToolResult(success=False, error=error, tool=tool, **kw)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSchema] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._alias_map: dict[str, str] = {}

    def register(self, schema: ToolSchema, handler: Optional[ToolHandler] = None) -> None:
        self._tools[schema.name] = schema
        if handler:
            self._handlers[schema.name] = handler
        for alias in schema.aliases:
            self._alias_map[alias] = schema.name

    def get(self, name: str) -> Optional[ToolSchema]:
        resolved = self._alias_map.get(name, name)
        return self._tools.get(resolved)

    def resolve(self, name_or_alias: str) -> Optional[str]:
        if name_or_alias in self._tools:
            return name_or_alias
        return self._alias_map.get(name_or_alias)

    def handler(self, name: str) -> Optional[ToolHandler]:
        resolved = self.resolve(name)
        if not resolved:
            return None
        return self._handlers.get(resolved)

    def execute(self, name: str, **params) -> ToolResult:
        import time
        t0 = time.time()
        resolved = self.resolve(name)
        if not resolved:
            return ToolResult.fail(f"Unknown tool: {name}", tool=name)
        schema = self._tools.get(resolved)
        if not schema or not schema.enabled:
            return ToolResult.fail(f"Tool disabled: {resolved}", tool=name)
        handler = self._handlers.get(resolved)
        if not handler:
            return ToolResult.fail(f"No handler for: {resolved}", tool=name)
        try:
            result = handler(**params)
            elapsed = (time.time() - t0) * 1000
            if isinstance(result, dict):
                return ToolResult.ok(data=result.get("data", result), tool=resolved, duration_ms=elapsed)
            if isinstance(result, ToolResult):
                result.tool = resolved
                result.duration_ms = elapsed
                return result
            return ToolResult.ok(data=result, tool=resolved, duration_ms=elapsed)
        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            return ToolResult.fail(f"{type(e).__name__}: {e}", tool=resolved, duration_ms=elapsed)

    def list_tools(self, category: Optional[str] = None) -> list[ToolSchema]:
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    def count(self) -> int:
        return len(self._tools)

    def capabilities_manifest(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "parameters": [{"name": p.name, "type": p.type, "required": p.required} for p in t.parameters],
            }
            for t in self._tools.values()
            if t.enabled
        ]


def _spec_to_schema(spec) -> ToolSchema:
    from engine.tool_registry import ToolSpec
    if not isinstance(spec, ToolSpec):
        raise TypeError(f"Expected ToolSpec, got {type(spec)}")
    params = []
    for slot in spec.required_slots:
        params.append(ToolParameter(name=slot, type="string", description=f"Required: {slot}", required=True))
    for slot in spec.optional_slots:
        params.append(ToolParameter(name=slot, type="string", description=f"Optional: {slot}", required=False))
    return ToolSchema(
        name=spec.name,
        description=spec.description,
        parameters=params,
        category=spec.category,
        safety=spec.safety,
        requires_confirmation=spec.requires_confirmation,
        handler=spec.handler,
        aliases=spec.aliases,
        examples=spec.examples,
        enabled=spec.enabled,
        returns="dict",
    )
