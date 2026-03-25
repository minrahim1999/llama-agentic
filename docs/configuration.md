# Configuration

llama-agentic uses environment variables for configuration, loaded from two files in priority order (later overrides earlier):

1. `~/.config/llama-agentic/config.env` — global defaults (shared across all projects)
2. `./.env` — per-project overrides (in the directory where you run `llama-agent`)

The setup wizard (`llama-agent --setup`) creates the global config file interactively.

---

## All variables

### Server

| Variable | Default | Description |
|---|---|---|
| `LLAMA_SERVER_URL` | `http://localhost:11435/v1` | Base URL of the llama-server OpenAI-compatible API |
| `LLAMA_SERVER_BIN` | `llama-server` | Path or name of the llama-server binary |
| `AUTO_START_SERVER` | `true` | Auto-launch llama-server when the agent starts |
| `AUTO_STOP_SERVER` | `false` | Shut down llama-server when the agent exits |

### Model

| Variable | Default | Description |
|---|---|---|
| `LLAMA_MODEL` | `local-model` | Model name sent in API requests (shown in `/model`) |
| `LLAMA_MODEL_PATH` | _(none)_ | Preferred full path to the GGUF model file used by auto-start, `autostart`, `doctor`, and helper commands |
| `LLAMA_CTX_SIZE` | `8192` | Context window in tokens passed to llama-server |
| `LLAMA_N_GPU_LAYERS` | `-1` | GPU layers to offload (`-1` = all, `0` = CPU only) |
| `MODEL_CACHE_DIR` | `~/.local/share/llama-agentic/models` | Where `llama-agent download` saves GGUF files |

### Agent behaviour

| Variable | Default | Description |
|---|---|---|
| `UNSAFE_MODE` | `false` | Skip all confirmation prompts for destructive tools |
| `MAX_TOOL_ITERATIONS` | `20` | Maximum tool calls per agent turn before giving up |
| `HISTORY_WINDOW` | `20` | Conversation turns kept in the model's context window |
| `TOOL_OUTPUT_LIMIT` | `8000` | Maximum characters per tool result (0 = unlimited) |
| `STREAM` | `true` | Stream model output token-by-token to the terminal |

---

## Example global config

`~/.config/llama-agentic/config.env`:

```env
LLAMA_SERVER_URL=http://localhost:11435/v1
LLAMA_MODEL=Qwen2.5-Coder-7B-Instruct-Q4_K_M
LLAMA_MODEL_PATH=/Users/you/.local/share/llama-agentic/models/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf
LLAMA_CTX_SIZE=8192
LLAMA_N_GPU_LAYERS=-1
AUTO_START_SERVER=true
AUTO_STOP_SERVER=false
UNSAFE_MODE=false
MAX_TOOL_ITERATIONS=20
HISTORY_WINDOW=20
TOOL_OUTPUT_LIMIT=8000
```

---

## Example per-project config

`.env` in your project directory:

```env
# Use a faster, lighter model for this project
LLAMA_MODEL=Llama-3.2-3B-Instruct-Q4_K_M
LLAMA_MODEL_PATH=/Users/you/.local/share/llama-agentic/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf

# Allow all tool calls without prompting (CI / automation)
UNSAFE_MODE=true

# Keep more history in context for a complex codebase
HISTORY_WINDOW=30
LLAMA_CTX_SIZE=16384
```

`LLAMA_MODEL_PATH` is preferred over scanning the model cache. If it is unset, llama-agentic falls back to the first `.gguf` it finds in `MODEL_CACHE_DIR`.

---

## Per-project data directories

When a `LLAMA.md` file is present in the current directory, llama-agentic uses a `.llama-agentic/` folder inside your project instead of the global directories:

| Data type | Global path | Per-project path |
|---|---|---|
| Memory | `~/.local/share/llama-agentic/memory/` | `.llama-agentic/memory/` |
| Sessions | `~/.local/share/llama-agentic/sessions/` | `.llama-agentic/sessions/` |
| MCP config | `~/.config/llama-agentic/mcp.json` | `.llama-agentic/mcp.json` |
| A2A config | `~/.config/llama-agentic/a2a.json` | `.llama-agentic/a2a.json` |

Generate `LLAMA.md` with `llama-agent --init` to activate per-project isolation.

---

## A2A agent config

Configured A2A agents live in JSON files rather than `config.env`:

- Global: `~/.config/llama-agentic/a2a.json`
- Per-project: `.llama-agentic/a2a.json`

Example:

```json
{
  "agents": {
    "planner": {
      "url": "https://agent.example.com",
      "description": "Project planning agent",
      "enabled": true
    }
  }
}
```

You can manage this file through the CLI:

```bash
llama-agent a2a add planner --url https://agent.example.com
llama-agent a2a list
llama-agent a2a connect planner
```

When configured, enabled A2A agents are loaded at startup and exposed to the model as `a2a_<name>` tools.

---

## llama-server flags

When `AUTO_START_SERVER=true`, the server is launched with these flags derived from your config:

```bash
llama-server \
  --model $LLAMA_MODEL_PATH \
  --port 11435 \
  --ctx-size $LLAMA_CTX_SIZE \
  --n-gpu-layers $LLAMA_N_GPU_LAYERS \
  --jinja
```

The `--model` value comes from `LLAMA_MODEL_PATH` when it is set. Otherwise the agent falls back to the first cached `.gguf` it can find.

You can also start the server manually with full control:

```bash
./scripts/start_server.sh /path/to/model.gguf
```

---

## Recommended model settings by hardware

### Apple Silicon (M1/M2/M3)

```env
LLAMA_N_GPU_LAYERS=-1    # full Metal GPU offload
LLAMA_CTX_SIZE=8192
```

### CPU only (no GPU)

```env
LLAMA_N_GPU_LAYERS=0
LLAMA_CTX_SIZE=4096      # keep small for speed
```

### High-VRAM GPU (24 GB+)

```env
LLAMA_N_GPU_LAYERS=-1
LLAMA_CTX_SIZE=32768     # can afford larger context
```
