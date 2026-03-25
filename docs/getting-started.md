# Getting Started

This guide walks you through installing llama-agentic, downloading a model, and running your first session.

---

## Requirements

| Requirement | Version | Install |
|---|---|---|
| macOS or Linux | macOS 12+ / Ubuntu 22+ | — |
| Python | 3.11+ | [python.org](https://python.org) |
| llama.cpp | latest | `brew install llama.cpp` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

> **Apple Silicon note:** llama.cpp uses Metal GPU offload by default on M1/M2/M3 chips — no extra configuration needed.

---

## Installation

### Option A — editable install from source (recommended for development)

```bash
git clone <repo-url>
cd llama-agentic
uv tool install --editable .
```

The `llama-agent` command is now available in your PATH from any directory.

### Option B — install from PyPI

```bash
pip install llama-agentic
# or with uv
uv tool install llama-agentic
```

### Verify the install

```bash
llama-agent --help
```

---

## First-run setup

On the first run, a setup wizard collects your preferences:

```bash
llama-agent
```

The wizard asks for:
- Path to your GGUF model (or you can download one first — see below)
- Whether to auto-start llama-server when the agent launches

Settings are saved to `~/.config/llama-agentic/config.env`.

To re-run the wizard at any time:

```bash
llama-agent --setup
```

---

## Download a model

llama-agentic includes a model downloader that pulls GGUF files from Hugging Face Hub:

```bash
# List known model aliases
llama-agent download

# Download by alias
llama-agent download qwen2.5-coder-7b   # recommended
llama-agent download qwen2.5-7b
llama-agent download llama3.2-3b        # lightweight

# Download a raw Hugging Face repo
llama-agent download bartowski/Qwen2.5-Coder-7B-Instruct-GGUF \
  --filename Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf

# Download to a custom directory
llama-agent download qwen2.5-coder-7b --dest ~/models/
```

Models are saved to `~/.local/share/llama-agentic/models/` by default.

### List downloaded models

```bash
llama-agent models
```

---

## Start the server

llama-agentic uses `llama-server` (part of llama.cpp) as its LLM backend.

### Auto-start (recommended)

Set `AUTO_START_SERVER=true` in your config (the setup wizard enables this). The agent will automatically start and stop the server.

### Manual start

```bash
./scripts/start_server.sh /path/to/model.gguf

# or directly
llama-server \
  --model ~/.local/share/llama-agentic/models/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --port 11435 \
  --ctx-size 8192 \
  --n-gpu-layers -1 \
  --jinja
```

### Switch model at runtime

```bash
./scripts/switch_model.sh /path/to/new-model.gguf
```

---

## Check your environment

```bash
llama-agent doctor
```

Output example:

```
  Check                   Status   Detail
  Python ≥ 3.11           ✓ OK     3.12.1
  llama-server binary     ✓ OK     /opt/homebrew/bin/llama-server
  llama-server running    ✓ OK     Qwen2.5-Coder-7B
  huggingface-hub         ✓ OK     0.20.0
  GGUF model(s) in cache  ✓ OK     2 model(s)
  Global config           ✓ OK     ~/.config/llama-agentic/config.env
```

Fix any warnings shown before proceeding.

---

## Generate project context (LLAMA.md)

Navigate to your project and generate a `LLAMA.md` file — a compact knowledge base the agent loads on every session:

```bash
cd your-project/
llama-agent --init
```

The LLM scans your project structure and writes a summary of:
- What the project does
- Key files and their purpose
- Tech stack and conventions
- Common commands

Refresh it when the project changes:

```bash
llama-agent --init --force   # from CLI
# or inside the REPL:
/refresh
```

---

## Your first session

```bash
cd your-project/
llama-agent
```

Try these prompts to get started:

```
List the files in this project
```

```
Read the main entry point and explain what it does
```

```
Find all TODO comments in the codebase
```

```
Write a summary of this project to summary.md
```

---

## Shell completions

```bash
# bash — add to ~/.bashrc
eval "$(llama-agent completions bash)"

# zsh — add to ~/.zshrc
eval "$(llama-agent completions zsh)"

# fish
llama-agent completions fish | source
```
