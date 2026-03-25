# llama-agentic

A local agentic AI CLI powered by **llama.cpp**. It runs on your machine, uses GGUF models, and exposes tools for files, shell commands, git, web access, memory, plugins, MCP servers, and A2A agents.

Think of it as a terminal coding agent driven by your local model instead of a hosted API.

```text
You:   Refactor the auth module to use JWT, run the tests, and commit

Agent: ⚙ view_file   ✓  Read agent/auth.py
       ⚙ edit_file   ✓  Applied JWT changes
       ⚙ run_shell   ✓  pytest tests/test_auth.py
       ⚙ git_commit  ✓  refactor: replace session auth with JWT
       Done — all tests pass and changes are committed.
```

---

## What it does

- Runs a **ReAct loop**: reason, choose a tool, observe results, repeat
- Works with **local llama.cpp models** through the OpenAI-compatible server API
- Includes **built-in tools** for files, editing, shell, Python, git, web, and memory
- Supports **MCP servers** so you can add GitHub, databases, browsers, Slack, and more
- Supports **A2A agents** so your local agent can delegate to remote JSON-RPC A2A agents
- Loads **LLAMA.md** automatically for project-specific context
- Supports **persistent memory**, **session save/load**, **watch mode**, and **plugin loading**

---

## Documentation

The repo docs are the primary guide set:

| Guide | Description |
|---|---|
| [Documentation Index](docs/index.md) | Overview of all guides |
| [Getting Started](docs/getting-started.md) | Install, setup, download a model, first run |
| [User Guide](docs/user-guide.md) | REPL usage, sessions, memory, watch mode |
| [Tools Reference](docs/tools-reference.md) | Built-in tools and examples |
| [Configuration](docs/configuration.md) | Environment variables and config hierarchy |
| [Plugin Development](docs/plugin-development.md) | Add custom tools |
| [MCP Integration](docs/mcp-integration.md) | Configure and use MCP servers |

---

## Requirements

| Requirement | Version | Install |
|---|---|---|
| macOS or Linux | macOS 12+ / Ubuntu 22+ | — |
| Python | 3.11+ | [python.org](https://python.org) |
| llama.cpp | latest | `brew install llama.cpp` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

Apple Silicon works well with Metal GPU offload by default.

---

## Installation

### From PyPI

```bash
pip install llama-agentic
# or
uv tool install llama-agentic
```

### From source

```bash
git clone https://github.com/minrahim1999/llama-agentic.git
cd llama-agentic
uv tool install --editable .
```

### Verify

```bash
llama-agent --help
```

---

## Quick Start

### 1. Run first-time setup

```bash
llama-agent
```

This creates `~/.config/llama-agentic/config.env` and can help detect `llama-server`, choose settings, and offer a starter model download.
It also saves a preferred `LLAMA_MODEL_PATH` so auto-start uses a deterministic GGUF file instead of guessing from the cache.

### 2. Download a model

```bash
llama-agent download
llama-agent download qwen2.5-coder-7b
```

Downloaded models are added to the cache and the selected file is persisted to `LLAMA_MODEL_PATH` automatically.

Recommended model:

```bash
llama-agent download qwen2.5-coder-7b
```

### 3. Start or verify the server

```bash
llama-agent doctor
llama-agent autostart enable
llama-agent autostart start
```

`autostart enable` and `autostart start` prefer the configured `LLAMA_MODEL_PATH` when it is set.

Or start it manually:

```bash
./scripts/start_server.sh /path/to/model.gguf
```

### 4. Generate project context

```bash
cd your-project
llama-agent --init
```

### 5. Start a session

```bash
llama-agent
llama-agent --task "Find and fix the failing tests"
```

---

## Common Commands

```bash
llama-agent                                       # interactive REPL
llama-agent --task "review the latest changes"    # one-shot task
llama-agent --resume sessions/chat_2026-01-15.json
llama-agent doctor                                # environment checks
llama-agent download qwen2.5-coder-7b             # download a model
llama-agent models                                # list cached models and the selected one
llama-agent mcp list                              # list configured MCP servers
llama-agent a2a list                              # list configured A2A agents
```

Common REPL commands:

- `/help`
- `/init`
- `/refresh`
- `/add <glob>`
- `/tools`
- `/memory`
- `/sessions`
- `/cost`
- `/exit`

See [docs/user-guide.md](docs/user-guide.md) for the full command list.

---

## Key Features

- **Diff-aware editing**: `edit_file` previews changes before writing and keeps `.bak` backups
- **Confirmation-gated actions**: destructive tools require approval unless `UNSAFE_MODE=true`
- **Persistent memory**: store facts across sessions
- **Session management**: save, load, resume, and inspect history
- **MCP integration**: dynamically register tools from external MCP servers over the currently supported transports
- **A2A integration**: register remote A2A agents as callable tools and inspect their Agent Cards
- **Plugin system**: load custom tools from configured plugin directories
- **`.llamaignore` support**: block reads and writes to protected paths

---

## Development

```bash
uv sync --dev
uv run pytest tests/ -v --tb=short
uv run ruff check agent/ tests/
uv build
```

Project layout and development conventions are documented in [AGENTS.md](AGENTS.md).

---

## License

MIT. See [LICENSE](LICENSE).
