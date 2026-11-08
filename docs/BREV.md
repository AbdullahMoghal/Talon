# Running Talon's models on Brev

Every agent runs on Nemotron served by vLLM on a Brev GPU instance. The engine talks to it like any
OpenAI-compatible API, so no engine code changes between build.nvidia.com and Brev: only `.env` changes.

```text
laptop (engine, SpacetimeDB runner) --brev port-forward--> Brev GPU: vLLM :8000 Nemotron Nano 9B v2
                                                                     vLLM :8001 safety guard (optional)
```

## 1. Create the instance

1. On brev.nvidia.com (or `brev create talon-gpu --type a100-80gb.1x`), create a **GPU instance**: a plain
   VM, not a NIM launchable. Choose a stoppable one.
2. GPU:
   - **L40S 48 GB or A100 40 GB:** enough for Nemotron Nano 9B v2. The safety agent uses its rules
     plus the same model.
   - **A100 80 GB or H100 80 GB:** also fits the separate safety guard model.
3. Disk: at least 100 GB (weights plus the vLLM install).
4. Stop the instance when you're not using it. It bills by the hour and the team has $60 in credits.

## 2. Start the model server

On your laptop, install the Brev CLI and log in (`brev login`), then open a shell on the instance:

```bash
brev shell <instance-name>
git clone https://github.com/AbdullahMoghal/Talon.git && cd Talon
git checkout feat/agent-engine   # until PR #9 is merged
# The server's API key: generated once, kept only on the instance (cat ~/.talon_key to copy it into .env)
[ -f ~/.talon_key ] || (openssl rand -hex 24 > ~/.talon_key && chmod 600 ~/.talon_key)
export NEMOTRON_API_KEY=$(cat ~/.talon_key)
bash agents/brev/serve.sh
# or, on an 80 GB GPU, with the safety guard model too:
# export HF_TOKEN=<your Hugging Face token>   # the guard model may be gated; accept its license on HF first
# ENABLE_GUARD=1 bash agents/brev/serve.sh
```

The first start downloads about 18 GB of weights. The script waits until the server answers, and
prints the last log lines if vLLM crashes. Logs are in `~/talon-logs/`.

The server only accepts requests carrying `NEMOTRON_API_KEY`, so it isn't open to anyone who finds the
port.

## 3. Point the engine at it

On your laptop, in a separate terminal, keep a tunnel open:

```bash
brev port-forward <instance-name> --port 8000:8000
# with the guard model, a second one: --port 8001:8001
```

In the repo-root `.env` (gitignored, never commit it):

```bash
NEMOTRON_API_KEY=<the key from step 2>
NEMOTRON_BASE_URL=http://localhost:8000/v1
NEMOTRON_MODEL=nvidia/nvidia-nemotron-nano-9b-v2
# only with ENABLE_GUARD=1:
# SAFETY_MODEL=nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3
# SAFETY_BASE_URL=http://localhost:8001/v1
```

Then check it and run the demo:

```bash
cd agents
.venv/Scripts/python -m talon_agents.check   # models served, plain reply, JSON, tool call, /think
.venv/Scripts/python -m talon_agents.cli --demo
```

`check` must pass before you trust a demo run. A failed tool-call check almost always means vLLM
started without its tool-call parser.

## What's been verified

Tested on 2026-11-07 on a Crusoe `a100-80gb.1x` (A100 80 GB, stoppable, $1.98/hr), running the engine on
the instance itself:

- `serve.sh` with vLLM 0.11.0 and transformers 4.57: Nemotron Nano 9B v2 serves, and `check` passes
  (plain reply, JSON, tool calls, `/think` reasoning). First request after start takes ~35 s (warm-up).
- The full `cli --demo` takeover and `eval_gold` both run against it.
- vLLM uses ~70 GB of the 80 GB at `--gpu-memory-utilization 0.85`; lower it if you add the guard model.

Pins, and why: newer vLLM (0.33) can't load Nemotron Nano v2's tool-call parser plugin, and vLLM 0.11
breaks on transformers 5. The image had no system `pip`, so `serve.sh` installs with `uv`.

Not verified yet: `brev port-forward` from a laptop, the safety guard model (`ENABLE_GUARD=1`) and its
Hugging Face ID.

## Notes

- The Brev CLI has no Windows build. On Windows, run it inside WSL Ubuntu
  (`wsl -d Ubuntu -- brev login`). Running a whole script on the instance works well:
  `brev exec talon-gpu @script.sh`.
- Pick a **stoppable** instance (`brev search gpu --stoppable`). Some cheaper listings can't be stopped and
  bill until deleted. `brev stop talon-gpu` when done; `brev start talon-gpu` brings it back with the
  setup intact.
- vLLM serves the model under `nvidia/nvidia-nemotron-nano-9b-v2`, the same ID as build.nvidia.com, so
  switching between the two only changes the URL and key.
- For the demo, the engine runner can run on the Brev instance itself (then
  `NEMOTRON_BASE_URL=http://localhost:8000/v1` there and no tunnel is needed). It only needs outbound
  access to SpacetimeDB Maincloud.
