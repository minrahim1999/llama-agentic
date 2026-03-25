# Repository Guidelines

## Project Structure & Module Organization
Core application code lives in `agent/`. Use `agent/cli.py` for the entrypoint, `agent/core.py` for the ReAct loop, and `agent/tools/` for built-in tool implementations such as file, shell, git, web, and memory actions. Keep optional extensions in `plugins/`, packaging assets in `Formula/`, and developer utilities in `scripts/`. Put automated tests in `tests/` with names like `test_core.py` or `test_tools.py`.

## Build, Test, and Development Commands
Use `uv` for local setup and execution.

- `uv sync --dev`: install runtime and test dependencies.
- `uv run pytest tests/ -v --tb=short`: run the full test suite, matching CI.
- `uv run pytest tests/test_core.py -v`: run a focused test file during iteration.
- `uv run python scripts/benchmark.py`: benchmark tool-calling behavior against a running `llama-server`.
- `uv build`: build the distributable package locally.
- `./scripts/start_server.sh /path/to/model.gguf`: start the local `llama-server` used by the CLI.

## Coding Style & Naming Conventions
Follow the existing Python style: 4-space indentation, module-level docstrings, small focused functions, and type hints where they improve clarity. Use `snake_case` for functions, variables, and modules; use `PascalCase` for classes like `Agent`. Keep new tool modules under `agent/tools/` and mirror them with targeted tests. CI runs `uv run ruff check agent/ tests/`; run that locally before opening a PR even though it is currently non-blocking.

## Testing Guidelines
Tests use `pytest` and `pytest-asyncio`. Add unit tests for every behavior change, especially around tool dispatch, history handling, config loading, and plugin integration. Name test files `test_*.py` and test functions `test_*`. Prefer narrow, deterministic tests with mocks over network or model-dependent execution.

## Commit & Pull Request Guidelines
Git history currently only shows an initial commit, so there is no strong project-specific convention yet. Use short, imperative commit subjects such as `core: tighten tool-call parsing` or `tests: cover MCP startup failure`. PRs should describe the behavioral change, list validation commands you ran, and link related issues. Include terminal output or screenshots only when changing CLI UX or docs that depend on visual confirmation.

## Security & Configuration Tips
Do not commit real model paths, secrets, or machine-specific `.env` values. Changes affecting shell execution, file editing, or `.llamaignore` behavior should call out safety implications in the PR description.
