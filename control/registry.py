"""Control action registry — stores and looks up registered actions."""

from dataclasses import dataclass, field
from typing import Callable, Any
from difflib import SequenceMatcher


@dataclass
class ControlAction:
    name: str
    handler: Callable
    risk: str = "safe"  # safe, medium, high, critical
    description: str = ""
    entities: list = field(default_factory=list)
    aliases: list = field(default_factory=list)


class ControlRegistry:
    def __init__(self):
        self._actions: dict[str, ControlAction] = {}

    def register(self, name: str, handler: Callable, risk: str = "safe",
                 description: str = "", entities: list = None, aliases: list = None):
        action = ControlAction(
            name=name, handler=handler, risk=risk,
            description=description, entities=entities or [], aliases=aliases or [],
        )
        self._actions[name.lower()] = action
        for alias in (aliases or []):
            self._actions[alias.lower()] = action

    def get(self, name: str) -> ControlAction | None:
        return self._actions.get(name.lower())

    def match(self, text: str, threshold: float = 0.6) -> ControlAction | None:
        lower = text.lower().strip()
        # Exact match
        if lower in self._actions:
            return self._actions[lower]
        # Fuzzy match
        best_score = 0.0
        best_action = None
        for key, action in self._actions.items():
            score = SequenceMatcher(None, lower, key).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_action = action
        return best_action

    def list_actions(self) -> list:
        seen = set()
        result = []
        for action in self._actions.values():
            if action.name not in seen:
                seen.add(action.name)
                result.append({"name": action.name, "risk": action.risk,
                               "description": action.description})
        return result


# Global registry
_registry = ControlRegistry()


def get_registry() -> ControlRegistry:
    return _registry


def register_defaults():
    """Register built-in control actions."""
    from control.desktop import register_desktop_controls
    from control.chrome import register_chrome_controls
    from control.file_control import register_file_controls
    register_desktop_controls(_registry)
    register_chrome_controls(_registry)
    register_file_controls(_registry)
