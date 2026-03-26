"""Unit tests for the trust store."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_trust(tmp_path, monkeypatch):
    """Return the trust module with both trust paths redirected to tmp_path."""
    import importlib
    import agent.trust as trust_mod

    project_trust = tmp_path / "project_trust.json"
    global_trust  = tmp_path / "global_trust.json"

    monkeypatch.setattr(trust_mod, "_PROJECT_TRUST", project_trust)
    monkeypatch.setattr(trust_mod, "_global_trust_path", lambda: global_trust)

    # Reset module-level state by reloading (avoids cross-test bleed)
    importlib.reload(trust_mod)
    monkeypatch.setattr(trust_mod, "_PROJECT_TRUST", project_trust)
    monkeypatch.setattr(trust_mod, "_global_trust_path", lambda: global_trust)

    return trust_mod, project_trust, global_trust


# ── is_trusted / remember ────────────────────────────────────────────────────

def test_not_trusted_by_default(tmp_path, monkeypatch):
    trust, _, _ = _make_trust(tmp_path, monkeypatch)
    assert not trust.is_trusted("run_shell", {"command": "ls"})


def test_remember_project_scope_makes_trusted(tmp_path, monkeypatch):
    trust, _, _ = _make_trust(tmp_path, monkeypatch)
    trust.remember("run_python", {}, scope="project")
    assert trust.is_trusted("run_python", {})


def test_remember_global_scope_makes_trusted(tmp_path, monkeypatch):
    trust, _, _ = _make_trust(tmp_path, monkeypatch)
    trust.remember("write_file", {}, scope="global")
    assert trust.is_trusted("write_file", {})


def test_remember_all_grants_blanket_trust(tmp_path, monkeypatch):
    trust, _, _ = _make_trust(tmp_path, monkeypatch)
    trust.remember_all(scope="project")
    assert trust.is_trusted("delete_file", {})
    assert trust.is_trusted("run_shell", {"command": "rm -rf /"})


def test_run_shell_key_uses_first_word(tmp_path, monkeypatch):
    trust, project_path, _ = _make_trust(tmp_path, monkeypatch)
    trust.remember("run_shell", {"command": "git status"}, scope="project")
    # Same first word → trusted
    assert trust.is_trusted("run_shell", {"command": "git log"})
    # Different first word → not trusted
    assert not trust.is_trusted("run_shell", {"command": "ls -la"})


# ── revoke ────────────────────────────────────────────────────────────────────

def test_revoke_removes_entry(tmp_path, monkeypatch):
    trust, _, _ = _make_trust(tmp_path, monkeypatch)
    trust.remember("run_python", {}, scope="project")
    assert trust.is_trusted("run_python", {})

    removed = trust.revoke("tool:run_python", scope="project")
    assert removed is True
    assert not trust.is_trusted("run_python", {})


def test_revoke_nonexistent_returns_false(tmp_path, monkeypatch):
    trust, _, _ = _make_trust(tmp_path, monkeypatch)
    assert trust.revoke("tool:nonexistent", scope="project") is False


# ── full_access_asked / mark_asked ────────────────────────────────────────────

def test_full_access_not_asked_initially(tmp_path, monkeypatch):
    trust, _, _ = _make_trust(tmp_path, monkeypatch)
    assert not trust.full_access_asked()


def test_mark_asked_persists(tmp_path, monkeypatch):
    trust, _, _ = _make_trust(tmp_path, monkeypatch)
    trust.mark_asked()
    assert trust.full_access_asked()


# ── list_trusted ──────────────────────────────────────────────────────────────

def test_list_trusted_returns_dict(tmp_path, monkeypatch):
    trust, _, _ = _make_trust(tmp_path, monkeypatch)
    trust.remember("edit_file", {}, scope="project")
    entries = trust.list_trusted(scope="project")
    assert isinstance(entries, dict)
    assert "tool:edit_file" in entries
