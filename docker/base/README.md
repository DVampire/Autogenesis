# base image — the project sandbox (Model X)

`autogenesis/base:latest` is the container the **whole agent runs inside**: the
framework, every agent, and all tool execution (bash / file edits / git / experiment
code). The host only launches it via [`scripts/run-in-sandbox.sh`](../../scripts/run-in-sandbox.sh);
the repo is bind-mounted in, so source is live and outputs land back on the host.

It is a **plain conda dev environment** (parity with the host's `agentos` env), NOT
built on opensandbox's execd/kernel runtime — that runtime exists for containers the
opensandbox daemon *manages* (the peer containers), whereas this container is launched
directly by `docker run` and is not daemon-managed. It therefore only needs a general
dev toolchain, not execd.

Contents:

- **conda base** (`continuumio/miniconda3`) → Python + pip
- **Node/JS** and **R** (`conda-forge` `nodejs`, `r-base`) — languages the agent may
  run locally inside the sandbox
- **git**, build-essential
- **CPU data-science stack**: numpy, pandas, scipy, scikit-learn, matplotlib, seaborn,
  lightgbm, xgboost
- the **autogenesis framework** + `sandbox` extra (`opensandbox` / `opensandbox-server`
  / `docker`), so the in-container agent can spawn peer containers (browser / deploy)
  through the mounted Docker socket

GPU / deep-learning stacks (torch, JAX, …) are intentionally left out — they are large
and GPU-specific and belong in a purpose-built image.

## Build

Build **from the repo root** (the context must be the repo, because the image installs
the framework):

```bash
docker build -f docker/base/Dockerfile -t autogenesis/base:latest .
```

## Smoke-test

```bash
docker run --rm autogenesis/base:latest python -c "import autogenesis, lightgbm; print('ok')"
docker run --rm autogenesis/base:latest bash -lc "node -v && Rscript -e 'cat(R.version.string)'"
```
