import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.ui_state_manager import canonical_state, label_for


def test_wake_detected_canonical_is_online():
    assert canonical_state("wake_detected") == "online"


def test_hotword_detected_canonical_is_online():
    assert canonical_state("hotword_detected") == "online"


def test_double_clap_detected_canonical_is_online():
    assert canonical_state("double_clap_detected") == "online"


def test_wake_detected_label_is_online():
    assert label_for("wake_detected") == "ONLINE"


def test_hotword_detected_label_is_online():
    assert label_for("hotword_detected", source="hotword") == "ONLINE"


def test_double_clap_detected_label_is_online():
    assert label_for("double_clap_detected", source="double_clap") == "ONLINE"


def test_wake_detected_does_not_show_hotword_detected():
    assert label_for("wake_detected", source="hotword") == "ONLINE"
