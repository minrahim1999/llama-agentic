# CLAUDE.md — llama-agentic

## Project Summary

A local agentic AI CLI powered by **llama.cpp** (`llama-server`). Implements a ReAct (Reason → Act → Observe) loop with Python tool execution. Zero cloud dependency — everything runs on the local machine.

## Architecture

- **LLM backend**: `llama-server` (installed at `/opt/homebrew/bin/llama-server`) — OpenAI-compatible HTTP API on port 8080
- **LLM client**: `openai` Python SDK pointed at `http://localhost:8080/v1`
- **Agent loop**: `agent/core.py` — parses tool calls from model output, dispatches to tools, injects observations back
- **CLI**: `agent/cli.py` — interactive REPL using `rich` for output formatting
- **Tools**: `agent/tools/` — file, shell, code, search operations

## Commands

```bash
# Start the LLM server (required before running the agent)
./scripts/start_server.sh

# Run interactive agent
python -m agent.cli

# Single-shot task
python -m agent.cli --task "your task here"

# With context directory injected
python -m agent.cli --context ./my-project

# Run tests
pytest tests/
```

## Environment Variables (.env)

```
LLAMA_SERVER_URL=http://localhost:8080/v1
LLAMA_MODEL_PATH=/path/to/model.gguf
LLAMA_CTX_SIZE=8192
LLAMA_N_GPU_LAYERS=-1
UNSAFE_MODE=false          # set true to skip tool confirmation prompts
```

## Tool Safety Rules

- `run_shell` and `write_file` always prompt the user for confirmation before executing **unless** `UNSAFE_MODE=true`
- `run_python` executes in a subprocess, never with `eval()`
- Never auto-delete files without explicit user confirmation

## Code Conventions

- Python 3.10+, type hints everywhere
- Tools are registered with `@tool` decorator in `agent/tools/__init__.py`
- Tool schemas are auto-generated from function signatures + docstrings (Google style)
- Keep each tool function focused — one operation per function
- No LangChain, no LlamaIndex — plain Python agentic loop

## Recommended Models

Best GGUF models for tool-calling (download to a local path):
- `Qwen2.5-Coder-7B-Instruct-Q5_K_M.gguf` — best for code tasks
- `Qwen2.5-7B-Instruct-Q5_K_M.gguf` — general agent
- `Llama-3.1-8B-Instruct-Q5_K_M.gguf` — general agent
- `Mistral-7B-Instruct-v0.3-Q5_K_M.gguf` — fastest

## Implementation Status

See `PLAN.md` for the phased implementation plan and checklist.

## Key Files

| File | Purpose |
|---|---|
| `agent/cli.py` | Entry point, REPL loop |
| `agent/core.py` | ReAct agent loop |
| `agent/llama_client.py` | OpenAI SDK wrapper for llama-server |
| `agent/config.py` | Pydantic settings from .env |
| `agent/tools/__init__.py` | Tool registry and decorator |
| `agent/memory.py` | Persistent memory read/write |
| `scripts/start_server.sh` | Launches llama-server with correct flags |

## llama-server Notes

llama-server is installed via Homebrew at `/opt/homebrew/bin/llama-server`.

Key flags:
```bash
llama-server \
  --model /path/to/model.gguf \
  --port 8080 \
  --ctx-size 8192 \
  --n-gpu-layers -1 \        # full Metal GPU offload on Apple Silicon
  --parallel 1 \
  --chat-template chatml      # adjust per model
```

The server exposes:
- `GET /v1/models`
- `POST /v1/chat/completions` (supports `tools` and `tool_choice`)
- `POST /v1/completions`
