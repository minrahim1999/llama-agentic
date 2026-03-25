# Changelog

All notable changes to llama-agentic are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

---

## [Unreleased]

## [0.1.0] — 2026-03-19

### Added
- **Foundation**: ReAct agent loop (Reason → Act → Observe) powered by llama.cpp via OpenAI-compatible API
- **Tool system**: `@tool` decorator with auto-schema generation from docstrings
- **Built-in tools**: `read_file`, `write_file`, `list_dir`, `make_dir`, `delete_file`, `view_file`, `edit_file`, `run_shell`, `run_python`, `web_search`, `save_memory`, `recall_memory`, `list_memories`, `delete_memory`
- **Git tools**: `git_status`, `git_diff`, `git_log`, `git_commit`
- **Web tools**: `fetch_url`, `system_info`
- **Memory system**: persistent key-value memory injected into system prompt
- **Session save/load**: JSON session files, auto-save on exit
- **Sliding window history**: configurable turn window, prevents context overflow
- **Tool output truncation**: configurable char limit with truncation notice
- **Interactive REPL**: rich terminal UI with syntax-highlighted diffs
- **Slash commands**: `/init`, `/refresh`, `/add` (glob support), `/undo`, `/model`, `/tools`, `/reset`, `/save`, `/load`, `/sessions`, `/memory`, `/forget`, `/history`, `/cost`, `/help`
- **Non-interactive mode**: `--task` flag for single-shot use
- **Watch mode**: `--watch <file>` auto-runs prompt on file changes
- **LLAMA.md**: LLM-generated project context file, auto-loaded each session
- **Plugin system**: drop `.py` files in `plugins/` for custom tools
- **Global install**: `uv tool install llama-agentic` → `llama-agent` in PATH
- **Config hierarchy**: `~/.config/llama-agentic/config.env` → `.env`
- **First-run wizard**: auto-triggers on fresh install
- **Auto server management**: start/stop llama-server subprocess automatically
- **Model downloader**: `llama-agent download <alias>` via huggingface-hub
- **Doctor command**: `llama-agent doctor` — environment diagnostics
- **`.llamaignore`**: protect files from agent read/write access
- **Token budget display**: estimated token count shown after each turn
- **Streaming shell output**: real-time stdout from `run_shell`
- **MCP client**: connect to any MCP server (stdio or HTTP), auto-register tools
- **MCP CLI**: `llama-agent mcp list/add/remove/connect`
- **Session stats**: `/cost` command shows turns, tool calls, tokens, elapsed time
- **GitHub Actions CI**: test on Python 3.11 and 3.12
- **GitHub Actions CD**: auto-publish to PyPI on version tags
- **Shell completions**: `llama-agent completions` for bash/zsh/fish

[Unreleased]: https://github.com/muhaimin/llama-agentic/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/muhaimin/llama-agentic/releases/tag/v0.1.0
