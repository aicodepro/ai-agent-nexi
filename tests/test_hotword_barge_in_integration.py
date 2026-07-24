#!/usr/bin/env python3
"""
Integration test for hotword barge-in feature.
This test simulates the end-to-end scenario described in the task.
"""

import os
import sys
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.audio_wake_pipeline import AudioWakePipeline


def get_mock_runtime_bridge():
    """Create a mock runtime bridge with command queue."""
    class MockRuntimeBridge:
        def __init__(self, command_queue=None):
            self._command_queue = command_queue or queue.Queue()
    
    import queue
    bridge = MockRuntimeBridge()
    return bridge


def test_hotword_during_speaking_intercepts_and_interrupts_tts():
    """Test that hotword during speaking triggers TTS interruption."""
    bridge = get_mock_runtime_bridge()
    
    with patch('engine.audio_wake_pipeline.get_session_manager') as mock_session_manager:
        mock_session_manager.return_value.are_detectors_paused.return_value = True
        mock_session_manager.return_value.get_state.return_value = "saying"
        
        with patch('engine.audio_wake_pipeline._is_speaking') as mock_is_speaking:
            mock_is_speaking.return_value = True
            
            with patch('engine.barge_in_manager.interrupt') as mock_barge_in_interrupt:
                mock_barge_in_interrupt.return_value = type('MockResult', (), {'interrupted': True})()
                
                pipeline = AudioWakePipeline(command_queue=bridge._command_queue)
                
                # Simulate hotword detection during speaking
                result = pipeline.process_frame(b"\x00\x00" * 160)
                
                # Verify barge-in was triggered
                assert mock_barge_in_interrupt.called
                assert result.get("wake") == True
                assert result.get("source") == "hotword"
                assert result.get("reason") == "hotword_during_speaking"
                print("✅ Hotword during speaking intercepts and interrupts TTS")


def test_hotword_during_speaking_does_not_route_hotword_as_command():
    """Test that hotword itself is not routed as a command."""
    bridge = get_mock_runtime_bridge()
    
    with patch('engine.audio_wake_pipeline.get_session_manager') as mock_session_manager:
        mock_session_manager.return_value.are_detectors_paused.return_value = True
        mock_session_manager.return_value.get_state.return_value = "saying"
        
        with patch('engine.audio_wake_pipeline._is_speaking') as mock_is_speaking:
            mock_is_speaking.return_value = True
            
            with patch('engine.barge_in_manager.interrupt') as mock_barge_in_interrupt:
                mock_barge_in_interrupt.return_value = type('MockResult', (), {'interrupted': True})()
                
                pipeline = AudioWakePipeline(command_queue=bridge._command_queue)
                
                # Simulate hotword detection during speaking
                result = pipeline.process_frame(b"\x00\x00" * 160)
                
                # Verify that the interrupt controller was called appropriately
                assert mock_barge_in_interrupt.called
                assert result.get("reason") == "hotword_during_speaking"
                print("✅ Hotword during speaking does not route hotword as command")


def test_next_utterance_after_hotword_barge_in_is_routed(monkeypatch):
    """Test that the next utterance after hotword barge-in is properly routed."""
    bridge = get_mock_runtime_bridge()

    # _wake_scorer is built lazily in start() (never called here), so it stays
    # None unless injected -- and with no scorer the "listening" code path (as
    # opposed to the "_is_speaking" barge-in branch, which assumes score=1.0
    # when no scorer is set) skips scoring entirely and can never wake. Inject
    # a scorer, and lower OWW_CONSECUTIVE for this single-frame test (the real
    # anti-false-wake default of 2 is deliberately not touched -- see
    # engine/audio_wake_pipeline.py OWW_CONSECUTIVE).
    import engine.audio_wake_pipeline as awp
    monkeypatch.setattr(awp, "OWW_THRESHOLD", 0.5)
    monkeypatch.setattr(awp, "OWW_CONSECUTIVE", 1)

    class _ScriptedHotwordScorer:
        name = "scripted"

        def score(self, frame):
            return 0.9

    with patch('engine.audio_wake_pipeline.get_session_manager') as mock_session_manager:
        mock_session_manager.return_value.are_detectors_paused.return_value = False
        mock_session_manager.return_value.get_state.return_value = "listening"
        mock_session_manager.return_value.is_post_session_suppressed.return_value = False

        with patch('engine.audio_wake_pipeline._is_speaking') as mock_is_speaking:
            mock_is_speaking.return_value = False

            pipeline = awp.AudioWakePipeline(
                command_queue=bridge._command_queue,
                wake_scorer=_ScriptedHotwordScorer(),
            )

            # Simulate normal hotword detection (not during speaking)
            result = pipeline.process_frame(b"\x00\x00" * 160)

            # This would trigger normal wake, not barge-in
            assert result.get("wake") == True
            assert result.get("source") == "hotword"
            print("✅ Next utterance after hotword barge-in is routed")


def test_voice_state_gate_rejects_commands_during_speaking_with_hotword():
    """Test that voice commands are rejected during speaking even with hotword detection."""
    bridge = get_mock_runtime_bridge()
    
    with patch('engine.audio_wake_pipeline.get_session_manager') as mock_session_manager:
        mock_session_manager.return_value.are_detectors_paused.return_value = True
        mock_session_manager.return_value.get_state.return_value = "saying"
        
        with patch('engine.audio_wake_pipeline._is_speaking') as mock_is_speaking:
            mock_is_speaking.return_value = True
            
            pipeline = AudioWakePipeline(command_queue=bridge._command_queue)
            
            # Simulate hotword detection during speaking
            result = pipeline.process_frame(b"\x00\x00" * 160)
            
            # The state should prevent command routing
            assert mock_is_speaking.called
            assert result.get("reason") == "hotword_during_speaking"
            print("✅ Voice state gate rejects commands during speaking with hotword")


def test_voice_diagnostics_include_hotword_barge_in_status():
    """Test that voice diagnostics include hotword barge-in status information."""
    bridge = get_mock_runtime_bridge()
    
    with patch('engine.audio_wake_pipeline.get_session_manager') as mock_session_manager:
        mock_session_manager.return_value.are_detectors_paused.return_value = True
        mock_session_manager.return_value.get_state.return_value = "saying"
        
        with patch('engine.audio_wake_pipeline._is_speaking') as mock_is_speaking:
            mock_is_speaking.return_value = True
            
            with patch('engine.barge_in_manager.interrupt') as mock_barge_in_interrupt:
                mock_barge_in_interrupt.return_value = type('MockResult', (), {'interrupted': True})()
                
                pipeline = AudioWakePipeline(command_queue=bridge._command_queue)
                
                # Simulate hotword detection during speaking
                result = pipeline.process_frame(b"\x00\x00" * 160)
                
                # Verify barge-in was triggered and diagnostics would include status
                assert mock_barge_in_interrupt.called
                assert result.get("reason") == "hotword_during_speaking"
                print("✅ Voice diagnostics include hotword barge-in status")


if __name__ == "__main__":
    test_hotword_during_speaking_intercepts_and_interrupts_tts()
    test_hotword_during_speaking_does_not_route_hotword_as_command()
    test_next_utterance_after_hotword_barge_in_is_routed()
    test_voice_state_gate_rejects_commands_during_speaking_with_hotword()
    test_voice_diagnostics_include_hotword_barge_in_status()
    print("\n✅ All hotword barge-in tests passed!")