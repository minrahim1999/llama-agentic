#!/usr/bin/env bash
# Hot-switch to a different GGUF model by restarting llama-server.
# Usage: ./scripts/switch_model.sh /path/to/new_model.gguf
set -euo pipefail

if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

NEW_MODEL="${1:-}"
PORT="${LLAMA_PORT:-8080}"
CTX="${LLAMA_CTX_SIZE:-8192}"
GPU_LAYERS="${LLAMA_N_GPU_LAYERS:--1}"

if [ -z "$NEW_MODEL" ]; then
  echo "Usage: ./scripts/switch_model.sh /path/to/model.gguf"
  echo ""
  echo "Available cached models:"
  ls "${HOME}/Library/Caches/llama.cpp/"*.gguf 2>/dev/null | xargs -I{} basename {} || echo "  (none found in ~/Library/Caches/llama.cpp/)"
  exit 1
fi

if [ ! -f "$NEW_MODEL" ]; then
  echo "Error: model file not found: $NEW_MODEL"
  exit 1
fi

# Kill existing server
echo "Stopping existing llama-server on port $PORT..."
pkill -f "llama-server.*--port $PORT" 2>/dev/null && sleep 2 || echo "(no server running)"

# Update .env
if [ -f .env ]; then
  # Update LLAMA_MODEL_PATH
  sed -i.bak "s|^LLAMA_MODEL_PATH=.*|LLAMA_MODEL_PATH=$NEW_MODEL|" .env
  # Update LLAMA_MODEL to basename
  MODEL_NAME=$(basename "$NEW_MODEL")
  sed -i.bak "s|^LLAMA_MODEL=.*|LLAMA_MODEL=$MODEL_NAME|" .env
  rm -f .env.bak
  echo ".env updated."
fi

# Start with new model
echo "Starting llama-server with: $(basename "$NEW_MODEL")"
llama-server \
  --model "$NEW_MODEL" \
  --port "$PORT" \
  --ctx-size "$CTX" \
  --n-gpu-layers "$GPU_LAYERS" \
  --parallel 1 \
  --jinja \
  --log-disable &

sleep 4
curl -s "http://localhost:${PORT}/v1/models" | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print('Ready:', d['data'][0]['id'])" 2>/dev/null \
  || echo "Server may still be loading..."
