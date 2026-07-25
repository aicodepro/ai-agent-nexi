import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import threading
from engine.memory.conversation_buffer import ConversationBuffer


class TestConversationBufferInit(unittest.TestCase):
    def test_starts_empty(self):
        buf = ConversationBuffer()
        self.assertEqual(buf.count(), 0)
        self.assertEqual(buf.get_turns(), [])
        self.assertEqual(buf.get_context(), [])

    def test_max_turns_default(self):
        buf = ConversationBuffer()
        self.assertEqual(buf.max_turns, 5)

    def test_max_turns_custom(self):
        buf = ConversationBuffer(max_turns=3)
        self.assertEqual(buf.max_turns, 3)


class TestConversationBufferAppend(unittest.TestCase):
    def test_append_one_turn(self):
        buf = ConversationBuffer()
        result = buf.append_turn("hello", "hi there")
        self.assertEqual(buf.count(), 1)
        self.assertIn("user", result)
        self.assertIn("assistant", result)
        self.assertIn("timestamp", result)
        self.assertEqual(result["user"], "hello")
        self.assertEqual(result["assistant"], "hi there")

    def test_append_multiple_turns(self):
        buf = ConversationBuffer()
        buf.append_turn("q1", "a1")
        buf.append_turn("q2", "a2")
        buf.append_turn("q3", "a3")
        self.assertEqual(buf.count(), 3)

    def test_stores_max_5_turns(self):
        buf = ConversationBuffer()
        for i in range(7):
            buf.append_turn(f"question {i}", f"answer {i}")
        self.assertEqual(buf.count(), 5)

    def test_keeps_latest_turns(self):
        buf = ConversationBuffer()
        for i in range(7):
            buf.append_turn(f"question {i}", f"answer {i}")
        turns = buf.get_turns()
        self.assertEqual(turns[0]["user"], "question 2")
        self.assertEqual(turns[-1]["user"], "question 6")

    def test_get_turns_returns_copy(self):
        buf = ConversationBuffer()
        buf.append_turn("q", "a")
        turns1 = buf.get_turns()
        turns2 = buf.get_turns()
        self.assertEqual(turns1, turns2)
        turns1.append({"extra": True})
        self.assertEqual(buf.count(), 1)

    def test_evicted_turns_roll_into_a_bounded_summary(self):
        buf = ConversationBuffer(max_turns=2)
        buf.append_turn("q1", "a1")
        buf.append_turn("q2", "a2")
        buf.append_turn("q3", "a3")

        self.assertEqual([turn["user"] for turn in buf.get_turns()], ["q2", "q3"])
        self.assertIn("User: q1", buf.get_summary())
        self.assertIn("Earlier conversation summary:", buf.get_formatted_context())
        for i in range(100):
            buf.append_turn(f"safe question {i} " + "x" * 100, "safe answer")
        self.assertLessEqual(len(buf.get_summary()), 2000)


class TestConversationBufferFormat(unittest.TestCase):
    def test_get_formatted_context(self):
        buf = ConversationBuffer()
        buf.append_turn("hello", "hi there")
        formatted = buf.get_formatted_context()
        self.assertIn("User: hello", formatted)
        self.assertIn("Nexi: hi there", formatted)

    def test_get_formatted_context_multiple(self):
        buf = ConversationBuffer()
        buf.append_turn("q1", "a1")
        buf.append_turn("q2", "a2")
        formatted = buf.get_formatted_context()
        lines = formatted.strip().split("\n")
        self.assertEqual(len(lines), 4)

    def test_get_formatted_context_empty(self):
        buf = ConversationBuffer()
        formatted = buf.get_formatted_context()
        self.assertEqual(formatted, "")


class TestConversationBufferClear(unittest.TestCase):
    def test_clear(self):
        buf = ConversationBuffer()
        buf.append_turn("q", "a")
        buf.clear()
        self.assertEqual(buf.count(), 0)
        self.assertEqual(buf.get_turns(), [])

    def test_clear_empty(self):
        buf = ConversationBuffer()
        buf.clear()
        self.assertEqual(buf.count(), 0)


class TestConversationBufferSecurity(unittest.TestCase):
    def test_password_blocked(self):
        buf = ConversationBuffer()
        buf.append_turn("my password is secret123", "ok")
        turns = buf.get_turns()
        self.assertEqual(turns[0]["user"], "[Content blocked]")

    def test_api_key_blocked(self):
        buf = ConversationBuffer()
        buf.append_turn("api_key = sk-abc123def456", "ok")
        turns = buf.get_turns()
        self.assertEqual(turns[0]["user"], "[Content blocked]")

    def test_token_blocked(self):
        buf = ConversationBuffer()
        buf.append_turn("auth_token = ghp_abc123def456token", "ok")
        turns = buf.get_turns()
        self.assertEqual(turns[0]["user"], "[Content blocked]")

    def test_cookie_blocked(self):
        buf = ConversationBuffer()
        buf.append_turn("cookie = session_id=abc123xyz", "ok")
        turns = buf.get_turns()
        self.assertEqual(turns[0]["user"], "[Content blocked]")

    def test_otp_blocked(self):
        buf = ConversationBuffer()
        buf.append_turn("otp = 123456", "ok")
        turns = buf.get_turns()
        self.assertEqual(turns[0]["user"], "[Content blocked]")

    def test_secret_blocked(self):
        buf = ConversationBuffer()
        buf.append_turn("secret = my_secret_value_here", "ok")
        turns = buf.get_turns()
        self.assertEqual(turns[0]["user"], "[Content blocked]")

    def test_no_raw_password_in_context(self):
        buf = ConversationBuffer()
        buf.append_turn("my password is secret123", "ok")
        formatted = buf.get_formatted_context()
        self.assertNotIn("secret123", formatted)

    def test_no_raw_api_key_in_context(self):
        buf = ConversationBuffer()
        buf.append_turn("api_key = sk-abc123def456", "ok")
        formatted = buf.get_formatted_context()
        self.assertNotIn("sk-abc123def456", formatted)

    def test_email_redacted_not_blocked(self):
        buf = ConversationBuffer()
        buf.append_turn("email me at test@example.com", "ok")
        turns = buf.get_turns()
        self.assertNotIn("test@example.com", turns[0]["user"])
        self.assertIn("[REDACTED]", turns[0]["user"])

    def test_safe_text_stored_normally(self):
        buf = ConversationBuffer()
        buf.append_turn("I prefer Chrome browser", "Sure")
        turns = buf.get_turns()
        self.assertEqual(turns[0]["user"], "I prefer Chrome browser")

    def test_empty_text_stored(self):
        buf = ConversationBuffer()
        buf.append_turn("", "")
        self.assertEqual(buf.count(), 1)
        self.assertEqual(buf.get_turns()[0]["user"], "")

    def test_raw_screen_dump_is_not_stored_or_summarized(self):
        raw = "screenshot image data: private terminal contents " + "x" * 200
        buf = ConversationBuffer(max_turns=1)
        buf.append_turn(raw, "ok")
        buf.append_turn("next", "done")
        stored = str(buf.to_dict())
        self.assertNotIn(raw, stored)
        self.assertIn("[Content blocked]", stored)


class TestConversationBufferThreadSafety(unittest.TestCase):
    def test_concurrent_appends_max_turns(self):
        buf = ConversationBuffer()
        barrier = threading.Barrier(10)

        def append_worker(idx):
            barrier.wait()
            buf.append_turn(f"q{idx}", f"a{idx}")

        threads = []
        for i in range(10):
            t = threading.Thread(target=append_worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertLessEqual(buf.count(), 5)
        self.assertGreater(buf.count(), 0)

    def test_concurrent_read_write(self):
        buf = ConversationBuffer()
        results = []
        lock = threading.Lock()

        def writer():
            for i in range(5):
                buf.append_turn(f"q{i}", f"a{i}")

        def reader():
            for _ in range(5):
                turns = buf.get_turns()
                with lock:
                    results.append(len(turns))

        writers = [threading.Thread(target=writer) for _ in range(3)]
        readers = [threading.Thread(target=reader) for _ in range(3)]

        for t in writers + readers:
            t.start()
        for t in writers + readers:
            t.join()

        self.assertTrue(len(results) > 0)
        self.assertLessEqual(buf.count(), 5)


class TestConversationBufferToDict(unittest.TestCase):
    def test_to_dict_structure(self):
        buf = ConversationBuffer()
        buf.append_turn("q", "a")
        d = buf.to_dict()
        self.assertIn("turns", d)
        self.assertIn("count", d)
        self.assertIn("max_turns", d)
        self.assertEqual(d["count"], 1)
        self.assertEqual(d["max_turns"], 5)

    def test_to_dict_empty(self):
        buf = ConversationBuffer()
        d = buf.to_dict()
        self.assertEqual(d["count"], 0)
        self.assertEqual(d["turns"], [])


if __name__ == "__main__":
    unittest.main()
