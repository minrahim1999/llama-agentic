# CLAUDE.md — llama-agentic

## Project Summary

A local agentic AI CLI powered by **llama.cpp** (`llama-server`). Implements a ReAct (Reason → Act → Observe) loop with Python tool execution. Zero cloud dependency — everything runs on the local machine. Current version: **v0.3.0**.

## Architecture

- **LLM backend**: `llama-server` (binary name: `llama-server`, resolved from PATH or `llama_server_bin`) — OpenAI-compatible HTTP API on port **11435** by default
- **LLM client**: `openai` Python SDK pointed at `http://localhost:11435/v1`
- **Agent loop**: `agent/core.py` — parses tool calls from model output, dispatches to tools, injects observations back
- **CLI**: `agent/cli.py` — interactive REPL using `rich` + `prompt_toolkit` for output and tab-completion
- **Modes**: `agent/mode.py` — five execution modes (chat/plan/code/hybrid/review) that gate tool access and inject system-prompt instructions
- **Trust store**: `agent/trust.py` — persist per-tool or blanket confirmation decisions across sessions (project + global scopes)
- **UI tools**: `agent/tools/ui.py` — `ask_choice` / `ask_questions` let the agent present interactive arrow-key selectors to the user
- **Tools**: `agent/tools/` — file, shell, code, search, edit, git, web, memory, find, process, ui operations
- **MCP**: `agent/mcp_client.py` — connects to MCP servers (stdio + HTTP), dynamically registers their tools
- **A2A**: `agent/a2a_client.py` — connects to Agent-to-Agent JSON-RPC servers, registers remote tasks as tools
- **Plugins**: `agent/plugins.py` — loads Python plugin files from `plugins_dir` (and optionally `.llama-agentic/plugins/`)
- **Server manager**: `agent/server_manager.py` — auto-starts/stops `llama-server` as a background subprocess
- **Model manager**: `agent/model_manager.py` — downloads GGUF models from Hugging Face into `model_cache_dir`
- **Session**: `agent/session.py` — save/load named conversation sessions
- **Memory**: `agent/memory.py` + `agent/tools/memory.py` — persistent key/value memory across sessions

## Commands

```bash
# First-time setup wizard
python -m agent.cli  # triggers setup wizard on first run if no global config

# Run interactive agent (auto-starts llama-server if configured)
python -m agent.cli

# Single-shot task
python -m agent.cli --task "your task here"

# With context directory injected
python -m agent.cli --context ./my-project

# Skip auto-start (assume server already running)
python -m agent.cli --no-auto-start

# Switch active model
./scripts/switch_model.sh

# Install globally (creates ~/.local/bin/llama-agentic entry point)
./scripts/install_global.sh

# Run tests
pytest tests/
```

## Slash Commands (REPL)

| Command | Description |
|---|---|
| `/help` | Show available slash commands |
| `/init [--force]` | Generate `LLAMA.md` for this project |
| `/refresh` | Re-generate `LLAMA.md` from current project state |
| `/add <glob>` | Attach file(s) to the current chat context |
| `/undo <file>` | Restore the last `.bak` version of a file |
| `/model [name]` | Show or switch the active model |
| `/tools` | List all registered tools |
| `/tool <name>` | Show one tool's description and input schema |
| `/mode [name\|save]` | Show or switch the agent mode (chat/plan/code/hybrid/review) |
| `/bg` | List background processes and their recent output |
| `/clear` | Clear the terminal screen (keeps conversation history) |
| `/rewind [n]` | Undo the last n turns (default 1) |
| `/trust [revoke <key>]` | List or revoke saved trust entries |
| `/reset` | Clear conversation history |
| `/save [name]` | Save the current session |
| `/load <name>` | Load a saved session |
| `/sessions` | List saved sessions |
| `/memory` | List persistent memory keys |
| `/forget <key>` | Delete a memory entry |
| `/history` | Show history window stats |
| `/verbose` | Toggle full tool output |
| `/cost` | Show session token and tool-call stats |
| `/exit` | Quit the REPL |

## Config Hierarchy

Settings are loaded in this order (later entries override earlier):

1. `~/.config/llama-agentic/config.env` — global defaults, created by setup wizard
2. `./.env` — project-level overrides

## Environment Variables

```
# Server
LLAMA_SERVER_URL=http://localhost:11435/v1
LLAMA_SERVER_BIN=llama-server        # path or name in PATH
LLAMA_MODEL_PATH=/path/to/model.gguf # explicit GGUF path
LLAMA_MODEL=local-model              # model name passed to API
LLAMA_CTX_SIZE=8192
LLAMA_N_GPU_LAYERS=-1

# Agent behaviour
MAX_TOOL_ITERATIONS=20
UNSAFE_MODE=false          # set true to skip tool confirmation prompts
AGENT_MODE=hybrid          # chat | plan | code | hybrid | review
STREAM=true
MAX_OUTPUT_TOKENS=2048
HISTORY_WINDOW=20
TOOL_OUTPUT_LIMIT=8000     # chars; 0 = unlimited

# Server management
AUTO_START_SERVER=true     # auto-start llama-server if not running
AUTO_STOP_SERVER=false     # stop server on exit

# Data directories (default to ~/.local/share/llama-agentic/)
MODEL_CACHE_DIR=~/.local/share/llama-agentic/models
MEMORY_DIR=~/.local/share/llama-agentic/memory
SESSIONS_DIR=~/.local/share/llama-agentic/sessions

# Plugins
PLUGINS_DIR=~/.config/llama-agentic/plugins
ENABLE_PROJECT_PLUGINS=false
```

## Tool Safety Rules

- `run_shell`, `run_background`, `write_file`, `edit_file`, `run_python`, `delete_file`, `git_commit`, `kill_process`, `stop_background`, `move_file` all prompt for confirmation **unless** `UNSAFE_MODE=true`
- `edit_file` shows a unified diff preview before prompting for confirmation
- `run_python` executes in a subprocess, never with `eval()`
- Never auto-delete files without explicit user confirmation
- Confirmation decisions can be persisted via the trust store (`/trust`) to avoid repeat prompts

## Code Conventions

- Python 3.10+, type hints everywhere
- Tools are registered with `@tool` decorator in `agent/tools/__init__.py`
- Tool schemas are auto-generated from function signatures + docstrings (Google style)
- Keep each tool function focused — one operation per function
- No LangChain, no LlamaIndex — plain Python agentic loop

## Recommended Models

Best GGUF models for tool-calling (use `/model` or `model_manager` to download):
- `qwen2.5-coder-7b` — best for code tasks
- `qwen2.5-7b` — general agent
- `llama3.2-3b` — lightweight general agent
- `mistral-7b` — fast general agent
- `deepseek-coder-7b` — alternative for code tasks

Aliases are defined in `agent/model_manager.py:KNOWN_MODELS`.

## Implementation Status

See `PLAN.md` for the phased implementation plan and checklist.

## Key Files

| File | Purpose |
|---|---|
| `agent/cli.py` | Entry point, REPL loop, slash commands |
| `agent/core.py` | ReAct agent loop |
| `agent/llama_client.py` | OpenAI SDK wrapper for llama-server |
| `agent/config.py` | Pydantic settings from .env / global config |
| `agent/tools/__init__.py` | Tool registry and `@tool` decorator |
| `agent/tools/file.py` | File read/write |
| `agent/tools/shell.py` | Shell command execution |
| `agent/tools/code.py` | Python code execution |
| `agent/tools/edit.py` | In-place file editing with diff preview |
| `agent/tools/git.py` | Git operations |
| `agent/tools/web.py` | Web fetch / DuckDuckGo search |
| `agent/tools/find.py` | File and content search |
| `agent/tools/process.py` | Process management + background process registry |
| `agent/tools/ui.py` | Interactive choice prompts (`ask_choice`, `ask_questions`) |
| `agent/tools/memory.py` | Persistent memory tool |
| `agent/tools/search.py` | Local file/code search |
| `agent/memory.py` | Memory backend (read/write/list/delete) |
| `agent/session.py` | Save/load named sessions |
| `agent/stats.py` | Token and tool-call usage tracking |
| `agent/server_manager.py` | Auto-start/stop llama-server |
| `agent/model_manager.py` | Download GGUF models from Hugging Face |
| `agent/mcp_config.py` | MCP server config loading |
| `agent/mcp_client.py` | MCP stdio + HTTP client, dynamic tool registration |
| `agent/a2a_config.py` | A2A agent config loading |
| `agent/a2a_client.py` | A2A JSON-RPC client, dynamic tool registration |
| `agent/mode.py` | Execution modes — tool gating and system-prompt injections |
| `agent/prompt_ui.py` | Arrow-key selector UI (backs `ask_choice` / `ask_questions`) |
| `agent/trust.py` | Trust store — persist confirmation decisions per tool/command |
| `agent/plugins.py` | Plugin loader |
| `agent/init_cmd.py` | `/init` command — generates `LLAMA.md` |
| `agent/doctor.py` | Health check (server, model, deps) |
| `agent/setup.py` | First-run setup wizard |
| `agent/ignore.py` | Ignore patterns for context/tree building |
| `agent/autostart.py` | Autostart logic helpers |
| `scripts/start_server.sh` | Launches llama-server with correct flags |
| `scripts/switch_model.sh` | Switch the active model |
| `scripts/install_global.sh` | Install agent globally |

## llama-server Notes

`llama-server` is resolved from PATH (configurable via `LLAMA_SERVER_BIN`). Default port is **11435** (changed from 8080).

Key flags:
```bash
llama-server \
  --model /path/to/model.gguf \
  --port 11435 \
  --ctx-size 8192 \
  --n-gpu-layers -1 \        # full Metal GPU offload on Apple Silicon
  --parallel 1 \
  --chat-template chatml      # adjust per model
```

The server exposes:
- `GET /v1/models`
- `POST /v1/chat/completions` (supports `tools` and `tool_choice`)
- `POST /v1/completions`

## Project Context File (LLAMA.md)

Running `/init` generates a `LLAMA.md` file in the current directory. This is injected as system context when running the agent in that directory — similar to how `CLAUDE.md` works. Use `/refresh` to regenerate it.
