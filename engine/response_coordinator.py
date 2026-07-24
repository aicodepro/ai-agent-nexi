"""Single response acceptance boundary for Nexi Access."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Any

from engine.assistant_response import guard_unverified_action_message, make_response


@dataclass(frozen=True)
class ResponseReceipt:
    accepted: bool
    reason: str
    request_id: str
    session_id: str
    session_epoch: float
    response: dict[str, Any] | None = None


class ResponseCoordinator:
    """Accept at most one response for a request in the current generation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest_epoch: dict[str, float] = {}
        self._accepted_requests: set[tuple[str, float, str]] = set()

    def reset(self) -> None:
        with self._lock:
            self._latest_epoch.clear()
            self._accepted_requests.clear()

    def accept(
        self,
        display_text: str,
        *,
        request_id: str = "",
        session_id: str = "",
        session_epoch: float = 0.0,
        spoken_text: str | None = None,
        expects_user_reply: bool = False,
        source: str = "assistant",
        tool_result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ResponseReceipt:
        safe_session = str(session_id or "")
        safe_epoch = float(session_epoch or 0.0)
        safe_request = str(request_id or uuid.uuid4().hex)
        key = (safe_session, safe_epoch, safe_request)

        with self._lock:
            latest = self._latest_epoch.get(safe_session, 0.0) if safe_session else 0.0
            if safe_session and safe_epoch > 0.0 and latest > safe_epoch:
                return ResponseReceipt(False, "stale_generation", safe_request, safe_session, safe_epoch)
            if key in self._accepted_requests:
                return ResponseReceipt(False, "duplicate_request", safe_request, safe_session, safe_epoch)
            if safe_session and safe_epoch > latest:
                self._latest_epoch[safe_session] = safe_epoch
                self._accepted_requests = {
                    item for item in self._accepted_requests
                    if item[0] != safe_session or item[1] >= safe_epoch
                }
            self._accepted_requests.add(key)

        guarded = guard_unverified_action_message(display_text, tool_result)
        response = make_response(
            guarded,
            spoken_text=spoken_text,
            expects_user_reply=expects_user_reply,
            source=source,
            metadata={
                **(metadata or {}),
                "request_id": safe_request,
                "session_id": safe_session,
                "session_epoch": safe_epoch,
            },
        )
        return ResponseReceipt(True, "accepted", safe_request, safe_session, safe_epoch, response)


_COORDINATOR = ResponseCoordinator()


def get_response_coordinator() -> ResponseCoordinator:
    return _COORDINATOR
