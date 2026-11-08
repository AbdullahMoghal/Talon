#!/usr/bin/env bash
# Serve Talon's Nemotron models with vLLM on a Brev GPU instance.
#
#   export NEMOTRON_API_KEY=<any long random string; the engine sends the same one>
#   bash agents/brev/serve.sh                # main model on :8000
#   ENABLE_GUARD=1 bash agents/brev/serve.sh # also the safety guard model on :8001 (needs ~80 GB GPU)
#
# Logs go to ~/talon-logs. Stop with: pkill -f "vllm serve"
set -euo pipefail

: "${NEMOTRON_API_KEY:?Set NEMOTRON_API_KEY first. It locks the server so only the engine can use it.}"
MAIN_MODEL="${MAIN_MODEL:-nvidia/NVIDIA-Nemotron-Nano-9B-v2}"
# Served under the same ID build.nvidia.com uses, so .env doesn't change between the two.
MAIN_NAME="${MAIN_NAME:-nvidia/nvidia-nemotron-nano-9b-v2}"
GUARD_MODEL="${GUARD_MODEL:-nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3}"
ENABLE_GUARD="${ENABLE_GUARD:-0}"
MAX_LEN="${MAX_LEN:-8192}"
# Nemotron Nano v2's tool-call parser plugin imports vLLM internals that moved in later releases,
# so pin to the version line its model card targets.
VLLM_VERSION="${VLLM_VERSION:-0.11.0}"

LOGS="$HOME/talon-logs"
PARSERS="$HOME/talon-parsers"
mkdir -p "$LOGS" "$PARSERS"

# vLLM gets its own venv so it never fights the system Python (which may not even have pip).
VENV="$HOME/.venvs/vllm"
if [ "$("$VENV/bin/python" -c "import vllm, transformers; print(vllm.__version__, transformers.__version__[0])" 2>/dev/null)" != "$VLLM_VERSION 4" ]; then
  echo "Installing vLLM $VLLM_VERSION into $VENV (a few minutes)..."
  # uv brings its own Python, so this works even without pip or python3-venv on the image.
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
  export PATH="$HOME/.local/bin:$PATH"
  rm -rf "$VENV"
  uv venv -q --python 3.12 "$VENV"
  VIRTUAL_ENV="$VENV" uv pip install -q "vllm==$VLLM_VERSION" "transformers>=4.56,<5" huggingface_hub
fi
export PATH="$VENV/bin:$PATH"

# Nemotron Nano v2 ships its tool-call parser as a .py file in the model repo.
python -c "import sys; from huggingface_hub import snapshot_download as d; d(sys.argv[1], allow_patterns=['*.py'], local_dir=sys.argv[2])" \
  "$MAIN_MODEL" "$PARSERS" >/dev/null
TOOL_PARSER="$(ls "$PARSERS"/*toolcall*parser*.py 2>/dev/null | grep -v streaming | head -1 || true)"
TOOL_PARSER="${TOOL_PARSER:-$(ls "$PARSERS"/*toolcall*parser*.py 2>/dev/null | head -1 || true)}"
if [ -z "$TOOL_PARSER" ]; then
  echo "No tool-call parser found in $MAIN_MODEL. Check the model card for the vLLM tool-calling flags." >&2
  exit 1
fi
echo "Tool-call parser: $TOOL_PARSER"

MAIN_MEM=0.85
[ "$ENABLE_GUARD" = "1" ] && MAIN_MEM=0.5

nohup vllm serve "$MAIN_MODEL" \
  --served-model-name "$MAIN_NAME" \
  --host 0.0.0.0 --port 8000 \
  --api-key "$NEMOTRON_API_KEY" \
  --trust-remote-code \
  --max-model-len "$MAX_LEN" \
  --max-num-seqs 64 \
  --mamba_ssm_cache_dtype float32 \
  --gpu-memory-utilization "$MAIN_MEM" \
  --enable-auto-tool-choice \
  --tool-parser-plugin "$TOOL_PARSER" \
  --tool-call-parser nemotron_json \
  >"$LOGS/main.log" 2>&1 &
echo "Main model starting on :8000 (log: $LOGS/main.log)"

if [ "$ENABLE_GUARD" = "1" ]; then
  # Let the main model claim its memory first.
  until curl -sf -H "Authorization: Bearer $NEMOTRON_API_KEY" localhost:8000/v1/models >/dev/null; do sleep 5; done
  nohup vllm serve "$GUARD_MODEL" \
    --host 0.0.0.0 --port 8001 \
    --api-key "$NEMOTRON_API_KEY" \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.35 \
    >"$LOGS/guard.log" 2>&1 &
  echo "Guard model starting on :8001 (log: $LOGS/guard.log)"
fi

echo "Waiting for the main model (first start downloads weights)..."
until curl -sf -H "Authorization: Bearer $NEMOTRON_API_KEY" localhost:8000/v1/models >/dev/null; do
  if ! pgrep -f "vllm serve $MAIN_MODEL" >/dev/null; then
    echo "vLLM exited. Last log lines:" >&2; tail -30 "$LOGS/main.log" >&2; exit 1
  fi
  sleep 10
done
echo "Ready: http://<this machine>:8000/v1 serving $MAIN_NAME"
