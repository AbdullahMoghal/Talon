# Running Talon's models on Brev

Every agent runs on Nemotron served by vLLM on a Brev GPU instance. The engine talks to it like any
OpenAI-compatible API, so no engine code changes between build.nvidia.com and Brev: only `.env` changes.

```text
laptop (engine, SpacetimeDB runner) --brev port-forward--> Brev GPU: vLLM :8000 Nemotron Nano 9B v2
                                                                     vLLM :8001 safety guard (optional)
```

## 1. Create the instance

1. On brev.nvidia.com, create a **GPU instance** (a plain VM with Docker/Python, not a NIM launchable).
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
export NEMOTRON_API_KEY=$(openssl rand -hex 24); echo "$NEMOTRON_API_KEY"   # copy this
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

## Notes and things not yet verified

- None of this has been run on a real Brev instance yet. The `brev port-forward` flags, the vLLM flags
  for Nemotron Nano v2 (from its model card), and the guard model's Hugging Face ID all need checking
  on the first run. `serve.sh` fails loudly instead of guessing when it can't find the tool-call parser.
- vLLM serves the model under `nvidia/nvidia-nemotron-nano-9b-v2`, the same ID as build.nvidia.com, so
  switching between the two only changes the URL and key.
- If `brev port-forward` is unreliable, Brev can also expose port 8000 as a public URL from the
  instance page. The API key still protects it.
- For the demo, the engine runner can also run on the Brev instance itself (then
  `NEMOTRON_BASE_URL=http://localhost:8000/v1` there and no tunnel is needed). It only needs outbound
  access to SpacetimeDB Maincloud.
