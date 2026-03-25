# llama-agentic

A local agentic AI CLI powered by **llama.cpp** — no cloud, no API keys, runs entirely on your machine.

Think Claude Code or Codex CLI, but driven by any GGUF model you have locally.

```
You: Refactor the auth module to use JWT, run the tests, and commit
Agent: [tool: view_file] agent/auth.py
       [tool: edit_file] Applied JWT changes (diff shown)
       [tool: run_shell] pytest tests/test_auth.py — 12 passed
       [tool: git_commit] "refactor: replace session auth with JWT"
       Done — all tests pass, committed.
```

---

## Features

- **ReAct loop** — Reason → Act → Observe, up to 20 tool iterations per turn
- **22 built-in tools** — file, shell, Python, git, web fetch, search, memory
- **Diff-aware editing** — `edit_file` shows syntax-highlighted diff before writing, auto-backup with `/undo`
- **Git integration** — `git_status`, `git_diff`, `git_log`, `git_commit`
- **MCP client** — connect to any [Model Context Protocol](https://modelcontextprotocol.io) server (GitHub, Postgres, Slack, browser, …)
- **Conversation summarization** — automatically compresses old turns instead of dropping them
- **Persistent memory** — save facts across sessions with `save_memory`
- **LLAMA.md** — LLM-generated project context file, auto-loaded every session
- **Plugin system** — drop a `.py` file in `plugins/` to add custom tools instantly
- **`.llamaignore`** — protect sensitive files from agent read/write access
- **Session save/load** — auto-saved on exit, resumable with `--resume`
- **Token budget display** — estimated tokens shown after every turn
- **Watch mode** — `--watch <file>` re-runs a prompt every time a file changes
- **Works with any tool-calling GGUF** — Qwen2.5, Llama3, Mistral, DeepSeek

---

## Requirements

- macOS (Apple Silicon recommended) or Linux
- [llama.cpp](https://github.com/ggerganov/llama.cpp) — `brew install llama.cpp`
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) — `curl -LsSf https://astral.sh/uv/install.sh | sh`

---

## Installation

### Global install (recommended)

```bash
git clone <repo-url>
cd llama-agentic
uv tool install --editable .
```

`llama-agent` is now available from any directory in your PATH.

### From PyPI (once published)

```bash
pip install llama-agentic
# or
uv tool install llama-agentic
```

---

## Quick Start

### 1. Download a model

```bash
# Built-in downloader (saves to ~/.local/share/llama-agentic/models/)
llama-agent download qwen2.5-coder-7b

# Or list available aliases
llama-agent download
```

### 2. Start the server

```bash
./scripts/start_server.sh
# or let llama-agent auto-start it (set AUTO_START_SERVER=true in config)
```

### 3. Check your environment

```bash
llama-agent doctor
```

```
  Check                   Status   Detail
  Python ≥ 3.11           ✓ OK     3.12
  llama-server binary     ✓ OK     /opt/homebrew/bin/llama-server
  llama-server running    ✓ OK     qwen2.5-coder-7b
  huggingface-hub         ✓ OK     0.20.0
  GGUF model(s) in cache  ✓ OK     1 model(s)
  Global config           ✓ OK     ~/.config/llama-agentic/config.env
```

### 4. Generate project context

```bash
cd your-project/
llama-agent --init
```

This scans your project and asks the LLM to write a `LLAMA.md` file — a compact project knowledge base that's auto-loaded every session.

### 5. Start coding

```bash
llama-agent                                          # interactive REPL
llama-agent --task "Find and fix the failing tests"  # single task
llama-agent --resume sessions/chat_2026-01-01.json   # resume session
```

---

## CLI Reference

```
llama-agent [OPTIONS] COMMAND

Options:
  -t, --task TEXT      Run a single task non-interactively
  -c, --context PATH   Inject a directory as project context
  -r, --resume FILE    Resume a saved session
  -m, --model NAME     Override model name
  -w, --watch FILE     Re-run prompt whenever file changes
  --unsafe             Skip all confirmation prompts
  --no-autosave        Disable auto-save on exit
  --init               Generate LLAMA.md and exit
  --setup              Re-run the first-run setup wizard

Commands:
  doctor       Check environment: server, model, config
  download     Download a GGUF model from Hugging Face Hub
  models       List cached GGUF models
  update       Upgrade to the latest version
  completions  Print shell completion script (bash/zsh/fish)
  mcp          Manage MCP servers (list / add / remove / connect)
```

---

## REPL Commands

| Command | Description |
|---|---|
| `/init [--force]` | Generate LLAMA.md for this project |
| `/refresh` | Re-generate LLAMA.md (update project knowledge) |
| `/add <glob>` | Attach file(s) to context — supports globs (`/add src/**/*.py`) |
| `/undo <file>` | Restore last `.bak` backup of a file |
| `/model [name]` | Show or switch active model |
| `/tools` | List all registered tools |
| `/reset` | Clear conversation history |
| `/save [name]` | Save session to disk |
| `/load <name>` | Resume a saved session |
| `/sessions` | List saved sessions |
| `/memory` | List persistent memory keys |
| `/forget <key>` | Delete a memory entry |
| `/history` | Show context window stats |
| `/cost` | Session stats: turns, tool calls, ~tokens, time |
| `/help` | Show this list |
| `/exit` | Quit |

---

## Available Tools

### File & Edit
| Tool | Description |
|---|---|
| `read_file` | Read a file's full contents |
| `write_file` | Write/create a file |
| `view_file` | Read with line numbers (use before editing) |
| `edit_file` | Exact-string replacement with diff preview + auto-backup |
| `list_dir` | List files in a directory |
| `make_dir` | Create a directory |
| `delete_file` | Delete a file |

### Shell & Code
| Tool | Description |
|---|---|
| `run_shell` | Execute a shell command (streams output live) |
| `run_python` | Execute Python code in a subprocess |

### Git
| Tool | Description |
|---|---|
| `git_status` | Show working tree status |
| `git_diff` | Show unstaged or staged changes |
| `git_log` | Show recent commit history |
| `git_commit` | Create a commit |

### Web & System
| Tool | Description |
|---|---|
| `web_search` | Search the web via DuckDuckGo |
| `fetch_url` | Fetch and extract text from a URL |
| `system_info` | OS, Python, shell, installed tool versions |

### Memory
| Tool | Description |
|---|---|
| `save_memory` | Persist a fact across sessions |
| `recall_memory` | Read a saved memory |
| `list_memories` | List all memory keys |
| `delete_memory` | Delete a memory entry |

Tools marked with a lock 🔒 (`run_shell`, `run_python`, `write_file`, `delete_file`, `edit_file`, `git_commit`) show a confirmation prompt before executing unless `--unsafe` is set.

---

## MCP — Tool Marketplace

Connect to any [MCP server](https://modelcontextprotocol.io) to give the agent access to GitHub, databases, browsers, Slack, and more.

```bash
# Add a server
llama-agent mcp add filesystem \
  --command npx --args "-y @modelcontextprotocol/server-filesystem /" \
  --desc "Sandboxed file access"

llama-agent mcp add github \
  --command npx --args "-y @modelcontextprotocol/server-github"

# Test connection and list tools
llama-agent mcp connect filesystem

# List all configured servers
llama-agent mcp list

# Remove
llama-agent mcp remove github
```

Once added, MCP tools appear automatically as `mcp_<server>__<tool>` in the agent — no code changes needed.

**Popular MCP servers:**

| Server | What it adds |
|---|---|
| `@modelcontextprotocol/server-filesystem` | Sandboxed file access |
| `@modelcontextprotocol/server-github` | GitHub issues, PRs, repos |
| `@modelcontextprotocol/server-postgres` | PostgreSQL queries |
| `@modelcontextprotocol/server-slack` | Slack messages |
| `@modelcontextprotocol/server-brave-search` | Brave web search |
| `mcp-server-docker` | Docker container management |

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

---

## Shell Completions

```bash
# bash
echo 'eval "$(llama-agent completions bash)"' >> ~/.bashrc

# zsh
echo 'eval "$(llama-agent completions zsh)"' >> ~/.zshrc

# fish
llama-agent completions fish | source
```

---

## Configuration

Config is loaded from two files (later overrides earlier):

1. `~/.config/llama-agentic/config.env` — global defaults (created by `--setup`)
2. `./.env` — per-project overrides

| Variable | Default | Description |
|---|---|---|
| `LLAMA_SERVER_URL` | `http://localhost:8080/v1` | llama-server endpoint |
| `LLAMA_MODEL` | `local-model` | Model name sent to server |
| `LLAMA_CTX_SIZE` | `8192` | Context window size (tokens) |
| `LLAMA_N_GPU_LAYERS` | `-1` | GPU layers (`-1` = all, `0` = CPU only) |
| `AUTO_START_SERVER` | `true` | Auto-launch llama-server if not running |
| `AUTO_STOP_SERVER` | `false` | Shut down server when agent exits |
| `LLAMA_SERVER_BIN` | `llama-server` | Path or name of llama-server binary |
| `MODEL_CACHE_DIR` | `~/.local/share/llama-agentic/models` | Where downloaded models are stored |
| `UNSAFE_MODE` | `false` | Skip all confirmation prompts |
| `MAX_TOOL_ITERATIONS` | `20` | Max tool calls per agent turn |
| `HISTORY_WINDOW` | `20` | Conversation turns kept in context |
| `TOOL_OUTPUT_LIMIT` | `8000` | Max chars per tool result (0 = unlimited) |
| `STREAM` | `true` | Stream model output token by token |

---

## Recommended Models

| Model | Size | Best For |
|---|---|---|
| `Qwen2.5-Coder-7B-Instruct-Q4_K_M` | ~5 GB | Code tasks, editing — **recommended** |
| `Qwen2.5-7B-Instruct-Q4_K_M` | ~5 GB | General agent tasks |
| `Llama-3.2-3B-Instruct-Q4_K_M` | ~2 GB | Fast, low memory |
| `Mistral-7B-Instruct-v0.3-Q4_K_M` | ~4 GB | Fast, good for simple tasks |
| `DeepSeek-Coder-7B-Instruct-Q4_K_M` | ~4 GB | Code reasoning |

```bash
llama-agent download qwen2.5-coder-7b   # recommended
llama-agent download llama3.2-3b        # lightweight
```

**Minimum**: 7B parameter model for reliable tool calling. Models smaller than 3B answer directly without using tools.

---

## Project Structure

```
llama-agentic/
├── agent/
│   ├── cli.py              # Interactive REPL + subcommands
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
├── tests/                  # pytest suite (56 tests)
├── scripts/
│   ├── start_server.sh     # Launch llama-server
│   ├── switch_model.sh     # Hot-swap GGUF model
│   └── benchmark.py        # Tool-calling accuracy benchmark
├── .github/workflows/
│   ├── ci.yml              # Test on Python 3.11 + 3.12
│   └── publish.yml         # Publish to PyPI on version tag
├── Formula/
│   └── llama-agentic.rb    # Homebrew formula template
├── Dockerfile              # Docker image
└── CHANGELOG.md
```

---

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_core.py -v

# Benchmark tool-calling accuracy
uv run python scripts/benchmark.py
```

---

## Docker

```bash
# Build
docker build -t llama-agentic .

# Run (point to a running llama-server on the host)
docker run -it \
  -e LLAMA_SERVER_URL=http://host.docker.internal:8080/v1 \
  -v ~/.local/share/llama-agentic:/data \
  llama-agentic
```
