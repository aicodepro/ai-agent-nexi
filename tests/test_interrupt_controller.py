import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_interrupt_requested_while_speaking():
    from engine import interrupt_controller as ic
    ic.clear_interrupt()
    ic.set_speaking(True)
    ic.request_interrupt("typed", "new command")
    assert ic.should_interrupt() is True
    assert ic.is_speaking() is True
    ic.clear_interrupt()
    ic.set_speaking(False)


def test_hotword_interrupts_tts():
    from engine import interrupt_controller as ic
    from engine.nexi_wake_controller import wake_nexi
    ic.set_speaking(True)
    with patch("engine.interrupt_controller.request_interrupt") as mock_interrupt:
        wake_nexi("hotword")
    mock_interrupt.assert_called_once_with(source="hotword", reason="wake")
    ic.set_speaking(False)


def test_sleep_interrupts_tts():
    from engine import interrupt_controller as ic
    from engine.nexi_wake_controller import sleep_nexi
    ic.set_speaking(True)
    with patch("engine.interrupt_controller.request_interrupt") as mock_interrupt:
        sleep_nexi("command")
    mock_interrupt.assert_called_once_with(source="sleep", reason="command")
    ic.set_speaking(False)
