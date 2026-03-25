#!/usr/bin/env bash
# Install llama-agentic globally so 'llama-agent' works from any directory.
# Usage: ./scripts/install_global.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Installing llama-agentic from: $REPO_DIR"
echo ""

# Prefer uv tool install, fall back to pipx, then plain pip
if command -v uv &>/dev/null; then
  echo "Using uv..."
  uv tool install --editable "$REPO_DIR"
elif command -v pipx &>/dev/null; then
  echo "Using pipx..."
  pipx install --editable "$REPO_DIR"
else
  echo "Using pip (user install)..."
  pip install --user --editable "$REPO_DIR"
  echo ""
  echo "NOTE: Make sure ~/.local/bin is in your PATH."
  echo "  Add to ~/.zshrc or ~/.bashrc:"
  echo '  export PATH="$HOME/.local/bin:$PATH"'
fi

echo ""
echo "Done! Try it:"
echo "  llama-agent --help"
echo "  llama-agent           # first run: setup wizard appears"
echo "  llama-agent /init     # in any project: generate LLAMA.md"
