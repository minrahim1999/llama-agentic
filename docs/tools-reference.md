# Tools Reference

All 22 built-in tools available to the agent. Tools marked 🔒 require confirmation before executing (unless `UNSAFE_MODE=true`).

---

## File tools

### `read_file`

Read the full text content of a file.

```
path  — absolute or relative path to the file
```

**Example prompt:** `"Read agent/core.py and explain the ReAct loop"`

---

### `write_file` 🔒

Write text content to a file, creating it (and any missing parent directories) if it does not exist.

```
path     — file path to write to
content  — text content to write
```

**Example prompt:** `"Create a summary.md file with a brief description of this project"`

---

### `list_dir`

List files and directories at a path.

```
path  — directory to list (defaults to current directory)
```

**Example prompt:** `"List the files in the agent/tools/ directory"`

---

### `make_dir`

Create a directory and any missing parent directories.

```
path  — directory path to create
```

**Example prompt:** `"Create a docs/ folder"`

---

### `delete_file` 🔒

Permanently delete a file.

```
path  — path of the file to delete
```

**Example prompt:** `"Delete the old backup file tmp/old_config.bak"`

---

## Edit tools

### `view_file`

Read a file with line numbers. Use this before calling `edit_file` so you know the exact text to replace.

```
path        — file to read
start_line  — (optional) first line to show
end_line    — (optional) last line to show
```

**Example prompt:** `"Show me lines 40–80 of agent/cli.py"`

---

### `edit_file` 🔒

Make an exact string replacement in a file. A diff is shown for confirmation before writing. A `.bak` backup is created automatically.

```
path        — file to edit
old_string  — exact text to find (must be unique in the file)
new_string  — text to replace it with
```

**Best practice:** always call `view_file` first to copy the exact text you want to replace.

**Example prompt:** `"In agent/config.py replace the default history_window from 10 to 20"`

---

## Shell tools

### `run_shell` 🔒

Execute a shell command and return the combined output.

```
command    — shell command to run
cwd        — (optional) working directory
env_vars   — (optional) KEY=VALUE pairs separated by spaces
timeout    — (optional) timeout in seconds (default: 30)
```

**Example prompts:**
- `"Run the test suite"`
- `"Install the missing dependencies with uv sync"`
- `"Check what's listening on port 11435"`

---

## Code tools

### `run_python` 🔒

Execute Python code in an isolated subprocess. Captures stdout and stderr.

```
code  — Python source code to execute
```

**Example prompt:** `"Write and run a script to count the total lines of code in agent/"`

---

## Git tools

### `git_status`

Show the working tree status (`git status`).

No arguments.

---

### `git_diff`

Show file changes.

```
staged  — (optional, bool) show staged changes instead of unstaged
path    — (optional) limit diff to this path
```

---

### `git_log`

Show recent commit history.

```
n  — number of commits to show (default: 10)
```

---

### `git_commit` 🔒

Stage all changes and create a commit.

```
message  — commit message
```

**Example prompt:** `"Commit the changes with message 'fix: correct typo in README'"`

---

## Web tools

### `web_search`

Search the web using DuckDuckGo and return the top results.

```
query    — search query
max_results  — (optional) number of results (default: 5)
```

**Example prompt:** `"Search for best practices for Python async context managers"`

---

### `fetch_url`

Fetch a URL and extract its readable text content (strips HTML tags).

```
url      — URL to fetch
timeout  — (optional) timeout in seconds (default: 10)
```

**Example prompt:** `"Fetch the changelog from https://github.com/ggerganov/llama.cpp/releases"`

---

### `system_info`

Return OS details, Python version, shell, and availability of common tools (git, node, docker, etc.).

No arguments.

---

## Memory tools

### `save_memory`

Persist a named fact to disk. The fact is included in the system prompt of every future session.

```
key    — short identifier (e.g. "db-stack", "project-owner")
value  — the value to store
```

**Example prompt:** `"Remember that the production database is PostgreSQL 16"`

---

### `recall_memory`

Read a previously saved memory entry by key.

```
key  — the memory key to look up
```

---

### `list_memories`

Return a list of all memory keys.

No arguments.

---

### `delete_memory`

Delete a memory entry by key.

```
key  — the memory key to delete
```

---

## Tool safety

Tools that can modify your system require confirmation before executing:

| Tool | Risk |
|---|---|
| `write_file` | Creates or overwrites files |
| `edit_file` | Modifies files (backup is created) |
| `delete_file` | Permanent deletion |
| `run_shell` | Runs arbitrary shell commands |
| `run_python` | Executes arbitrary Python |
| `git_commit` | Creates a permanent git commit |

When a confirmation dialog appears, type `y` and press Enter to allow. Pressing Enter alone defaults to **No** (deny).

Skip all confirmations with `--unsafe` or `UNSAFE_MODE=true`.

---

## Adding custom tools

See [Plugin Development](plugin-development.md) to add your own tools without modifying the core.
