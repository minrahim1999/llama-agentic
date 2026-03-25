"""Tests for memory tools, session persistence, and sliding window."""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch


# ── Memory tools ─────────────────────────────────────────────────────────────

def test_save_and_recall(tmp_path):
    with patch("agent.config.config.memory_dir", str(tmp_path)):
        from agent import memory
        memory.save("test_key", "hello world")
        result = memory.load("test_key")
        assert result == "hello world"


def test_recall_missing(tmp_path):
    with patch("agent.config.config.memory_dir", str(tmp_path)):
        from agent import memory
        result = memory.load("nonexistent")
        assert result is None


def test_list_memories(tmp_path):
    with patch("agent.config.config.memory_dir", str(tmp_path)):
        from agent import memory
        memory.save("alpha", "a")
        memory.save("beta", "b")
        keys = memory.list_memories()
        assert "alpha" in keys
        assert "beta" in keys


def test_forget_memory(tmp_path):
    with patch("agent.config.config.memory_dir", str(tmp_path)):
        from agent import memory
        memory.save("to_delete", "bye")
        result = memory.forget("to_delete")
        assert "deleted" in result.lower()
        assert memory.load("to_delete") is None


def test_load_all(tmp_path):
    with patch("agent.config.config.memory_dir", str(tmp_path)):
        from agent import memory
        memory.save("foo", "content foo")
        memory.save("bar", "content bar")
        combined = memory.load_all()
        assert "foo" in combined
        assert "content foo" in combined


# ── Session persistence ───────────────────────────────────────────────────────

def test_session_save_and_load(tmp_path):
    with patch("agent.config.config.sessions_dir", str(tmp_path)):
        from agent import session
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        path = session.save(history, name="test")
        filename = Path(path).name
        loaded = session.load(filename)
        assert loaded == history


def test_session_list(tmp_path):
    with patch("agent.config.config.sessions_dir", str(tmp_path)):
        from agent import session
        session.save([{"role": "user", "content": "x"}], name="s1")
        session.save([{"role": "user", "content": "y"}], name="s2")
        names = session.list_sessions()
        assert len(names) == 2


def test_session_load_missing(tmp_path):
    with patch("agent.config.config.sessions_dir", str(tmp_path)):
        from agent import session
        with pytest.raises(FileNotFoundError):
            session.load("no_such_session")


# ── Sliding window ────────────────────────────────────────────────────────────

def test_windowed_history_trims():
    from agent.core import Agent
    from unittest.mock import MagicMock
    from agent.config import config

    agent = Agent.__new__(Agent)
    agent.confirm_callback = None
    agent.system_prompt = ""
    agent.client = MagicMock()

    # Build 5 user/assistant turn pairs
    agent.history = []
    for i in range(5):
        agent.history.append({"role": "user", "content": f"msg {i}"})
        agent.history.append({"role": "assistant", "content": f"reply {i}"})

    original_window = config.history_window
    config.history_window = 3
    try:
        windowed = agent._windowed_history()
        # Should contain the last 3 turns = 6 messages
        user_msgs = [m for m in windowed if m["role"] == "user"]
        assert len(user_msgs) == 3
        assert user_msgs[0]["content"] == "msg 2"  # oldest kept turn
        assert user_msgs[-1]["content"] == "msg 4"  # newest turn
    finally:
        config.history_window = original_window


def test_windowed_history_no_trim():
    from agent.core import Agent
    from unittest.mock import MagicMock
    from agent.config import config

    agent = Agent.__new__(Agent)
    agent.confirm_callback = None
    agent.system_prompt = ""
    agent.client = MagicMock()

    agent.history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    original_window = config.history_window
    config.history_window = 10
    try:
        assert agent._windowed_history() == agent.history
    finally:
        config.history_window = original_window
