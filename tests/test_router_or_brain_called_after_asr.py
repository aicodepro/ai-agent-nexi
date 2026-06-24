from __future__ import annotations

from unittest.mock import patch


def test_router_or_brain_called_after_asr():
    from engine.command_bus import submit_user_command

    with patch("engine.command_bus.dispatch_unified_command") as dispatch:
        assert submit_user_command("explain machine learning", source="hotword", mode="voice")

    dispatch.assert_called_once_with("explain machine learning", source="hotword")

