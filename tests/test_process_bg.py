"""Unit tests for background process management tools."""

import time
import pytest


def _clear_registry():
    """Remove all entries from the background process registry."""
    from agent.tools.process import _BACKGROUND_PROCS
    _BACKGROUND_PROCS.clear()


# ── run_background / list_background / stop_background ───────────────────────

def test_run_background_starts_process():
    from agent.tools.process import run_background, _BACKGROUND_PROCS
    _clear_registry()

    result = run_background("sleep 30")
    pid = next(iter(_BACKGROUND_PROCS))

    assert "Background process started" in result
    assert str(pid) in result

    # cleanup
    from agent.tools.process import stop_background
    stop_background(pid)


def test_run_background_registers_in_registry():
    from agent.tools.process import run_background, _BACKGROUND_PROCS
    _clear_registry()

    run_background("sleep 30")
    assert len(_BACKGROUND_PROCS) == 1
    info = next(iter(_BACKGROUND_PROCS.values()))
    assert "proc" in info
    assert "command" in info
    assert "buf" in info

    pid = next(iter(_BACKGROUND_PROCS))
    from agent.tools.process import stop_background
    stop_background(pid)


def test_list_background_empty():
    from agent.tools.process import list_background
    _clear_registry()

    result = list_background()
    assert "No background processes" in result


def test_list_background_shows_running_process():
    from agent.tools.process import run_background, list_background
    _clear_registry()

    run_background("sleep 30")
    result = list_background()
    assert "running" in result
    assert "sleep 30" in result

    from agent.tools.process import _BACKGROUND_PROCS, stop_background
    pid = next(iter(_BACKGROUND_PROCS))
    stop_background(pid)


def test_stop_background_removes_from_registry():
    from agent.tools.process import run_background, stop_background, _BACKGROUND_PROCS
    _clear_registry()

    run_background("sleep 30")
    pid = next(iter(_BACKGROUND_PROCS))

    result = stop_background(pid)
    assert "stopped" in result.lower()
    assert pid not in _BACKGROUND_PROCS


def test_stop_background_unknown_pid():
    from agent.tools.process import stop_background
    _clear_registry()

    result = stop_background(999999)
    assert "not found" in result.lower()


def test_kill_all_background_cleans_up():
    from agent.tools.process import run_background, kill_all_background, _BACKGROUND_PROCS
    _clear_registry()

    run_background("sleep 30")
    run_background("sleep 30")
    assert len(_BACKGROUND_PROCS) == 2

    killed = kill_all_background()
    assert killed == 2
    assert len(_BACKGROUND_PROCS) == 0


# ── Port helpers ──────────────────────────────────────────────────────────────

def test_extract_port_from_flag():
    from agent.tools.process import _extract_port
    assert _extract_port("uvicorn app:app --port 8000") == 8000
    assert _extract_port("node server.js --port=3000") == 3000


def test_extract_port_returns_none_when_absent():
    from agent.tools.process import _extract_port
    assert _extract_port("sleep 30") is None


def test_substitute_port():
    from agent.tools.process import _substitute_port
    cmd = "uvicorn app:app --port 8000"
    assert _substitute_port(cmd, 8000, 8001) == "uvicorn app:app --port 8001"
