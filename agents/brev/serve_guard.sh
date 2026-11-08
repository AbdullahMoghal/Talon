#!/usr/bin/env bash
# Serve only the safety guard (Llama 3.1 Nemotron Safety Guard 8B v3) with vLLM, on its own GPU instance.
# Use this when the main model's GPU is busy or too small for both; serve.sh with ENABLE_GUARD=1 runs both
# on one 80 GB GPU instead.
#
#   export NEMOTRON_API_KEY=<the same key the engine sends>
#   bash agents/brev/serve_guard.sh          # guard on :8001
#
# Engine settings (.env): SAFETY_MODEL=nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3,
# SAFETY_BASE_URL=http://<this machine or tunnel>:8001/v1. Stop with: pkill -f "vllm serve"
set -euo pipefail
: "${NEMOTRON_API_KEY:?Set NEMOTRON_API_KEY first. It locks the server so only the engine can use it.}"
GUARD_MODEL="${GUARD_MODEL:-nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3}"
PORT="${PORT:-8001}"
VLLM_VERSION="${VLLM_VERSION:-0.11.0}"  # same pin as serve.sh, so one venv works for both
LOGS="$HOME/talon-logs"
mkdir -p "$LOGS"

VENV="$HOME/.venvs/vllm"
if [ "$("$VENV/bin/python" -c "import vllm, transformers; print(vllm.__version__, transformers.__version__[0])" 2>/dev/null)" != "$VLLM_VERSION 4" ]; then
  echo "Installing vLLM $VLLM_VERSION into $VENV (a few minutes)..."
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
  export PATH="$HOME/.local/bin:$PATH"
  rm -rf "$VENV"
  uv venv -q --python 3.12 "$VENV"
  VIRTUAL_ENV="$VENV" uv pip install -q "vllm==$VLLM_VERSION" "transformers>=4.56,<5" huggingface_hub
fi
export PATH="$VENV/bin:$PATH"

# The guard is an 8B model with a short prompt (template + one message + one reply), so 4k context is plenty.
nohup vllm serve "$GUARD_MODEL" \
  --host 0.0.0.0 --port "$PORT" \
  --api-key "$NEMOTRON_API_KEY" \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85 \
  >"$LOGS/guard.log" 2>&1 &
echo "Guard starting on :$PORT (log: $LOGS/guard.log). First start downloads about 16 GB of weights."

until curl -sf -H "Authorization: Bearer $NEMOTRON_API_KEY" "localhost:$PORT/v1/models" >/dev/null; do
  if ! pgrep -f "vllm serve $GUARD_MODEL" >/dev/null; then
    echo "vLLM exited. Last log lines:" >&2; tail -30 "$LOGS/guard.log" >&2; exit 1
  fi
  sleep 10
done
echo "Ready: http://<this machine>:$PORT/v1 serving $GUARD_MODEL"
