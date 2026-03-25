"""Tests for configured GGUF model path handling."""


def test_update_global_config_values_writes_model_path(tmp_path, monkeypatch):
    from agent import config as cfg

    config_file = tmp_path / "config.env"
    config_file.write_text("LLAMA_MODEL=existing-model\n", encoding="utf-8")

    monkeypatch.setattr(cfg, "GLOBAL_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "GLOBAL_CONFIG_FILE", config_file)

    cfg.update_global_config_values({
        "LLAMA_MODEL_PATH": "/tmp/model.gguf",
        "UNSAFE_MODE": False,
    })

    text = config_file.read_text(encoding="utf-8")
    assert "LLAMA_MODEL=existing-model" in text
    assert "LLAMA_MODEL_PATH=/tmp/model.gguf" in text
    assert "UNSAFE_MODE=false" in text


def test_persist_selected_model_updates_runtime_and_global_config(tmp_path, monkeypatch):
    from agent import config as cfg
    from agent.model_manager import persist_selected_model

    model_path = tmp_path / "demo.gguf"
    model_path.write_text("binary-ish", encoding="utf-8")
    config_file = tmp_path / "config.env"

    monkeypatch.setattr(cfg, "GLOBAL_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "GLOBAL_CONFIG_FILE", config_file)
    monkeypatch.setattr(cfg.config, "llama_model_path", "")

    persisted = persist_selected_model(str(model_path))

    assert persisted == str(model_path.resolve())
    assert cfg.config.llama_model_path == str(model_path.resolve())
    assert f"LLAMA_MODEL_PATH={model_path.resolve()}" in config_file.read_text(encoding="utf-8")


def test_resolve_model_file_prefers_explicit_path_over_config_and_cache(tmp_path, monkeypatch):
    from agent import config as cfg
    from agent.server_manager import resolve_model_file

    explicit = tmp_path / "explicit.gguf"
    explicit.write_text("x", encoding="utf-8")
    configured = tmp_path / "configured.gguf"
    configured.write_text("x", encoding="utf-8")
    cached = tmp_path / "cache" / "cached.gguf"
    cached.parent.mkdir()
    cached.write_text("x", encoding="utf-8")

    monkeypatch.setattr(cfg.config, "llama_model_path", str(configured))
    monkeypatch.setattr(cfg.config, "model_cache_dir", str(cached.parent))

    assert resolve_model_file(str(explicit)) == str(explicit.resolve())


def test_resolve_model_file_prefers_configured_path_over_cache(tmp_path, monkeypatch):
    from agent import config as cfg
    from agent.server_manager import resolve_model_file

    configured = tmp_path / "configured.gguf"
    configured.write_text("x", encoding="utf-8")
    cached = tmp_path / "cache" / "cached.gguf"
    cached.parent.mkdir()
    cached.write_text("x", encoding="utf-8")

    monkeypatch.setattr(cfg.config, "llama_model_path", str(configured))
    monkeypatch.setattr(cfg.config, "model_cache_dir", str(cached.parent))

    assert resolve_model_file() == str(configured.resolve())


def test_resolve_model_file_falls_back_to_cache(tmp_path, monkeypatch):
    from agent import config as cfg
    from agent.server_manager import resolve_model_file

    cached = tmp_path / "cache" / "cached.gguf"
    cached.parent.mkdir()
    cached.write_text("x", encoding="utf-8")

    monkeypatch.setattr(cfg.config, "llama_model_path", "")
    monkeypatch.setattr(cfg.config, "model_cache_dir", str(cached.parent))

    assert resolve_model_file() == str(cached)


def test_configured_model_path_returns_none_for_missing_file(tmp_path, monkeypatch):
    from agent import config as cfg

    missing = tmp_path / "missing.gguf"
    monkeypatch.setattr(cfg.config, "llama_model_path", str(missing))

    assert cfg.configured_model_path() is None
