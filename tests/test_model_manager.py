"""Tests for built-in model alias definitions."""


def test_known_models_include_documented_qwen_general_alias():
    from agent.model_manager import KNOWN_MODELS, list_known

    assert "qwen2.5-7b" in KNOWN_MODELS
    assert "qwen2.5-7b" in list_known()

    repo_id, filename = KNOWN_MODELS["qwen2.5-7b"]
    assert repo_id == "Qwen/Qwen2.5-7B-Instruct-GGUF"
    assert filename == "qwen2.5-7b-instruct-q4_k_m.gguf"
