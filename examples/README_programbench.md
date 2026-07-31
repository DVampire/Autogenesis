# Running the ProgramBench benchmark

This guide covers running Autogenesis's MetaAgent on **ProgramBench** tasks and
scoring the results. ProgramBench gives the agent *only a compiled binary plus its
documentation* and asks it to reconstruct, from scratch, a source tree that
reproduces the program's behavior — building a `./compile.sh` that rebuilds an
equivalent `./executable` on a clean checkout.

- **Runner:** [`examples/run_programbench.py`](run_programbench.py) — runs tasks only, **no scoring**.
- **Scorer:** the official `programbench eval` CLI (from the `programbench` pip package), pointed at the runner's output.
- **Config:** [`configs/programbench_agent.py`](../configs/programbench_agent.py).

> Only on the `feature/programbench-runner` branch.

---

## 1. Prerequisites

### 1.1 Python environment
```bash
conda create -n autogenesis python=3.12 && conda activate autogenesis
# benchmark + sandbox extras are REQUIRED for ProgramBench (programbench, opensandbox, docker SDK):
pip install -e ".[benchmark,sandbox]"     # or ".[all]"
```

### 1.2 Docker (required)
Each task runs in a real Docker container, so you need a working Docker Engine + daemon,
and your user must be able to reach it without sudo:
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"     # then re-login, or use `newgrp docker`
docker run --rm hello-world         # must succeed
```
`opensandbox-server` is started automatically by the runner (on `localhost:28080`) and
writes `~/.sandbox.toml` on first use — you don't start it yourself.

### 1.3 API keys (`.env` at repo root)
Vault is **optional** — if it isn't configured/reachable, the framework reads keys straight
from `.env`. For the default model (`google/gemini-*`) you need:
```bash
GOOGLE_API_BASE='...'
GOOGLE_API_KEY='...'
```
Other providers are also supported by putting their keys in `.env`: `OPENAI_API_KEY/BASE`,
`OPENROUTER_API_KEY/BASE`, `ANTHROPIC_API_KEY/BASE` (see `autogenesis/model/context.py`).

---

## 2. Running tasks

```bash
conda activate autogenesis

# Run specific instances by id:
python examples/run_programbench.py \
  --task-ids abishekvashok__cmatrix.5c082c6,wfxr__csview.8ac4de0 \
  --cfg-options model_name=google/gemini-3.1-pro-preview \
  --no-evolve

# Or run a slice of the loaded instance list:
python examples/run_programbench.py --start 0 --end 5 --no-evolve
```

You must pass either `--task-ids` **or** `--start/--end` (it refuses to run all 201 by default).

### Key flags
| Flag | Meaning |
| --- | --- |
| `--task-ids a,b` | Comma-separated **instance_id** list (takes priority over `--start/--end`). |
| `--start N --end M` | Run instances `[N, M)` by load order. |
| `--evolve` / `--no-evolve` | Include the self-evolution roster (15 optimizer/generator/evaluator agents + evolution tools/skills) or not. Default: `--evolve` **on**. Use `--no-evolve` for a lean, cheaper "just do the task" run. |
| `--cfg-options k=v ...` | Override config, e.g. `model_name=google/gemini-3.1-pro-preview`. The override propagates to every agent. |
| `--config <path>` | Config file (default `configs/programbench_agent.py`). |
| `--out <dir>` | Results JSON output dir. |

### Finding instance IDs
Instance IDs look like `<owner>__<repo>.<shortsha>` (e.g. `abishekvashok__cmatrix.5c082c6`),
**not** `owner/repo`. To list them:
```bash
python -c "from autogenesis.data.programbench import ProgramBenchDataset as D; \
[print(i['instance_id'], '|', i['repository'], '|', i['language']) for i in D().data]"
```

### Outputs
Each run is a session under `output/programbench_agent/<session-id>/`:
- `workspace/submission.tar.gz` — the reconstructed source tree pulled out of the container.
- Results JSON: `output/programbench_agent/<bootstrap-id>/log/results/programbench/run_<id>.json`
  (`status: done` just means the agent's loop finished — **not** that it passed; see scoring).

---

## 3. Scoring

The runner does **not** score. Scoring rebuilds each `submission.tar.gz` via its `compile.sh`
and runs the hidden test suite in Docker; score = fraction of (non-ignored) tests passed.
**No LLM is involved in scoring.**

### 3.1 Get the test blobs
The full test set (`programbench/ProgramBench-Tests` on HuggingFace) is ~12 GB. You do **not**
need all of it — fetch only the instances you scored (a few files each, seconds):
```bash
programbench blob sync abishekvashok__cmatrix.5c082c6
programbench blob sync wfxr__csview.8ac4de0
# (omit the id to sync everything; slow without an HF token due to rate limits —
#  set HF_ENDPOINT=https://hf-mirror.com for a faster mirror, or export HF_TOKEN=...)
```

### 3.2 Lay out a run dir and evaluate
`programbench eval` expects `<run>/<instance_id>/submission.tar.gz`:
```bash
RUN=$(mktemp -d)
for iid in abishekvashok__cmatrix.5c082c6 wfxr__csview.8ac4de0; do
  # find the session that produced this instance's submission, then:
  mkdir -p "$RUN/$iid"
  cp output/programbench_agent/<session-id>/workspace/submission.tar.gz "$RUN/$iid/"
done

programbench eval "$RUN" --branch-workers 1 --force -o "$RUN/out"
```
It prints an **Evaluation Summary** (per-instance score + comment such as `ERROR: compile_failed`),
and writes `<out>/.../<iid>/<iid>.eval.json`. A score of `1.0` (all tests pass) = solved.

> **Use official defaults for a faithful score.** Don't override `--docker-cpus` (default `10`,
> also exported as `PYTEST_XDIST_AUTO_NUM_WORKERS`); `--image-tag` defaults to `task_cleanroom_v6`,
> the artifact-free cleanroom image (matches what the agent ran in). Lowering CPUs can affect
> timing-sensitive tests.

---

## 4. Gotchas / troubleshooting

- **First-run sandbox `ReadTimeout` ("Network connectivity error").** The task image
  (`programbench/<...>:task_cleanroom_v6`, ~4 GB) is pulled on first use, and the pull can
  exceed the 60 s sandbox-create timeout. **Pre-pull it**, then re-run:
  ```bash
  docker pull programbench/<image_name>:task_cleanroom_v6
  ```
  (Once cached, `acquire` takes a few seconds.)

- **Network isolation is ON by default** (`--network none`, the anti-cheat that stops the
  agent from downloading the original source). Consequences:
  - The agent cannot fetch build dependencies inside the sandbox. Languages that pull deps at
    build time (e.g. Rust/`cargo` fetching crates) will fail to compile unless the image
    pre-caches them.
  - Disable only for debugging: `AUTOGENESIS_SANDBOX_ISOLATE_NETWORK=0` (this permits the
    agent to cheat, so scores from such runs are not comparable).
  - On hosts with IPv6 disabled at the kernel, set `disable_ipv6 = false` under `[egress]` in
    `~/.sandbox.toml`.

- **The agent must write to `/workspace`.** Inside the sandbox the working directory is
  `/workspace`; `extract_submission()` only tars `/workspace`. The agent's prompt now reports
  `/workspace` as its workspace whenever a container sandbox is bound (see
  `Sandbox.container_workspace` / `_resolve_workspace_root`). Anything written elsewhere (e.g. a
  host-style `/home/.../workspace` path) is lost from the submission.

- **`opensandbox-server` port.** Defaults to `localhost:28080` (avoids the common `8080`
  clash). Override with `AUTOGENESIS_OPENSANDBOX_DOMAIN=host:port`.

- **Only `bash_tool` is sandbox-aware.** The ProgramBench config deliberately excludes
  `read_file/write_file/edit_file/list_dir/git` tools — they'd operate on the host, not the
  container. All file/git work goes through `bash_tool`.

---

## 5. Quick end-to-end example

```bash
conda activate autogenesis
IMG=$(python -c "from autogenesis.data.programbench import ProgramBenchDataset as D; \
print(next(i['image_name'] for i in D().data if i['instance_id']=='abishekvashok__cmatrix.5c082c6'))")
docker pull "$IMG:task_cleanroom_v6"                     # avoid the cold-pull timeout

python examples/run_programbench.py \
  --task-ids abishekvashok__cmatrix.5c082c6 \
  --cfg-options model_name=google/gemini-3.1-pro-preview --no-evolve

# then score (see §3)
programbench blob sync abishekvashok__cmatrix.5c082c6
RUN=$(mktemp -d); mkdir -p "$RUN/abishekvashok__cmatrix.5c082c6"
cp output/programbench_agent/<session-id>/workspace/submission.tar.gz "$RUN/abishekvashok__cmatrix.5c082c6/"
programbench eval "$RUN" --branch-workers 1 --force -o "$RUN/out"
```
