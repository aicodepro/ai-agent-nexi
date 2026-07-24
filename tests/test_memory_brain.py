import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import tempfile
import shutil
import uuid
from pathlib import Path
from unittest.mock import patch

from engine.memory.memory_policy import (
    classify_memory_text, classify_key_value, sensitivity_for, is_key_blocked,
)
from engine.memory.memory_redaction import (
    redact_sensitive, redact_dict, sanitize_for_summary,
)
from engine.memory.local_memory import (
    LocalMemoryStore, LocalJsonlStore, validate_storage_path,
)
from engine.memory.preference_store import PreferenceStore
from engine.memory.task_memory import TaskMemory
from engine.memory.episodic_memory import Episode, EpisodicMemory
from engine.memory.semantic_memory import SemanticFact, SemanticMemory


class TestMemoryPolicy(unittest.TestCase):
    def test_safe_preference_allowed(self):
        decision, reason = classify_memory_text("I prefer Chrome browser")
        self.assertEqual(decision, "ALLOW")

    def test_preferred_repo_allowed(self):
        decision, reason = classify_memory_text("preferred repo is E:\\nexi-main")
        self.assertEqual(decision, "ALLOW")

    def test_password_rejected(self):
        decision, reason = classify_memory_text("my password is secret123")
        self.assertEqual(decision, "REJECT")

    def test_api_key_rejected(self):
        decision, reason = classify_memory_text("api_key = sk-abc123def456")
        self.assertEqual(decision, "REJECT")

    def test_token_rejected(self):
        decision, reason = classify_memory_text("auth_token = ghp_abc123def456token")
        self.assertEqual(decision, "REJECT")

    def test_cookie_rejected(self):
        decision, reason = classify_memory_text("cookie = session_id=abc123xyz")
        self.assertEqual(decision, "REJECT")

    def test_card_number_rejected(self):
        decision, reason = classify_memory_text("card 4111 1111 1111 1111")
        self.assertEqual(decision, "REJECT")

    def test_otp_rejected(self):
        decision, reason = classify_memory_text("otp = 123456")
        self.assertEqual(decision, "REJECT")

    def test_secret_rejected(self):
        decision, reason = classify_memory_text("secret = my_secret_value")
        self.assertEqual(decision, "REJECT")

    def test_phone_requires_confirmation(self):
        decision, reason = classify_memory_text("my number is +1-555-123-4567")
        self.assertEqual(decision, "REQUIRE_CONFIRMATION")

    def test_email_requires_confirmation(self):
        decision, reason = classify_memory_text("email me at test@example.com")
        self.assertEqual(decision, "REQUIRE_CONFIRMATION")

    def test_screenshot_rejected(self):
        decision, reason = classify_memory_text("screenshot image data here")
        self.assertEqual(decision, "REQUIRE_CONFIRMATION")

    def test_raw_audio_rejected(self):
        decision, reason = classify_memory_text("raw audio recording data")
        self.assertEqual(decision, "REQUIRE_CONFIRMATION")

    def test_empty_text_allowed(self):
        decision, reason = classify_memory_text("")
        self.assertEqual(decision, "ALLOW")

    def test_classify_key_value_blocked_key(self):
        decision, reason = classify_key_value("password", "anything")
        self.assertEqual(decision, "REJECT")

    def test_classify_key_value_safe(self):
        decision, reason = classify_key_value("preferred_browser", "Chrome")
        self.assertEqual(decision, "ALLOW")

    def test_sensitivity_for_reject(self):
        self.assertEqual(sensitivity_for("REJECT"), "HIGH")

    def test_sensitivity_for_require_confirmation(self):
        self.assertEqual(sensitivity_for("REQUIRE_CONFIRMATION"), "MEDIUM")

    def test_sensitivity_for_allow(self):
        self.assertEqual(sensitivity_for("ALLOW"), "LOW")

    def test_is_key_blocked_true(self):
        self.assertTrue(is_key_blocked("password"))

    def test_is_key_blocked_false(self):
        self.assertFalse(is_key_blocked("preferred_browser"))


class TestMemoryRedaction(unittest.TestCase):
    def test_redact_api_key(self):
        result = redact_sensitive("api_key = sk-abc123def456")
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("sk-abc123def456", result)

    def test_redact_email(self):
        result = redact_sensitive("contact test@example.com")
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("test@example.com", result)

    def test_redact_phone(self):
        result = redact_sensitive("call +1-555-123-4567")
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("+1-555-123-4567", result)

    def test_redact_card(self):
        result = redact_sensitive("card 4111111111111111")
        self.assertIn("[REDACTED]", result)

    def test_redact_otp(self):
        result = redact_sensitive("otp = 123456")
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("123456", result)

    def test_redact_safe_text_unchanged(self):
        text = "I prefer Chrome browser"
        result = redact_sensitive(text)
        self.assertEqual(result, text)

    def test_redact_dict_values(self):
        data = {"name": "test", "api": "api_key = sk-xyz"}
        result = redact_dict(data)
        self.assertIn("[REDACTED]", result["api"])
        self.assertEqual(result["name"], "test")

    def test_redact_dict_nested(self):
        data = {"user": {"email": "a@b.com"}}
        result = redact_dict(data)
        self.assertIn("[REDACTED]", result["user"]["email"])

    def test_sanitize_for_summary(self):
        item = {"key": "api_key", "value": "api_key = sk-xyz"}
        safe = sanitize_for_summary(item)
        self.assertIn("[REDACTED]", safe["value"])

    def test_none_input_returns_none(self):
        self.assertIsNone(redact_sensitive(None))


class TestLocalMemoryStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.filepath = os.path.join(self.tmpdir, "test_prefs.json")
        self.store = LocalMemoryStore(self.filepath, _skip_validation=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_set_and_get(self):
        self.store.set("foo", {"value": "bar"})
        self.assertEqual(self.store.get("foo"), {"value": "bar"})

    def test_get_default(self):
        self.assertIsNone(self.store.get("nonexistent"))

    def test_exists(self):
        self.store.set("a", 1)
        self.assertTrue(self.store.exists("a"))
        self.assertFalse(self.store.exists("b"))

    def test_delete(self):
        self.store.set("a", 1)
        self.assertTrue(self.store.delete("a"))
        self.assertFalse(self.store.exists("a"))

    def test_delete_nonexistent(self):
        self.assertFalse(self.store.delete("nonexistent"))

    def test_keys(self):
        self.store.set("a", 1)
        self.store.set("b", 2)
        self.assertIn("a", self.store.keys())
        self.assertIn("b", self.store.keys())

    def test_all(self):
        self.store.set("a", 1)
        all_data = self.store.all()
        self.assertEqual(all_data["a"], 1)

    def test_clear(self):
        self.store.set("a", 1)
        self.store.clear()
        self.assertEqual(self.store.size(), 0)

    def test_filepath_returns_path(self):
        self.assertEqual(self.store.filepath(), self.filepath)

    def test_persistence_across_reload(self):
        self.store.set("key", "val")
        reloaded = LocalMemoryStore(self.filepath, _skip_validation=True)
        self.assertEqual(reloaded.get("key"), "val")

    def test_two_instances_do_not_overwrite_each_others_writes(self):
        second = LocalMemoryStore(self.filepath, _skip_validation=True)
        self.store.set("first", 1)
        second.set("second", 2)
        reloaded = LocalMemoryStore(self.filepath, _skip_validation=True)
        self.assertEqual(reloaded.all(), {"first": 1, "second": 2})

    def test_save_uses_atomic_replace(self):
        with patch("os.replace", wraps=os.replace) as replace:
            self.store.set("atomic", True)
        replace.assert_called_once()

    def test_corrupt_json_is_quarantined_and_reported(self):
        Path(self.filepath).write_text("{broken", encoding="utf-8")
        with self.assertWarns(RuntimeWarning):
            store = LocalMemoryStore(self.filepath, _skip_validation=True)
        self.assertTrue(store.load_error)
        self.assertFalse(Path(self.filepath).exists())
        self.assertEqual(len(list(Path(self.tmpdir).glob("test_prefs.json.corrupt-*"))), 1)


class TestLocalJsonlStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.filepath = os.path.join(self.tmpdir, "test_tasks.jsonl")
        self.store = LocalJsonlStore(self.filepath, _skip_validation=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_append_and_read(self):
        self.store.append({"task": "test"})
        entries = self.store.read_all()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["task"], "test")

    def test_read_all_empty(self):
        entries = self.store.read_all()
        self.assertEqual(entries, [])

    def test_read_recent(self):
        for i in range(5):
            self.store.append({"i": i})
        recent = self.store.read_recent(3)
        self.assertEqual(len(recent), 3)

    def test_size(self):
        self.store.append({"a": 1})
        self.store.append({"b": 2})
        self.assertEqual(self.store.size(), 2)

    def test_size_empty(self):
        self.assertEqual(self.store.size(), 0)

    def test_corrupt_jsonl_is_quarantined_and_reported(self):
        Path(self.filepath).write_text('{"ok": 1}\n{broken\n', encoding="utf-8")
        with self.assertWarns(RuntimeWarning):
            entries = self.store.read_all()
        self.assertEqual(entries, [{"ok": 1}])
        self.assertTrue(self.store.load_error)
        self.assertFalse(Path(self.filepath).exists())
        self.assertEqual(len(list(Path(self.tmpdir).glob("test_tasks.jsonl.corrupt-*"))), 1)

    def test_size_does_not_silently_count_corrupt_lines(self):
        Path(self.filepath).write_text('{broken\n', encoding="utf-8")
        with self.assertWarns(RuntimeWarning):
            self.assertEqual(self.store.size(), 0)
        self.assertFalse(Path(self.filepath).exists())


class TestValidateStoragePath(unittest.TestCase):
    def test_path_inside_project(self):
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        )
        test_path = os.path.join(project_root, "data", "memory", "test.json")
        valid, msg = validate_storage_path(test_path)
        self.assertTrue(valid)

    def test_path_outside_project(self):
        valid, msg = validate_storage_path("C:\\Windows\\temp\\test.json")
        self.assertFalse(valid)


class TestPreferenceStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.filepath = os.path.join(self.tmpdir, "prefs.json")
        self.store = PreferenceStore(self.filepath)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_safe_preference_saved(self):
        result = self.store.remember("preferred_browser", "Chrome")
        self.assertTrue(result["ok"])
        self.assertEqual(self.store.count(), 1)

    def test_existing_preference_updated(self):
        self.store.remember("preferred_browser", "Firefox")
        result = self.store.update("preferred_browser", "Chrome")
        self.assertTrue(result["ok"])
        get_result = self.store.get("preferred_browser")
        self.assertEqual(get_result["data"]["item"]["value"], "Chrome")

    def test_preference_forgotten(self):
        self.store.remember("preferred_browser", "Chrome")
        result = self.store.forget("preferred_browser")
        self.assertTrue(result["ok"])
        self.assertEqual(self.store.count(), 0)

    def test_get_preference_works(self):
        self.store.remember("repo", "E:\\nexi-main")
        result = self.store.get("repo")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["item"]["value"], "E:\\nexi-main")

    def test_get_nonexistent_returns_error(self):
        result = self.store.get("nonexistent")
        self.assertFalse(result["ok"])

    def test_forget_nonexistent_returns_error(self):
        result = self.store.forget("nonexistent")
        self.assertFalse(result["ok"])

    def test_summary_excludes_sensitive_raw_values(self):
        self.store.remember("name", "Jarvi")
        result = self.store.summarize()
        self.assertTrue(result["ok"])
        summary_str = str(result)
        self.assertNotIn("api_key", summary_str.lower())
        self.assertNotIn("password", summary_str.lower())

    def test_password_memory_rejected(self):
        result = self.store.remember("password", "secret123")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "REJECTED")

    def test_api_key_memory_rejected(self):
        result = self.store.remember("api_key", "sk-abc123")
        self.assertFalse(result["ok"])

    def test_token_memory_rejected(self):
        result = self.store.remember("auth_token", "ghp_abc123")
        self.assertFalse(result["ok"])

    def test_cookie_memory_rejected(self):
        result = self.store.remember("cookie", "session=abc")
        self.assertFalse(result["ok"])

    def test_phone_requires_confirmation(self):
        result = self.store.remember("my_phone", "+1-555-123-4567")
        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["item"]["requires_confirmation"])

    def test_email_requires_confirmation(self):
        result = self.store.remember("my_email", "test@example.com")
        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["item"]["requires_confirmation"])

    def test_update_rejected_for_sensitive(self):
        self.store.remember("name", "Jarvi")
        result = self.store.update("name", "password = secret")
        self.assertFalse(result["ok"])

    def test_summary_no_secrets_in_messages(self):
        self.store.remember("repo", "E:\\nexi-main")
        result = self.store.summarize()
        result_str = str(result)
        self.assertNotIn("DEEPSEEK_API_KEY", result_str)
        self.assertNotIn("GLM_API_KEY", result_str)


class TestTaskMemory(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.filepath = os.path.join(self.tmpdir, "tasks.jsonl")
        self.store = TaskMemory(self.filepath)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_task_summary_saved_when_safe(self):
        result = self.store.append({
            "task_type": "coding",
            "summary": "Refactored intent brain",
            "status": "completed",
            "duration_ms": 1500,
        })
        self.assertTrue(result["ok"])
        self.assertEqual(self.store.count(), 1)

    def test_sensitive_task_summary_rejected(self):
        result = self.store.append({
            "task_type": "login",
            "summary": "password = secret123",
        })
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "REJECTED")

    def test_recent_returns_safe_entries(self):
        self.store.append({"task_type": "test", "summary": "ran tests", "status": "done"})
        result = self.store.recent(10)
        self.assertTrue(result["ok"])
        self.assertGreater(result["data"]["count"], 0)

    def test_no_secrets_in_task_output(self):
        self.store.append({"task_type": "coding", "summary": "built feature", "status": "ok"})
        result = self.store.recent(10)
        result_str = str(result)
        self.assertNotIn("api_key", result_str.lower())
        self.assertNotIn("password", result_str.lower())

    def test_invalid_input_rejected(self):
        result = self.store.append("not a dict")
        self.assertFalse(result["ok"])

    def test_empty_recent_returns_empty(self):
        result = self.store.recent(10)
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["count"], 0)


class TestPreferenceStorePersistence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.filepath = os.path.join(self.tmpdir, "prefs.json")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_memory_persists_across_store_instances(self):
        s1 = PreferenceStore(self.filepath)
        s1.remember("assistant_name", "Jarvi")
        s2 = PreferenceStore(self.filepath)
        result = s2.get("assistant_name")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["item"]["value"], "Jarvi")


class TestStructuredMemoryPersistence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_episodic_and_semantic_writes_use_atomic_replace(self):
        with patch("os.replace", wraps=os.replace) as replace:
            EpisodicMemory(self.tmpdir / "episodes.json").store(
                Episode(user_input="open the project", steps_taken=["opened project"])
            )
            SemanticMemory(self.tmpdir / "facts.json").upsert(
                SemanticFact(object="prefers concise answers")
            )
        self.assertEqual(replace.call_count, 2)

    def test_corrupt_structured_memory_is_quarantined_and_reported(self):
        for name, factory in (
            ("episodes.json", lambda path: EpisodicMemory(path).count()),
            ("facts.json", lambda path: SemanticMemory(path).count()),
        ):
            with self.subTest(name=name):
                path = self.tmpdir / name
                path.write_text("{broken", encoding="utf-8")
                with self.assertWarns(RuntimeWarning):
                    self.assertEqual(factory(path), 0)
                self.assertFalse(path.exists())
                self.assertEqual(len(list(self.tmpdir.glob(f"{name}.corrupt-*"))), 1)

    def test_default_preference_and_task_paths_stay_inside_current_project(self):
        from engine.memory.preference_store import _DEFAULT_PREFS_PATH
        from engine.memory.task_memory import _DEFAULT_TASKS_PATH

        project_root = Path(__file__).resolve().parents[1]
        self.assertTrue(Path(_DEFAULT_PREFS_PATH).is_relative_to(project_root))
        self.assertTrue(Path(_DEFAULT_TASKS_PATH).is_relative_to(project_root))


if __name__ == "__main__":
    unittest.main()
