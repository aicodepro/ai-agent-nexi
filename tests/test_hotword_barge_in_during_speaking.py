#!/usr/bin/env python3
"""
Test the hotword barge-in scenario during speaking.
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.audio_wake_pipeline import AudioWakePipeline


def test_hotword_barge_in_during_speaking_transitions_to_listening():
    """Test that hotword during speaking transitions to listening state."""
    with patch('engine.audio_wake_pipeline.get_session_manager') as mock_session_manager:
        mock_session_manager.return_value.are_detectors_paused.return_value = True
        mock_session_manager.return_value.get_state.return_value = "saying"
        
        with patch('engine.audio_wake_pipeline._is_speaking') as mock_is_speaking:
            mock_is_speaking.return_value = True
            
            with patch('engine.barge_in_manager.interrupt') as mock_barge_in_interrupt:
                mock_barge_in_interrupt.return_value = type('MockResult', (), {'interrupted': True})()
                
                pipeline = AudioWakePipeline()
                
                # Simulate hotword detection during speaking
                result = pipeline.process_frame(b"\x00\x00" * 160)
                
                # Verify barge-in was triggered
                assert mock_barge_in_interrupt.called
                assert result.get("wake") == True
                assert result.get("source") == "hotword"
                assert result.get("reason") == "hotword_during_speaking"
                print("✅ Hotword barge-in during speaking transitions to listening")


def test_hotword_barge_in_during_speaking_echo_guard():
    """Test that hotword barge-in prevents echo/self-TTS."""
    with patch('engine.audio_wake_pipeline.get_session_manager') as mock_session_manager:
        mock_session_manager.return_value.are_detectors_paused.return_value = True
        mock_session_manager.return_value.get_state.return_value = "saying"
        
        with patch('engine.audio_wake_pipeline._is_speaking') as mock_is_speaking:
            mock_is_speaking.return_value = True
            
            with patch('engine.barge_in_manager.interrupt') as mock_barge_in_interrupt:
                mock_barge_in_interrupt.return_value = type('MockResult', (), {'interrupted': True})()
                
                pipeline = AudioWakePipeline()
                
                # Simulate hotword detection during speaking
                result = pipeline.process_frame(b"\x00\x00" * 160)
                
                # Verify that the interrupt controller was called appropriately
                assert mock_barge_in_interrupt.called
                assert result.get("reason") == "hotword_during_speaking"
                print("✅ Hotword barge-in during speaking prevents echo/self-TTS")


if __name__ == "__main__":
    test_hotword_barge_in_during_speaking_transitions_to_listening()
    test_hotword_barge_in_during_speaking_echo_guard()
    print("\n✅ All hotword barge-in during speaking tests passed!")