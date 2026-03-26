"""Unit tests for CLI helper behavior."""

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from agent import cli


def test_match_slash_suggestions_root_includes_core_commands():
    suggestions = cli._match_slash_suggestions("/")
    commands = {item[0] for item in suggestions}

    assert "/help" in commands
    assert "/tools" in commands
    assert "/tool <name>" in commands


def test_match_slash_suggestions_tool_prefix_filters_tool_names(monkeypatch):
    monkeypatch.setattr(
        cli,
        "_tool_specs",
        lambda: [
            ("read_file", "Read a file"),
            ("run_shell", "Run a shell command"),
            ("write_file", "Write a file"),
        ],
    )

    suggestions = cli._match_slash_suggestions("/tool ru")

    assert suggestions == [("/tool run_shell", "tool · Run a shell command")]


def test_slash_completer_exposes_command_metadata(monkeypatch):
    monkeypatch.setattr(
        cli,
        "_tool_specs",
        lambda: [("run_shell", "Run a shell command")],
    )
    completer = cli.SlashCommandCompleter()

    completions = list(
        completer.get_completions(
            Document("/tool r"),
            CompleteEvent(completion_requested=True),
        )
    )

    assert completions
    assert completions[0].text == "/tool run_shell"
    assert "tool" in str(completions[0].display_meta).lower()


def test_format_recent_activity_handles_missing_sessions(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.session, "list_sessions", lambda: [])
    monkeypatch.setattr(cli.config, "sessions_dir", str(tmp_path))

    assert cli._format_recent_activity() == "No recent activity"


def test_format_recent_activity_uses_latest_session(monkeypatch, tmp_path):
    session_file = tmp_path / "chat_2026-03-26_10-30-00.json"
    session_file.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(cli.session, "list_sessions", lambda: [session_file.name])
    monkeypatch.setattr(cli.config, "sessions_dir", str(tmp_path))

    activity = cli._format_recent_activity()

    assert activity.startswith("chat updated ")
    assert "No recent activity" not in activity


def test_build_prompt_session_returns_none_without_prompt_toolkit(monkeypatch):
    monkeypatch.setattr(cli, "_PROMPT_TOOLKIT_AVAILABLE", False)
    monkeypatch.setattr(cli, "PromptSession", None)
    monkeypatch.setattr(cli, "InMemoryHistory", None)

    assert cli._build_prompt_session() is None
