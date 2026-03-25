# QWEN.md — llama-agentic

## Project Overview

**llama-agentic** is a local agentic AI CLI powered by **llama.cpp** (`llama-server`). It implements a ReAct (Reason → Act → Observe) loop with Python tool execution, running entirely on the local machine with zero cloud dependency.

Think Claude Code or Codex CLI, but driven by any GGUF model locally via llama.cpp.

### Key Features
- **ReAct loop** — Reason → Act → Observe, up to 20 tool iterations per turn
- **22 built-in tools** — file operations, shell, Python, git, web search, fetch, memory
- **Diff-aware editing** — `edit_file` shows syntax-highlighted diff before writing, auto-backup with `/undo`
- **MCP client** — connect to any [Model Context Protocol](https://modelcontextprotocol.io) server (GitHub, Postgres, Slack, browser, etc.)
- **Conversation summarization** — automatically compresses old turns instead of dropping them
- **Persistent memory** — save facts across sessions with `save_memory`
- **LLAMA.md** — LLM-generated project context file, auto-loaded every session
- **Plugin system** — drop a `.py` file in `plugins/` to add custom tools
- **`.llamaignore`** — protect sensitive files from agent read/write access
- **Session save/load** — auto-saved on exit, resumable with `--resume`

---

## Architecture

```
User (CLI)
    │
    ▼
agent/cli.py          ← interactive REPL + --task / --init modes
    │
    ▼
agent/core.py         ← ReAct loop, tool dispatch, sliding-window history, summarization
    │
    ├──► llama-server (OpenAI-compatible HTTP API, port 8080)
    │         llama-server --model <model.gguf> --port 8080 --jinja
    │
    ├──► agent/tools/
    │         file.py     ← read_file, write_file, list_dir, make_dir, delete_file
    │         edit.py     ← view_file, edit_file (diff-aware with backup)
    │         shell.py    ← run_shell (confirmation-gated)
    │         code.py     ← run_python (subprocess-isolated)
    │         search.py   ← web_search (DuckDuckGo)
    │         git.py      ← git_status, git_diff, git_log, git_commit
    │         web.py      ← fetch_url, system_info
    │         memory.py   ← save/recall/list/delete memory (tool-facing)
    │
    ├──► agent/memory.py      ← persistent memory files (backend)
    ├──► agent/session.py     ← session save/load (JSON)
    ├──► agent/plugins.py     ← plugin auto-loader
    ├──► agent/mcp_client.py  ← MCP protocol client (stdio + HTTP)
    ├──► agent/init_cmd.py    ← /init → LLM-generated LLAMA.md
    └──► plugins/             ← drop .py files here for custom tools
```

### Tech Stack

| Component | Choice | Reason |
|---|---|---|
| LLM backend | `llama-server` (Homebrew) | Local, fast, OpenAI-compatible API |
| LLM client | `openai` Python SDK | Works with llama-server `/v1/chat/completions` |
| Tool protocol | OpenAI function-calling + content parser | Handles models that embed calls in text (Qwen2.5 XML) |
| CLI | `click` + `rich` | Pretty terminal output, syntax-highlighted diffs |
| Config | `pydantic-settings` | Global `~/.config/llama-agentic/config.env` + per-project `.env` |
| Package manager | `uv` | Fast, editable global install via `uv tool install` |
| Tests | `pytest` | Test suite in `tests/` |

---

## Building and Running

### Requirements
- macOS (Apple Silicon recommended) or Linux
- [llama.cpp](https://github.com/ggerganov/llama.cpp) — `brew install llama.cpp`
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) — `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Installation

```bash
# Clone and install
git clone <repo-url>
cd llama-agentic
uv tool install --editable .

# Now `llama-agent` is available in PATH
```

### Quick Start

```bash
# 1. Download a model (saves to ~/.local/share/llama-agentic/models/)
llama-agent download qwen2.5-coder-7b

# 2. Start the server (or let llama-agent auto-start it)
./scripts/start_server.sh

# 3. Check environment
llama-agent doctor

# 4. Generate project context
llama-agent --init

# 5. Start coding
llama-agent                                          # interactive REPL
llama-agent --task "Find and fix the failing tests"  # single task
llama-agent --resume sessions/chat_2026-01-01.json   # resume session
```

### Key Commands

```bash
# Run tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_core.py -v

# Benchmark tool-calling accuracy
uv run python scripts/benchmark.py

# Start server manually
./scripts/start_server.sh

# Switch GGUF model
./scripts/switch_model.sh /path/to/new-model.gguf
```

---

## Development Conventions

### Code Style
- Python 3.11+, type hints everywhere
- Tools registered with `@tool` decorator in `agent/tools/__init__.py`
- Tool schemas auto-generated from function signatures + Google-style docstrings
- No LangChain, no LlamaIndex — pure Python agentic loop

### Tool Safety Rules
- `run_shell`, `write_file`, `delete_file`, `run_python`, `edit_file`, `git_commit` require Y/n confirmation unless `UNSAFE_MODE=true`
- `run_python` executes in a subprocess, never with `eval()`
- Never auto-delete files without explicit user confirmation

### Project Structure

```
llama-agentic/
├── agent/
│   ├── cli.py              # Entry point, REPL loop
│   ├── core.py             # ReAct agent loop + summarization
│   ├── config.py           # Pydantic settings from .env
│   ├── llama_client.py     # OpenAI SDK → llama-server
│   ├── server_manager.py   # Auto-start/stop llama-server
│   ├── model_manager.py    # Download GGUF models from HF Hub
│   ├── mcp_client.py       # MCP protocol client (stdio + HTTP)
│   ├── mcp_config.py       # MCP server config (mcp.json)
│   ├── memory.py           # Persistent memory backend
│   ├── session.py          # Session save/load
│   ├── plugins.py          # Plugin auto-loader
│   ├── ignore.py           # .llamaignore enforcement
│   ├── stats.py            # Session stats (tokens, turns, time)
│   ├── doctor.py           # Environment diagnostics
│   ├── init_cmd.py         # LLM-assisted LLAMA.md generation
│   ├── setup.py            # First-run setup wizard
│   └── tools/
│       ├── __init__.py     # @tool registry + dispatch
│       ├── file.py         # read/write/list/delete
│       ├── edit.py         # view_file + edit_file (diff + backup)
│       ├── shell.py        # run_shell (streaming)
│       ├── code.py         # run_python
│       ├── search.py       # web_search
│       ├── git.py          # git_status/diff/log/commit
│       ├── web.py          # fetch_url + system_info
│       └── memory.py       # save/recall/list/delete memory
├── plugins/                # Drop custom tools here
├── tests/                  # pytest suite
├── scripts/
│   ├── start_server.sh     # Launch llama-server
│   ├── switch_model.sh     # Hot-swap GGUF model
│   ├── benchmark.py        # Tool-calling accuracy benchmark
│   └── install_global.sh   # Global install script
├── memory/                 # Global persistent memory (or .llama-agentic/)
├── sessions/               # Saved session logs
└── .llama-agentic/         # Per-project data (when LLAMA.md present)
```

### Testing Practices
- Tests in `tests/` directory using `pytest`
- Test files: `test_core.py`, `test_tools.py`, `test_edit.py`, `test_memory.py`, `test_parser.py`, `test_plugins.py`
- Run all tests: `uv run pytest tests/ -v`

---

## Environment Variables

Config hierarchy (later overrides earlier):
1. `~/.config/llama-agentic/config.env` — global defaults
2. `./.env` — per-project overrides

| Variable | Default | Description |
|---|---|---|
| `LLAMA_SERVER_URL` | `http://localhost:8080/v1` | llama-server endpoint |
| `LLAMA_MODEL` | `local-model` | Model name sent to server |
| `LLAMA_CTX_SIZE` | `8192` | Context window size (tokens) |
| `LLAMA_N_GPU_LAYERS` | `-1` | GPU layers (`-1` = all, `0` = CPU only) |
| `AUTO_START_SERVER` | `true` | Auto-launch llama-server if not running |
| `AUTO_STOP_SERVER` | `false` | Shut down server when agent exits |
| `UNSAFE_MODE` | `false` | Skip all confirmation prompts |
| `MAX_TOOL_ITERATIONS` | `20` | Max tool calls per agent turn |
| `HISTORY_WINDOW` | `20` | Conversation turns kept in context |
| `TOOL_OUTPUT_LIMIT` | `8000` | Max chars per tool result (0 = unlimited) |

---

## Recommended Models

| Model | Size | Best For |
|---|---|---|
| `Qwen2.5-Coder-7B-Instruct-Q4_K_M` | ~5 GB | Code tasks — **recommended** |
| `Qwen2.5-7B-Instruct-Q4_K_M` | ~5 GB | General agent |
| `Llama-3.2-3B-Instruct-Q4_K_M` | ~2 GB | Fast, low memory |
| `Mistral-7B-Instruct-v0.3-Q4_K_M` | ~4 GB | Fast, lightweight |

**Note**: Models below 7B cannot reliably use tools. They answer directly without calling functions.

---

## Key Files

| File | Purpose |
|---|---|
| `agent/cli.py` | Entry point, interactive REPL |
| `agent/core.py` | ReAct agent loop with summarization |
| `agent/llama_client.py` | OpenAI SDK wrapper for llama-server |
| `agent/config.py` | Pydantic settings from .env |
| `agent/tools/__init__.py` | Tool registry and decorator |
| `agent/memory.py` | Persistent memory read/write |
| `scripts/start_server.sh` | Launches llama-server with correct flags |
| `README.md` | Full user-facing documentation |
| `PLAN.md` | Implementation plan and roadmap |
| `CHANGELOG.md` | Version history |

---

## MCP — Model Context Protocol

Connect to any MCP server to give the agent access to GitHub, databases, browsers, Slack, and more.

```bash
# Add a server
llama-agent mcp add filesystem \
  --command npx --args "-y @modelcontextprotocol/server-filesystem /"

llama-agent mcp add github \
  --command npx --args "-y @modelcontextprotocol/server-github"

# List configured servers
llama-agent mcp list

# Test connection and list tools
llama-agent mcp connect filesystem

# Remove
llama-agent mcp remove github
```

Once added, MCP tools appear automatically as `mcp_<server>__<tool>` in the agent.

---

## Plugin System

Drop any `.py` file into `plugins/` and it's auto-loaded at startup:

```python
# plugins/my_tools.py
from agent.tools import tool

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: City name to look up.
    """
    return f"Weather in {city}: sunny, 22°C"
```

To disable without deleting, prefix the filename with `_` (e.g. `_my_tools.py`).

---

## .llamaignore

Protect sensitive files from being read or modified by the agent:

```
# .llamaignore
.env
secrets/
**/*.key
/config/prod.json
```

Same syntax as `.gitignore`. The agent will refuse to read, write, or edit any matching path.
