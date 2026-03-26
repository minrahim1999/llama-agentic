# Changelog

All notable changes to llama-agentic are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

---

## [Unreleased]

## [0.3.1] — 2026-03-26

### Fixed
- **`run_shell` timeout**: timeout parameter now actually fires on hanging processes — stdout drain moved to a background thread so `proc.wait(timeout)` runs concurrently
- **`read_file` error handling**: returns a clean error string instead of crashing with `FileNotFoundError` or `PermissionError`
- **`list_dir` error handling**: `iterdir()` wrapped to return `"Error: permission denied"` instead of crashing
- **`git` error output**: git errors now show both stderr and stdout so no error detail is silently dropped
- **`run_background` duplicate guard**: calling `run_background` with an already-running command returns an informative message instead of spawning a duplicate process
- **`/bg` UI**: each background process now renders as a styled Rich panel (status, port, start time, monokai output) instead of a plain text dump
- **System prompt — tool capability**: explicitly lists `run_shell`, `run_background`, etc. as available tools; forbids the "I cannot run commands" refusal that small models revert to
- **HYBRID mode**: simplified execution paths — direct tool calls for simple requests, `ask_choice` gate only for complex multi-step changes; plain-text "yes/proceed" from user now treated as approval

## [0.2.1] — 2026-03-25

### Added
- **License file**: added a top-level MIT `LICENSE` file for GitHub and PyPI consumers

### Changed
- **README**: rewritten to match the structure and guidance in the `docs/` folder and reflect the current published install and setup flow

## [0.2.0] — 2026-03-25

### Added
- **Cross-platform installers**: `install.py` for macOS, Linux, and Windows plus `install.ps1` for Windows bootstrap setup
- **Auto-start management**: `llama-agent autostart enable|disable|status|start` to register `llama-server` on login or boot using launchd, systemd user services, or Windows Task Scheduler
- **Find tools**: `glob_files` for glob-based file discovery and `search_files` for regex content search
- **Process tools**: `process_list` and `kill_process` for basic process inspection and termination
- **File utilities**: `move_file` and `copy_file`
- **Git utilities**: `git_add` and `git_branch`
- **Documentation set**: new getting started, user guide, configuration, tool reference, MCP integration, plugin development, and docs index pages, plus a bundled `.docx` guide

### Changed
- **Setup wizard**: now checks free disk space, detects or attempts installation of `llama-server`, and can offer a starter model download when no cached model exists
- **CLI rendering**: improved streamed output formatting with better Markdown/code block display and clearer tool success or failure status lines
- **Shell tool**: `run_shell` now supports a working directory and inline environment variables, and appends non-zero exit codes to output
- **Doctor diagnostics**: now report auto-start service status
- **Default server port**: changed local `llama-server` defaults from `8080` to `11435` across config, setup, and startup scripts

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

[Unreleased]: https://github.com/muhaimin/llama-agentic/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/muhaimin/llama-agentic/releases/tag/v0.2.1
[0.2.0]: https://github.com/muhaimin/llama-agentic/releases/tag/v0.2.0
[0.1.0]: https://github.com/muhaimin/llama-agentic/releases/tag/v0.1.0
