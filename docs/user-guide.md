# User Guide

---

## Running the agent

### Interactive REPL (default)

```bash
llama-agent
```

Starts an interactive session with full history, memory, and REPL commands.

### Single task (non-interactive)

```bash
llama-agent --task "Refactor the login function to use bcrypt"
```

Runs one turn and exits. The session is auto-saved to `sessions/`.

### With project context

```bash
llama-agent --context ./my-project
```

Injects a file tree + README into the system prompt. Useful when starting a session outside your project directory.

### Resume a previous session

```bash
llama-agent --resume sessions/chat_2026-01-15_14-30.json
# or by partial name
llama-agent --resume 14-30
```

### Watch a file for changes

```bash
llama-agent --watch ./src/main.py
```

Prompts for a template string (e.g. `"Review changes to {path}: {content}"`) and re-runs it every time the file is modified. Useful for continuous review or auto-documentation.

---

## CLI flags

| Flag | Short | Description |
|---|---|---|
| `--task TEXT` | `-t` | Run a single task and exit |
| `--context PATH` | `-c` | Inject a directory as project context |
| `--resume FILE` | `-r` | Resume a saved session |
| `--model NAME` | `-m` | Override the active model name |
| `--watch FILE` | `-w` | Watch a file and re-prompt on change |
| `--unsafe` | | Skip all confirmation prompts |
| `--no-autosave` | | Disable auto-save on exit |
| `--init` | | Generate LLAMA.md and exit |
| `--setup` | | Re-run the first-run setup wizard |

---

## REPL commands

Type these inside the interactive session:

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/init [--force]` | Generate LLAMA.md for the current project |
| `/refresh` | Re-generate LLAMA.md (update project knowledge) |
| `/add <glob>` | Attach files to conversation context |
| `/undo <file>` | Restore a file from its last `.bak` backup |
| `/model [name]` | Show or switch the active model |
| `/tools` | List all registered tools with descriptions |
| `/reset` | Clear conversation history (keep memory) |
| `/save [name]` | Save the session to disk |
| `/load <name>` | Load a previously saved session |
| `/sessions` | List all saved sessions |
| `/memory` | List all persistent memory keys |
| `/forget <key>` | Delete a memory entry |
| `/history` | Show how many messages are in the context window |
| `/verbose` | Toggle full tool output on/off |
| `/cost` | Show session stats (turns, tool calls, tokens, time) |
| `/exit` | Quit (auto-saves the session) |

---

## Attaching files to context

Use `/add` to inject file content into the conversation:

```
/add src/auth.py
/add src/**/*.py
/add README.md pyproject.toml
```

Files are added as user messages with their content. The agent can then reason about them without needing to call `read_file`.

---

## Confirmation prompts

The following tools require your explicit approval before running:

| Tool | Why |
|---|---|
| `write_file` | Creates or overwrites a file |
| `edit_file` | Modifies an existing file |
| `delete_file` | Permanently deletes a file |
| `run_shell` | Runs an arbitrary shell command |
| `run_python` | Executes Python code |
| `git_commit` | Creates a git commit |

When a confirmation appears, type `y` and press Enter to approve. Pressing Enter alone defaults to **No**.

### Skipping confirmations

For automation or when you trust the task:

```bash
llama-agent --unsafe --task "Run all tests and fix any failures"
```

Or set permanently in your config:

```
UNSAFE_MODE=true
```

### Verbose tool output

By default, tool output is hidden (only a one-line status is shown). To see full tool results:

```
/verbose
```

Toggle it back off with `/verbose` again.

---

## Sessions

Sessions are the full conversation history (all messages, tool calls, observations).

### Auto-save

Sessions are automatically saved when you exit:
- Interactive sessions: saved as `sessions/chat_<timestamp>.json`
- `--task` sessions: saved as `sessions/task_<timestamp>.json`

Disable with `--no-autosave`.

### Manual save and load

```
/save my-refactor-session
/load my-refactor-session
```

```
/sessions
```

---

## Persistent memory

The agent can remember facts across sessions using named memory entries.

The model saves things with `save_memory` and reads them with `recall_memory`. You can also manage memory from the REPL:

```
/memory               → list all keys
/forget project-stack → delete a specific key
```

Memory files are stored in:
- `memory/` (global, when LLAMA.md is not present)
- `.llama-agentic/memory/` (per-project, when LLAMA.md is present)

Example usage in a conversation:

```
You:   Remember that this project uses PostgreSQL 16 and SQLAlchemy 2.0

Agent: ⚙ save_memory  ✓  Saved 'db-stack'
       Got it — I'll remember that for future sessions.
```

---

## LLAMA.md — project knowledge

`LLAMA.md` is a file the agent generates (via `/init`) and auto-loads at the start of every session. It gives the agent context about your project without burning tokens on file reads.

### Generate

```bash
llama-agent --init
# or inside the REPL:
/init
```

### What it contains

- Project summary and purpose
- Key files and their roles
- Tech stack and dependencies
- Common commands (build, test, run)
- Coding conventions

### Keep it fresh

Run `/refresh` after major changes (new features, refactors, dependency changes).

---

## The ReAct loop

Each turn works like this:

1. **Reason** — the model reads the conversation and thinks about what to do
2. **Act** — the model calls a tool (file read, shell command, web search, etc.)
3. **Observe** — the tool result is injected back into the conversation
4. Repeat up to `MAX_TOOL_ITERATIONS` times (default: 20)
5. **Respond** — once the task is done, the model gives a final answer

If the model hits the iteration limit without finishing, you'll see `[max iterations reached]`. You can continue the task by sending a follow-up message.

---

## Context window management

llama-agentic uses a **sliding window** to keep the conversation within the model's context limit.

- `HISTORY_WINDOW=20` keeps the last 20 user turns in context
- Older turns are **summarized** (not dropped) when the window is exceeded
- Tool results are truncated at `TOOL_OUTPUT_LIMIT=8000` chars

Check current window usage:

```
/history
→ 47 total msgs · 31 in window (window=20 turns)
```

---

## Docker

```bash
# Build
docker build -t llama-agentic .

# Run (points to llama-server running on the host)
docker run -it \
  -e LLAMA_SERVER_URL=http://host.docker.internal:11435/v1 \
  -v ~/.config/llama-agentic:/root/.config/llama-agentic \
  -v ~/.local/share/llama-agentic:/root/.local/share/llama-agentic \
  llama-agentic
```
