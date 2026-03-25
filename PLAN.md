# llama-agentic — Build Plan

## Overview

Build a local agentic AI CLI (similar to Claude Code / Codex CLI) powered entirely by **llama.cpp** (`llama-server`). The agent runs a ReAct loop — Reason → Act → Observe — calling tools defined in Python, with no cloud dependency.

---

## Architecture

```
User (CLI)
    │
    ▼
agent/cli.py          ← interactive REPL + --task / --init modes
    │
    ▼
agent/core.py         ← ReAct loop, tool dispatch, sliding-window history
    │
    ├──► llama_server (OpenAI-compatible HTTP API, port 8080)
    │         llama-server --model <model.gguf> --port 8080 --jinja
    │
    ├──► agent/tools/
    │         file.py     ← read_file, write_file, list_dir, make_dir, delete_file
    │         edit.py     ← view_file, edit_file (diff-aware)
    │         shell.py    ← run_shell (confirmation-gated)
    │         code.py     ← run_python (subprocess-isolated)
    │         search.py   ← web_search (DuckDuckGo)
    │         memory.py   ← save/recall/list/delete memory (tool-facing)
    │
    ├──► agent/memory.py      ← persistent memory files (backend)
    ├──► agent/session.py     ← session save/load (JSON)
    ├──► agent/plugins.py     ← plugin auto-loader
    ├──► agent/init_cmd.py    ← /init → LLM-generated LLAMA.md
    ├──► agent/setup.py       ← first-run wizard
    └──► plugins/             ← drop .py files here for custom tools
```

---

## Tech Stack

| Component | Choice | Reason |
|---|---|---|
| LLM backend | `llama-server` (Homebrew) | Local, fast, OpenAI-compatible API |
| LLM client | `openai` Python SDK | Works with llama-server `/v1/chat/completions` |
| Tool protocol | OpenAI function-calling + content parser | Handles models that embed calls in text (Qwen2.5 XML) |
| CLI | `click` + `rich` | Pretty terminal output, syntax-highlighted diffs |
| Config | `pydantic-settings` | Global `~/.config/llama-agentic/config.env` + per-project `.env` |
| Package manager | `uv` | Fast, editable global install via `uv tool install` |
| Tests | `pytest` | 40 tests across 5 test files |

---

## Completed Phases

### ✅ Phase 1 — Foundation
- [x] Project scaffold: `pyproject.toml`, `uv` venv, directory structure
- [x] `llama_client.py` — thin `openai` SDK wrapper pointed at local server
- [x] `agent/core.py` — streaming ReAct loop
- [x] `agent/cli.py` — interactive REPL with `rich`
- [x] Config via `.env` + pydantic-settings
- [x] `scripts/start_server.sh` — launch `llama-server` with correct flags
- [x] Content-based tool call parser — handles Qwen2.5 XML/JSON fallback format

### ✅ Phase 2 — Tool System
- [x] Tool registry: decorator-based `@tool` registration with auto schema generation
- [x] Tools: `read_file`, `write_file`, `list_dir`, `make_dir`, `delete_file`
- [x] Tools: `run_shell` (confirmation-gated)
- [x] Tools: `run_python` (subprocess-isolated)
- [x] Tools: `web_search` (DuckDuckGo)
- [x] Tool schema auto-generation from function signatures + Google-style docstrings
- [x] Tool call loop: parse → dispatch → inject observation → re-prompt

### ✅ Phase 3 — Memory & Context
- [x] Sliding window history (configurable `HISTORY_WINDOW`, trims whole turns cleanly)
- [x] Persistent memory files (`memory/` dir) — auto-injected into system prompt
- [x] Memory tools: `save_memory`, `recall_memory`, `list_memories`, `delete_memory`
- [x] System prompt builder: context + memory + tool schemas
- [x] `--context <dir>` flag: reads CLAUDE.md/README/pyproject.toml + file tree
- [x] Session save/load: `/save`, `/load`, `/sessions`, auto-save on exit

### ✅ Phase 4 — Code Agent Mode
- [x] `/add <file>` slash command: inject file into conversation
- [x] `view_file` with line numbers (prerequisite for accurate editing)
- [x] `edit_file` — exact-string replacement, fails on ambiguity, returns unified diff
- [x] Diff preview in confirmation prompt (syntax-highlighted via `rich.syntax`)
- [x] `--task` flag: non-interactive single-shot mode
- [x] Session auto-saved after every `--task` run

### ✅ Phase 5 — Polish
- [x] Benchmark script (`scripts/benchmark.py`) — 9-case tool-calling accuracy suite
- [x] README.md — full setup, usage, tools, plugin guide, model recommendations
- [x] `--model` in REPL + `scripts/switch_model.sh` for full GGUF hot-swap
- [x] Plugin system — drop `.py` in `plugins/`, auto-loaded at startup
- [x] `scripts/install_global.sh` — one-step global install

### ✅ Phase 6 — Global Install & Project Init
- [x] Global install via `uv tool install --editable .` → `llama-agent` in PATH
- [x] Config hierarchy: `~/.config/llama-agentic/config.env` → `./.env`
- [x] First-run setup wizard (`--setup` flag, auto-triggers on fresh install)
- [x] `/init` REPL command + `--init` CLI flag — LLM-assisted LLAMA.md generation
- [x] LLAMA.md auto-loaded as project context when present in CWD
- [x] Per-project data dirs (`.llama-agentic/memory`, `.llama-agentic/sessions`) when LLAMA.md present
- [x] `run_init(yes=)` skip-confirm for `--unsafe` mode

---

## Next Release Plan

### Target: v0.2.2

**Theme**: make the current feature set trustworthy before adding more surface area.

The next release should focus on protocol correctness, safety boundaries, packaging consistency, and test coverage. The repo already presents itself as a local coding agent with MCP and plugin extensibility; the next release should make those promises defensible in real-world use.

### Release Goals

1. **Make MCP support real**
   - Replace the current newline-delimited stdio handling with spec-compatible MCP message framing.
   - Replace the current ad hoc HTTP `/tools` and `/tools/call` assumptions with actual MCP remote transport support.
   - Validate against at least two real MCP servers:
     - `@modelcontextprotocol/server-filesystem`
     - `@modelcontextprotocol/server-github`
   - Add integration tests for MCP tool discovery and tool invocation.

2. **Harden plugin loading**
   - Stop auto-loading `plugins/` from the current working directory by default.
   - Introduce an explicit plugin search path strategy:
     - package-provided example plugins for docs only
     - user plugin dir under config/home
     - optional per-project plugin dir only when explicitly enabled
   - Ensure the agent never imports arbitrary repo-local Python just because a project contains a `plugins/` folder.
   - Add tests covering plugin path resolution and opt-in per-project plugin loading.

3. **Close file safety gaps**
   - Enforce `.llamaignore` checks on destination paths for `move_file` and `copy_file`, not only the source.
   - Review all file-writing paths for consistent protected-path enforcement.
   - Add tests for protected destination paths, cross-directory moves, and ignored files outside the cwd-relative root.

4. **Fix packaging and developer workflow drift**
   - Add `ruff` to the dev dependency set so the documented lint command actually works.
   - Remove CI masking for lint once the project is clean enough to enforce it.
   - Reconcile package metadata, setup wizard presets, docs, and downloader aliases so all recommended model names are valid.
   - Verify `llama-agent download`, `llama-agent models`, and `llama-agent completions` match the docs exactly.

5. **Make runtime model selection deterministic**
   - Persist a concrete GGUF model path in config, not only the model identifier reported by the server.
   - Make auto-start prefer the configured model path rather than “first `.gguf` found”.
   - Improve doctor/setup output so users can see exactly which model path will be used.

6. **Strengthen release confidence**
   - Expand tests around:
     - MCP config and client behavior
     - server manager startup selection and fallback behavior
     - setup wizard model alias flow
     - `.llamaignore` edge cases
     - CLI subcommands that are currently documented as first-class workflows
   - Keep the next release limited to these reliability items unless a small fix is required to complete them.

### Non-Goals For v0.2.2

- No new major tool categories
- No telemetry expansion
- No additional distribution channels
- No major UI redesign
- No parallel tool execution work

### Exit Criteria

- Real MCP servers can be connected and used successfully from the CLI.
- Plugin loading no longer imports arbitrary cwd-local `plugins/` code by default.
- Protected paths cannot be bypassed through move/copy destination writes.
- `uv run ruff check agent/ tests/` passes in a fresh dev environment.
- Setup, docs, and downloader aliases agree on the supported recommended models.
- New coverage exists for MCP, setup, server management, and ignore-path enforcement.

### Candidate Work Breakdown

#### Track 1 — Protocol correctness
- [x] Rework `agent/mcp_client.py` transports to match MCP expectations
- [x] Add MCP integration tests using real or fixture-backed servers
- [ ] Update MCP docs to describe only supported transports and limitations

#### Track 2 — Safety and trust boundaries
- [x] Rework plugin discovery paths and defaults
- [x] Enforce `.llamaignore` destination checks for file mutations
- [ ] Audit destructive tools for consistent confirmation and path protection

#### Track 3 — Packaging and onboarding consistency
- [x] Add `ruff` to dev dependencies and unmask lint in CI
- [x] Reconcile setup presets, downloader aliases, and docs examples
- [x] Persist explicit configured model paths and surface them in doctor/setup

#### Track 4 — Test coverage and release validation
- [ ] Add targeted tests for MCP, setup, server selection, and ignore enforcement
- [ ] Run full validation:
  - `uv run pytest tests/ -v --tb=short`
  - `uv run ruff check agent/ tests/`
  - manual smoke tests for `download`, `models`, `doctor`, and `mcp connect`

---

## Known Gaps (not yet addressed)

| Gap | Impact | Planned In |
|---|---|---|
| Tool output not truncated — large file reads can overflow context | High | Phase 7 |
| No conversation summarization — old turns dropped silently | Medium | Phase 7 |
| No `download_model.sh` script | Low | Phase 7 |
| `main.py` is a uv-generated placeholder | Low | Phase 7 |
| `.gitignore` missing `.env`, `sessions/`, `memory/`, `LLAMA.md` | Medium | Phase 7 |
| No `test_core.py` — ReAct loop has no unit tests | Medium | Phase 7 |
| `run_shell` has no sandboxing (only confirmation gate) | Medium | Phase 8 |
| No git-aware tools (`git_status`, `git_diff`, `git_commit`) | Medium | Phase 8 |
| No `fetch_url` tool for reading web pages | Medium | Phase 8 |
| `/add` only accepts single file, not globs | Low | Phase 8 |
| No `/undo` for edit_file (no backup before write) | Medium | Phase 8 |
| No `/refresh` to update an existing LLAMA.md | Low | Phase 8 |
| No token usage tracking / context budget display | Low | Phase 9 |
| No streaming output for long-running shell commands | Low | Phase 9 |
| No `.llamaignore` to protect sensitive files | Medium | Phase 9 |
| Async: core loop is synchronous | Low | Phase 9 |

---

## Enhancement Plan

### Phase 7 — Robustness & Housekeeping
- [x] **Tool output truncation**: cap all tool results at N chars (configurable `TOOL_OUTPUT_LIMIT=8000`), append `...(truncated)` notice
- [x] **Fix `.gitignore`**: add `.env`, `sessions/`, `memory/`, `LLAMA.md`, `.llama-agentic/`
- [x] **Remove `main.py`** placeholder (it conflicts with the `llama-agent` entry point)
- [x] **`scripts/download_model.sh`**: interactive script to browse and download recommended GGUF models from HuggingFace via `llama-cli --hf-repo`
- [x] **`tests/test_core.py`**: unit tests for ReAct loop — mock LLM, verify tool dispatch, windowing, history structure
- [x] **Server health check on startup**: detect if llama-server is unreachable and print actionable message (`./scripts/start_server.sh`) instead of raw OpenAI connection error

### Phase 8 — Intelligence & Power Tools
- [x] **Conversation summarization**: when turns exceed `HISTORY_WINDOW`, call LLM to summarize the oldest N turns into a single "Summary so far" message instead of dropping them
- [x] **`agent/tools/git.py`**: `git_status`, `git_diff`, `git_log`, `git_commit` — git-aware tools behind confirmation gate
- [x] **`fetch_url` tool**: retrieve a URL's text content (via `httpx` + strip HTML tags); adds research capability without search
- [x] **`/add` glob support**: `/add src/**/*.py` — expand glob and attach multiple files at once
- [x] **`edit_file` backup**: write `.bak` file before every edit; `/undo` command restores the last backup
- [x] **`/refresh`**: re-run `/init` logic on an existing `LLAMA.md`, preserving any manual edits via diff-merge
- [x] **`system_info` tool**: returns OS, Python version, installed packages — useful for debugging tasks

### Phase 9 — UX & Performance
- [x] **Token budget display**: estimate and show tokens used / remaining after each turn (use `tiktoken` or char-based estimate)
- [x] **Streaming shell output**: for `run_shell`, stream stdout in real-time instead of blocking until process exits
- [x] **`.llamaignore`**: file-based deny-list that prevents the agent from reading/editing specified paths (like `.gitignore` syntax)
- [x] **`/cost` command**: show session stats — turns, tool calls, estimated tokens, wall-clock time
- [x] **`--watch <file>`**: monitor a file for changes and auto-feed a prompt to the agent when it changes (for iterative development loops)
- [x] **Async core**: refactor `core.py` to use `asyncio` for non-blocking tool dispatch and potential parallel tool execution when model returns multiple calls

---

## Distribution & Ecosystem Roadmap

> Goal: make `llama-agent` installable with a single command and connected to the broader MCP tool ecosystem — comparable to how Claude Code, Codex CLI, and Gemini CLI work.

### Why it's different from Claude Code / Codex

| | Claude Code / Codex / Gemini | llama-agentic |
|---|---|---|
| Model | Cloud API — no local setup | Local GGUF — user needs llama.cpp |
| Install | `npm install -g` (no deps) | `pip install` + llama.cpp + model |
| Tools | MCP ecosystem | Plugin files + MCP (planned) |
| Offline | No | Yes — fully air-gapped |

The local model requirement is permanent — that's the whole point. But everything else (distribution, server management, model download, MCP tools) can match or exceed cloud tools.

---

### Phase 10 — One-Command Install & Auto-managed Server

**Goal**: `pip install llama-agentic` → `llama-agent` works. No manual server, no manual model download.

- [x] **PyPI publishing**: set up `pyproject.toml` classifiers, version management, GitHub Actions CI/CD pipeline for `pip install llama-agentic` / `uv tool install llama-agentic`
- [x] **`agent/server_manager.py`**: auto-start/stop llama-server as a subprocess
  - On agent start: check if server is reachable → if not, auto-launch it
  - On agent exit: optionally shut down the server (configurable `AUTO_STOP_SERVER=false`)
  - Show startup progress bar while model loads
  - Handle port conflicts gracefully
- [x] **`agent/model_manager.py`**: built-in model downloader
  - `llama-agent --download` → interactive menu of recommended models
  - Downloads via `huggingface-hub` Python library (no manual HF-repo commands)
  - Shows download progress bar
  - Auto-sets `LLAMA_MODEL_PATH` in global config after download
  - Stores models in `~/.local/share/llama-agentic/models/`
- [x] **`llama-agent doctor`** subcommand: diagnose environment
  - Check: llama.cpp installed? llama-server version? model exists? server reachable? Python version OK?
  - Print ✓/✗ for each, with fix suggestions
- [x] **Smarter setup wizard**: auto-detect installed GGUF files (searches `~/Library/Caches/llama.cpp/`, `~/.local/share/llama-agentic/models/`), offer them as choices

### Phase 11 — MCP Client (Tool Marketplace)

**Goal**: connect to any MCP server to access GitHub, databases, browsers, APIs — the same ecosystem Claude Code uses.

**What is MCP?** Model Context Protocol (by Anthropic) — an open standard where tool/resource providers expose a JSON-RPC interface. Hundreds of community MCP servers exist. Being an MCP client means the agent gets all of them for free.

- [x] **`agent/mcp_client.py`**: MCP protocol client
  - Connect to local MCP servers via stdio (subprocess JSON-RPC)
  - Connect to remote MCP servers via HTTP/SSE
  - Discover available tools (`tools/list` RPC call)
  - Execute tools (`tools/call` RPC call)
  - Auto-convert MCP tool schemas → `@tool` registry format
- [x] **MCP config file**: `~/.config/llama-agentic/mcp.json`
  ```json
  {
    "servers": {
      "github": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"] },
      "filesystem": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/"] },
      "postgres": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://..."] }
    }
  }
  ```
- [x] **`llama-agent mcp list`**: list configured MCP servers and their tools
- [x] **`llama-agent mcp add <name>`**: interactive wizard to add an MCP server
- [x] **`llama-agent mcp remove <name>`**: remove an MCP server
- [x] **Per-project MCP override**: `.llama-agentic/mcp.json` overrides global config for that project
- [x] **MCP resources support**: expose MCP `resources` (file/db content) as read-only context injection

**Popular MCP servers to test against:**
| Server | What it adds |
|---|---|
| `@modelcontextprotocol/server-filesystem` | Sandboxed file access |
| `@modelcontextprotocol/server-github` | GitHub issues, PRs, repos |
| `@modelcontextprotocol/server-postgres` | PostgreSQL queries |
| `@modelcontextprotocol/server-slack` | Slack messages |
| `@modelcontextprotocol/server-brave-search` | Brave web search API |
| `mcp-server-docker` | Docker container management |

### Phase 12 — Distribution Polish

**Goal**: the final mile from "works for me" to "works for everyone".

- [x] **`CHANGELOG.md`** + semantic versioning (`v0.1.0`, `v0.2.0`, etc.)
- [x] **GitHub Actions**: CI runs tests on push; CD publishes to PyPI on tag
- [x] **Homebrew formula** (`brew install llama-agentic`): tap for macOS users who already have Homebrew
- [x] **Shell completions**: generate bash/zsh/fish completions via `click`
- [x] **`llama-agent update`** subcommand: `pip install --upgrade llama-agentic` with changelog display
- [x] **Telemetry opt-in**: anonymous usage stats (which models, which tools, crash reports) — opt-in only, helps prioritise development
- [x] **Docker image**: `docker run llama-agentic/agent` for fully sandboxed use (model volume-mounted)

---

## Recommended Models (GGUF, tool-calling capable)

| Model | Size | Best For |
|---|---|---|
| Qwen2.5-Coder-7B-Instruct-Q4_K_M | ~5 GB | Code tasks — **recommended** |
| Qwen2.5-7B-Instruct-Q4_K_M | ~5 GB | General agent |
| Llama-3.1-8B-Instruct-Q4_K_M | ~5 GB | General agent |
| Mistral-7B-Instruct-v0.3-Q4_K_M | ~4 GB | Fast, lightweight |
| DeepSeek-Coder-V2-Lite-Q4_K_M | ~9 GB | Complex reasoning + code |

**Note**: Models below 7B (e.g. Qwen2-1.5B) cannot reliably use tools. They answer directly without calling functions.

---

## Key Design Decisions

1. **OpenAI-compatible API** — llama-server's `/v1/chat/completions` + `openai` SDK, no wrapper changes needed.
2. **Dual tool-call parsing** — primary: OpenAI `tool_calls` field; fallback: parse `<functionCalls>`, `<function_call>`, ` ```json ` blocks from content. Handles Qwen2.5 and similar models that embed tool calls in text.
3. **No framework lock-in** — pure Python ReAct loop. No LangChain, no LlamaIndex.
4. **Safety by default** — `run_shell`, `write_file`, `delete_file`, `run_python`, `edit_file` all require Y/n confirmation unless `UNSAFE_MODE=true`.
5. **Streaming everywhere** — SSE streaming for real-time token output; tool observations shown inline.
6. **Plugin-first extensibility** — new tools = drop a `.py` file in `plugins/`. No core changes needed.
7. **LLAMA.md as project memory** — analogous to CLAUDE.md; generated by `/init`, auto-loaded each session.

---

## File Structure (current)

```
llama-agentic/
├── CLAUDE.md                    ← project guide for Claude Code
├── PLAN.md                      ← this file
├── README.md                    ← user-facing documentation
├── pyproject.toml               ← package + entry point (llama-agent)
├── .env / .env.example
├── scripts/
│   ├── start_server.sh          ← launch llama-server
│   ├── switch_model.sh          ← hot-swap GGUF model
│   ├── install_global.sh        ← uv/pipx global install
│   └── benchmark.py             ← tool-calling accuracy suite
├── agent/
│   ├── cli.py                   ← REPL + --task / --init entry point
│   ├── core.py                  ← ReAct loop + content-based tool parser
│   ├── config.py                ← pydantic settings, global config hierarchy
│   ├── llama_client.py          ← openai SDK → llama-server
│   ├── memory.py                ← persistent memory backend
│   ├── session.py               ← session save/load
│   ├── plugins.py               ← plugin auto-loader
│   ├── setup.py                 ← first-run wizard
│   ├── init_cmd.py              ← /init → LLAMA.md generation
│   └── tools/
│       ├── __init__.py          ← @tool registry + dispatch + schema gen
│       ├── file.py              ← read/write/list/delete/mkdir
│       ├── edit.py              ← view_file + edit_file (diff-aware)
│       ├── shell.py             ← run_shell
│       ├── code.py              ← run_python
│       ├── search.py            ← web_search
│       └── memory.py            ← memory tools (agent-facing)
├── plugins/
│   └── example_plugin.py        ← reference plugin
├── memory/                      ← global persistent memory (or .llama-agentic/)
├── sessions/                    ← saved session logs
└── tests/
    ├── test_tools.py
    ├── test_edit.py
    ├── test_memory.py
    ├── test_parser.py
    └── test_plugins.py
```

---

## Quick Start (global install)

```bash
# Install once
./scripts/install_global.sh

# In any project
cd ~/my-project
llama-agent --init          # generate LLAMA.md
llama-agent                 # start interactive session (LLAMA.md auto-loaded)
llama-agent --task "..."    # single task, non-interactive
```
