import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
import unittest
from engine.hotword_helper import (
    is_nexi_hotword,
    check_hotword_cooldown,
    reset_hotword_cooldown,
    set_hotword_awake,
    is_hotword_awake,
    HOTWORD_COOLDOWN_SECONDS,
)


class TestIsNexiHotword(unittest.TestCase):

    def test_hotword_rejects_jar(self):
        self.assertFalse(is_nexi_hotword("jar"))

    def test_hotword_rejects_jars(self):
        self.assertFalse(is_nexi_hotword("jars"))

    def test_hotword_rejects_java(self):
        self.assertFalse(is_nexi_hotword("java"))

    def test_hotword_rejects_service(self):
        self.assertFalse(is_nexi_hotword("service"))

    def test_hotword_rejects_harvest(self):
        self.assertFalse(is_nexi_hotword("harvest"))

    def test_hotword_rejects_empty(self):
        self.assertFalse(is_nexi_hotword(""))
        self.assertFalse(is_nexi_hotword("   "))

    def test_hotword_rejects_nonsense(self):
        self.assertFalse(is_nexi_hotword("asdfgh"))
        self.assertFalse(is_nexi_hotword("nexisss"))

    def test_hotword_accepts_nexi(self):
        self.assertTrue(is_nexi_hotword("nexi"))

    def test_hotword_accepts_hey_nexi(self):
        self.assertTrue(is_nexi_hotword("hey nexi"))

    def test_hotword_accepts_hey_nexi_case(self):
        self.assertTrue(is_nexi_hotword("Hey Nexi"))

    def test_hotword_accepts_jervis(self):
        self.assertTrue(is_nexi_hotword("jervis"))

    def test_hotword_accepts_hey_jervis(self):
        self.assertTrue(is_nexi_hotword("hey jervis"))

    def test_hotword_accepts_jarves(self):
        self.assertTrue(is_nexi_hotword("jarves"))

    def test_hotword_accepts_hey_jarves(self):
        self.assertTrue(is_nexi_hotword("hey jarves"))

    def test_hotword_rejects_jar_in_sentence(self):
        self.assertFalse(is_nexi_hotword("open the jar"))
        self.assertFalse(is_nexi_hotword("where is the jar"))


class TestHotwordCooldown(unittest.TestCase):

    def setUp(self):
        reset_hotword_cooldown()

    def test_cooldown_allows_first_detection(self):
        self.assertTrue(check_hotword_cooldown())

    def test_cooldown_blocks_repeat_detection(self):
        self.assertTrue(check_hotword_cooldown())
        self.assertFalse(check_hotword_cooldown())

    def test_cooldown_expires_after_delay(self):
        self.assertTrue(check_hotword_cooldown())
        time.sleep(HOTWORD_COOLDOWN_SECONDS + 0.1)
        self.assertTrue(check_hotword_cooldown())

    def test_awake_state_toggle(self):
        self.assertFalse(is_hotword_awake())
        set_hotword_awake(True)
        self.assertTrue(is_hotword_awake())
        set_hotword_awake(False)
        self.assertFalse(is_hotword_awake())


class TestHotwordAcceptRejectMatrix(unittest.TestCase):

    def test_all_accepts(self):
        accepts = [
            "nexi", "Nexi", "NEXI",
            "hey nexi", "hey Nexi",
            "jervis", "Jervis",
            "jarves", "Jarves",
            "say nexi", "please nexi",
        ]
        for text in accepts:
            self.assertTrue(is_nexi_hotword(text), f"should accept: {text}")

    def test_all_rejects(self):
        rejects = [
            "jar", "jars", "java", "service", "harvest",
            "", "   ", "nexisss", "jarv", "jari",
            "jarvi", "nexi_extra", "hello world",
            "open the jar", "where is my jar",
        ]
        for text in rejects:
            self.assertFalse(is_nexi_hotword(text), f"should reject: {text}")


if __name__ == "__main__":
    unittest.main()
