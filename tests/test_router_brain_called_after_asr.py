from __future__ import annotations

from unittest.mock import patch



def test_router_brain_called_after_asr():
    from engine.command_bus import submit_user_command

    with patch("engine.command_bus.dispatch_unified_command") as dispatch:
        assert submit_user_command("tell me something useful", source="hotword", mode="voice")

    dispatch.assert_called_once_with("tell me something useful", source="hotword")

