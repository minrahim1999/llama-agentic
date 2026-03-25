"""Tests for tool registry and individual tools."""

import tempfile
import os
from pathlib import Path


def test_tool_registry_populated():
    from agent.tools import _REGISTRY, get_all_schemas
    import agent.tools.file  # noqa: F401
    import agent.tools.shell  # noqa: F401
    import agent.tools.code  # noqa: F401
    import agent.tools.search  # noqa: F401

    assert len(_REGISTRY) > 0
    schemas = get_all_schemas()
    assert all(s["type"] == "function" for s in schemas)
    names = [s["function"]["name"] for s in schemas]
    assert "read_file" in names
    assert "run_shell" in names
    assert "run_python" in names


def test_read_write_file():
    from agent.tools.file import read_file, write_file

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "hello.txt")
        result = write_file(path, "hello world")
        assert "Written" in result

        content = read_file(path)
        assert content == "hello world"


def test_list_dir():
    from agent.tools.file import list_dir, write_file

    with tempfile.TemporaryDirectory() as d:
        write_file(os.path.join(d, "a.txt"), "a")
        write_file(os.path.join(d, "b.txt"), "b")
        result = list_dir(d)
        assert "a.txt" in result
        assert "b.txt" in result


def test_delete_file():
    from agent.tools.file import write_file, delete_file

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "del.txt")
        write_file(path, "bye")
        result = delete_file(path)
        assert "Deleted" in result
        assert not Path(path).exists()


def test_make_dir_blocks_ignored_path(tmp_path, monkeypatch):
    from agent.tools.file import make_dir

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".llamaignore").write_text("secret\n")

    result = make_dir("secret")

    assert "protected" in result
    assert not (tmp_path / "secret").exists()


def test_list_dir_blocks_ignored_path(tmp_path, monkeypatch):
    from agent.tools.file import list_dir

    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".llamaignore").write_text("secret\n")

    result = list_dir("secret")

    assert "protected" in result


def test_move_file_blocks_ignored_destination(tmp_path, monkeypatch):
    from agent.tools.file import move_file

    src = tmp_path / "source.txt"
    src.write_text("hello")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".llamaignore").write_text("secret/*\n")
    (tmp_path / "secret").mkdir()

    result = move_file("source.txt", "secret/moved.txt")

    assert "protected" in result
    assert src.exists()
    assert not (tmp_path / "secret" / "moved.txt").exists()


def test_copy_file_blocks_ignored_destination(tmp_path, monkeypatch):
    from agent.tools.file import copy_file

    src = tmp_path / "source.txt"
    src.write_text("hello")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".llamaignore").write_text("secret/*\n")
    (tmp_path / "secret").mkdir()

    result = copy_file("source.txt", "secret/copied.txt")

    assert "protected" in result
    assert src.exists()
    assert not (tmp_path / "secret" / "copied.txt").exists()


def test_run_python():
    from agent.tools.code import run_python

    result = run_python("print(1 + 1)")
    assert result.strip() == "2"


def test_run_python_error():
    from agent.tools.code import run_python

    result = run_python("raise ValueError('oops')")
    assert "ValueError" in result


def test_tool_dispatch():
    from agent.tools import dispatch
    import agent.tools.code  # noqa: F401

    result = dispatch("run_python", '{"code": "print(42)"}')
    assert "42" in result


def test_dispatch_unknown():
    from agent.tools import dispatch

    result = dispatch("nonexistent_tool", "{}")
    assert "unknown tool" in result


def test_schema_generation():
    from agent.tools import _build_schema
    from agent.tools.file import read_file

    schema = _build_schema(read_file)
    assert schema["function"]["name"] == "read_file"
    assert "path" in schema["function"]["parameters"]["properties"]
    assert "path" in schema["function"]["parameters"]["required"]
