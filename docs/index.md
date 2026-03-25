# llama-agentic Documentation

A local agentic AI CLI powered by **llama.cpp** — no cloud, no API keys, runs entirely on your machine.

---

## Contents

| Guide | Description |
|---|---|
| [Getting Started](getting-started.md) | Installation, setup, first run |
| [User Guide](user-guide.md) | REPL usage, sessions, memory, watch mode |
| [Tools Reference](tools-reference.md) | All 22 built-in tools with examples |
| [Configuration](configuration.md) | Environment variables and config hierarchy |
| [Plugin Development](plugin-development.md) | Write and distribute custom tools |
| [MCP Integration](mcp-integration.md) | Connect to GitHub, databases, browsers and more |

---

## What is llama-agentic?

llama-agentic is a terminal-based AI agent that runs **fully local** using [llama.cpp](https://github.com/ggerganov/llama.cpp). It implements a **ReAct loop** (Reason → Act → Observe) — the agent thinks, picks a tool, uses it, observes the result, and repeats until the task is done.

```
You:   Refactor the auth module to use JWT, run the tests, and commit

Agent: ⚙ view_file    ✓  Read 142 lines from agent/auth.py
       ⚙ edit_file    ✓  Applied JWT changes (+28/-14)
       ⚙ run_shell    ✓  pytest tests/test_auth.py — 12 passed
       ⚙ git_commit   ✓  refactor: replace session auth with JWT
       Done — all tests pass and changes are committed.
```

### Key features

- **22 built-in tools** — file, shell, Python, git, web, memory
- **MCP client** — connect to MCP servers over the currently supported transports
- **A2A client** — delegate work to remote A2A JSON-RPC agents
- **Diff-aware editing** — shows a syntax-highlighted diff before writing
- **Plugin system** — load custom tools from configured plugin directories
- **`.llamaignore`** — protect sensitive files from agent access
- **Persistent memory** — save facts across sessions
- **LLAMA.md** — LLM-generated project context, auto-loaded every session
- **Session save/load** — auto-saved on exit, resumable with `--resume`

---

## Quick reference

```bash
llama-agent                                       # interactive REPL
llama-agent --task "find and fix failing tests"   # single task
llama-agent --init                                # generate LLAMA.md
llama-agent doctor                                # check environment
llama-agent download qwen2.5-coder-7b             # download a model
```

---

## Recommended model

`Qwen2.5-Coder-7B-Instruct-Q4_K_M` — best balance of speed and tool-calling accuracy.

```bash
llama-agent download qwen2.5-coder-7b
```
