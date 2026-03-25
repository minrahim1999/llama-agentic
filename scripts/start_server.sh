#!/usr/bin/env bash
# Start llama-server with settings from .env
# Usage: ./scripts/start_server.sh [model_path]
set -euo pipefail

# Load .env if present
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

MODEL_PATH="${1:-${LLAMA_MODEL_PATH:-}}"
PORT="${LLAMA_PORT:-11435}"
CTX="${LLAMA_CTX_SIZE:-8192}"
GPU_LAYERS="${LLAMA_N_GPU_LAYERS:--1}"

if [ -z "$MODEL_PATH" ]; then
  echo "Error: no model path specified."
  echo "Usage: ./scripts/start_server.sh /path/to/model.gguf"
  echo "Or set LLAMA_MODEL_PATH in .env"
  exit 1
fi

if [ ! -f "$MODEL_PATH" ]; then
  echo "Error: model file not found: $MODEL_PATH"
  exit 1
fi

echo "Starting llama-server..."
echo "  Model : $MODEL_PATH"
echo "  Port  : $PORT"
echo "  Ctx   : $CTX"
echo "  GPU   : $GPU_LAYERS layers"
echo ""

llama-server \
  --model "$MODEL_PATH" \
  --port "$PORT" \
  --ctx-size "$CTX" \
  --n-gpu-layers "$GPU_LAYERS" \
  --parallel 1 \
  --jinja \
  --log-disable
