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

LOGS="$HOME/talon-logs"
PARSERS="$HOME/talon-parsers"
mkdir -p "$LOGS" "$PARSERS"

# vLLM gets its own venv so it never fights the system Python (which may not even have pip).
VENV="$HOME/.venvs/vllm"
if [ ! -x "$VENV/bin/vllm" ]; then
  echo "Installing vLLM into $VENV (a few minutes)..."
  python3 -m venv "$VENV" 2>/dev/null || {
    sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv python3-pip >/dev/null
    rm -rf "$VENV"; python3 -m venv "$VENV"
  }
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q "vllm>=0.10.2" huggingface_hub
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
