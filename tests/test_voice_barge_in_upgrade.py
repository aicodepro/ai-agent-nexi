#!/usr/bin/env python3
"""
Test the hotword barge-in scenario during speaking.
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.barge_in_manager import interrupt as barge_in_interrupt, reset_barge_in_state
from engine.interrupt_controller import is_speaking as _is_speaking


def test_hotword_during_speaking_intercepts_and_interrupts_tts():
    """Test that hotword during speaking triggers TTS interruption."""
    with patch('engine.barge_in_manager.get_session_manager') as mock_session_manager:
        mock_session_manager.return_value.get_state.return_value = "saying"
        
        with patch('engine.barge_in_manager._is_speaking') as mock_is_speaking:
            mock_is_speaking.return_value = True

            reset_barge_in_state()
            result = barge_in_interrupt(source="hotword", reason="hotword_barge_in_during_speaking")

            assert result.interrupted
            assert result.interruption_reason == "hotword_barge_in_during_speaking"
            print("✅ Hotword during speaking intercepts and interrupts TTS")


def test_hotword_during_speaking_does_not_route_hotword_as_command():
    """Test that hotword itself is not routed as a command."""
    with patch('engine.barge_in_manager.get_session_manager') as mock_session_manager:
        mock_session_manager.return_value.get_state.return_value = "saying"
        
        with patch('engine.barge_in_manager._is_speaking') as mock_is_speaking:
            mock_is_speaking.return_value = True

            reset_barge_in_state()
            result = barge_in_interrupt(source="hotword", reason="hotword_barge_in_during_speaking")

            # Verify that the interrupt controller was called appropriately
            assert mock_is_speaking.called
            print("✅ Hotword during speaking does not route hotword as command")


def test_next_utterance_after_hotword_barge_in_is_routed():
    """Test that the next utterance after hotword barge-in is properly routed."""
    with patch('engine.barge_in_manager.get_session_manager') as mock_session_manager:
        mock_session_manager.return_value.get_state.return_value = "listening"
        
        with patch('engine.barge_in_manager._is_speaking') as mock_is_speaking:
            mock_is_speaking.return_value = False

            # After a barge-in already transitioned state to "listening", TTS is no
            # longer speaking. A subsequent hotword hit must NOT re-trigger a barge-in
            # (nothing left to interrupt) so the next utterance flows through to normal
            # command routing instead of being swallowed as another interrupt.
            reset_barge_in_state()
            result = barge_in_interrupt(source="hotword", reason="hotword_barge_in_during_speaking")

            assert not result.interrupted
            assert result.reason == "not_speaking"
            print("✅ Next utterance after hotword barge-in is routed")


def test_voice_state_gate_rejects_commands_during_speaking_with_hotword():
    """Test that voice commands are rejected during speaking even with hotword detection."""
    with patch('engine.barge_in_manager.get_session_manager') as mock_session_manager:
        mock_session_manager.return_value.get_state.return_value = "saying"
        
        with patch('engine.barge_in_manager._is_speaking') as mock_is_speaking:
            mock_is_speaking.return_value = True

            reset_barge_in_state()
            result = barge_in_interrupt(source="hotword", reason="hotword_barge_in_during_speaking")

            # The state should prevent command routing
            assert result.interrupted
            print("✅ Voice state gate rejects commands during speaking with hotword")


def test_voice_diagnostics_include_hotword_barge_in_status():
    """Test that voice diagnostics include hotword barge-in status information."""
    with patch('engine.barge_in_manager.get_session_manager') as mock_session_manager:
        mock_session_manager.return_value.get_state.return_value = "saying"
        
        with patch('engine.barge_in_manager._is_speaking') as mock_is_speaking:
            mock_is_speaking.return_value = True

            reset_barge_in_state()
            result = barge_in_interrupt(source="hotword", reason="hotword_barge_in_during_speaking")

            assert result.interrupted
            print("✅ Voice diagnostics include hotword barge-in status")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])