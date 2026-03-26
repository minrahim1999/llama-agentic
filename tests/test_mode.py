"""Unit tests for agent execution modes."""

import pytest
from agent.mode import (
    Mode,
    ALL_MODES,
    get_blocked_tools,
    get_mode_instruction,
    mode_label,
    mode_colour,
    mode_description,
    parse_mode,
)

# ── parse_mode ────────────────────────────────────────────────────────────────

def test_parse_mode_valid():
    assert parse_mode("chat") == Mode.CHAT
    assert parse_mode("HYBRID") == Mode.HYBRID
    assert parse_mode("  Plan  ") == Mode.PLAN


def test_parse_mode_unknown_returns_none():
    assert parse_mode("turbo") is None
    assert parse_mode("") is None


# ── get_blocked_tools ─────────────────────────────────────────────────────────

_MUTATING = {
    "write_file", "edit_file", "delete_file", "make_dir",
    "copy_file", "move_file",
    "run_shell", "run_background", "run_python",
    "git_commit", "kill_process", "stop_background",
}


def test_chat_blocks_all_mutating_tools():
    blocked = get_blocked_tools(Mode.CHAT)
    assert _MUTATING.issubset(blocked)


def test_plan_allows_write_file_blocks_execute():
    blocked = get_blocked_tools(Mode.PLAN)
    assert "write_file" not in blocked
    assert "run_shell" in blocked
    assert "run_python" in blocked
    assert "git_commit" in blocked


def test_review_allows_write_file_blocks_execute():
    blocked = get_blocked_tools(Mode.REVIEW)
    assert "write_file" not in blocked
    assert "run_shell" in blocked


def test_code_blocks_nothing():
    assert get_blocked_tools(Mode.CODE) == set()


def test_hybrid_blocks_nothing():
    assert get_blocked_tools(Mode.HYBRID) == set()


# ── get_mode_instruction ──────────────────────────────────────────────────────

@pytest.mark.parametrize("mode", ALL_MODES)
def test_mode_instruction_non_empty(mode):
    instr = get_mode_instruction(mode)
    assert isinstance(instr, str) and instr.strip()


def test_mode_instruction_contains_mode_name():
    assert "CHAT" in get_mode_instruction(Mode.CHAT).upper()
    assert "PLAN" in get_mode_instruction(Mode.PLAN).upper()
    assert "CODE" in get_mode_instruction(Mode.CODE).upper()
    assert "HYBRID" in get_mode_instruction(Mode.HYBRID).upper()
    assert "REVIEW" in get_mode_instruction(Mode.REVIEW).upper()


# ── display helpers ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("mode", ALL_MODES)
def test_mode_label_non_empty(mode):
    assert mode_label(mode)


@pytest.mark.parametrize("mode", ALL_MODES)
def test_mode_colour_is_hex(mode):
    colour = mode_colour(mode)
    assert colour.startswith("#") and len(colour) == 7


@pytest.mark.parametrize("mode", ALL_MODES)
def test_mode_description_non_empty(mode):
    assert mode_description(mode)
