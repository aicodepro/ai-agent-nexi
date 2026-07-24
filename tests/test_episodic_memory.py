import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_episodic_memory_store_and_recall_recent(tmp_path):
    from engine.memory.episodic_memory import Episode, EpisodicMemory

    memory = EpisodicMemory(tmp_path / "episodes.json")
    episode_id = memory.store(Episode(user_input="create folder on desktop", intent="create_folder", route="workflow"))
    assert episode_id.startswith("ep_")
    recent = memory.recall_recent(1)
    assert recent[0].user_input == "create folder on desktop"
    assert recent[0].intent == "create_folder"


def test_episodic_memory_recall_similar(tmp_path):
    from engine.memory.episodic_memory import Episode, EpisodicMemory

    memory = EpisodicMemory(tmp_path / "episodes.json")
    memory.store(Episode(user_input="open chrome", intent="open_app", route="tool"))
    memory.store(Episode(user_input="create folder documents", intent="create_folder", route="workflow"))

    matches = memory.recall_similar("make folder in documents", n=2)
    assert matches
    assert matches[0].intent == "create_folder"


def test_episodic_memory_prunes_old_entries(tmp_path):
    from engine.memory.episodic_memory import Episode, EpisodicMemory

    memory = EpisodicMemory(tmp_path / "episodes.json")
    memory.store(Episode(user_input="old task", timestamp=time.time() - 86400 * 40))
    memory.store(Episode(user_input="new task"))
    assert memory.prune_old(days=30) == 1
    assert memory.count() == 1


def test_episodic_memory_filters_secret_text(tmp_path):
    from engine.memory.episodic_memory import Episode, EpisodicMemory

    memory = EpisodicMemory(tmp_path / "episodes.json")
    episode_id = memory.store(Episode(user_input="my password is 123"))
    assert episode_id == ""
    assert memory.count() == 0


def test_episodic_memory_caps_max_entries(tmp_path):
    from engine.memory.episodic_memory import Episode, EpisodicMemory

    memory = EpisodicMemory(tmp_path / "episodes.json", max_episodes=2)
    memory.store(Episode(user_input="task one"))
    memory.store(Episode(user_input="task two"))
    memory.store(Episode(user_input="task three"))
    assert [ep.user_input for ep in memory.recall_recent(10)] == ["task two", "task three"]
