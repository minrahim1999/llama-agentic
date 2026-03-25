"""Tests for view_file, edit_file, and compute_diff."""

from pathlib import Path


def test_view_file_full(tmp_path):
    from agent.tools.edit import view_file
    f = tmp_path / "hello.py"
    f.write_text("line1\nline2\nline3\n")
    result = view_file(str(f))
    assert "1│" in result or "1│ " in result.replace("│", "│ ")
    assert "line1" in result
    assert "line3" in result


def test_view_file_range(tmp_path):
    from agent.tools.edit import view_file
    f = tmp_path / "code.py"
    f.write_text("\n".join(f"line{i}" for i in range(1, 11)) + "\n")
    result = view_file(str(f), start_line=3, end_line=5)
    assert "line3" in result
    assert "line5" in result
    assert "line1" not in result
    assert "line6" not in result


def test_view_file_missing(tmp_path):
    from agent.tools.edit import view_file
    result = view_file(str(tmp_path / "nope.py"))
    assert "Error" in result


def test_view_file_blocks_ignored_path(tmp_path, monkeypatch):
    from agent.tools.edit import view_file

    secret = tmp_path / "secret.txt"
    secret.write_text("hidden\n")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".llamaignore").write_text("secret.txt\n")

    result = view_file("secret.txt")

    assert "protected" in result


def test_edit_file_simple(tmp_path):
    from agent.tools.edit import edit_file
    f = tmp_path / "greet.py"
    f.write_text("def hello():\n    return 'hi'\n")
    result = edit_file(str(f), "return 'hi'", "return 'hello world'")
    assert "Edited" in result
    assert f.read_text() == "def hello():\n    return 'hello world'\n"


def test_edit_file_shows_diff(tmp_path):
    from agent.tools.edit import edit_file
    f = tmp_path / "sample.py"
    f.write_text("x = 1\n")
    result = edit_file(str(f), "x = 1", "x = 42")
    assert "-x = 1" in result
    assert "+x = 42" in result


def test_edit_file_not_found(tmp_path):
    from agent.tools.edit import edit_file
    result = edit_file(str(tmp_path / "missing.py"), "old", "new")
    assert "Error" in result


def test_edit_file_ambiguous(tmp_path):
    from agent.tools.edit import edit_file
    f = tmp_path / "dup.py"
    f.write_text("x = 1\nx = 1\n")
    result = edit_file(str(f), "x = 1", "x = 2")
    assert "Error" in result
    assert "2 times" in result


def test_edit_file_old_not_found(tmp_path):
    from agent.tools.edit import edit_file
    f = tmp_path / "code.py"
    f.write_text("a = 1\n")
    result = edit_file(str(f), "b = 2", "b = 3")
    assert "Error" in result
    assert "not found" in result


def test_create_new_file_via_edit(tmp_path):
    from agent.tools.edit import edit_file
    new_file = str(tmp_path / "newfile.py")
    result = edit_file(new_file, "", "print('hello')\n")
    assert "Created" in result
    assert Path(new_file).read_text() == "print('hello')\n"


def test_compute_diff(tmp_path):
    from agent.tools.edit import compute_diff
    f = tmp_path / "f.py"
    f.write_text("a = 1\n")
    diff = compute_diff(str(f), "a = 1", "a = 99")
    assert "-a = 1" in diff
    assert "+a = 99" in diff


def test_compute_diff_blocks_ignored_path(tmp_path, monkeypatch):
    from agent.tools.edit import compute_diff

    secret = tmp_path / "secret.py"
    secret.write_text("a = 1\n")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".llamaignore").write_text("secret.py\n")

    diff = compute_diff("secret.py", "a = 1", "a = 2")

    assert "protected" in diff
