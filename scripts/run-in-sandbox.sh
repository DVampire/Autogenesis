#!/usr/bin/env bash
set -euo pipefail

# Run an Autogenesis agent entirely inside a container (Model X).
#
# The host only launches; everything — the framework, every agent, and all tool
# execution (bash / file edits / git / experiment code) — runs in the container.
# The host project is bind-mounted in, so source is live and outputs land back on
# the host. Service peers (browser / deploy) are spawned as sibling containers via
# the mounted Docker socket and reached over the shared host network.
#
# Usage:
#   scripts/run-in-sandbox.sh [--image IMG] [--gpus] -- <command...>
#
# Examples:
#   scripts/run-in-sandbox.sh -- python examples/run_meta_agent.py \
#       --task-file examples/tasks/iris_lightgbm_experiment.html
#   scripts/run-in-sandbox.sh --image someorg/task:v1 -- python examples/run_programbench.py ...
#   scripts/run-in-sandbox.sh --gpus -- python examples/run_meta_agent.py --task "..."

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

IMAGE="autogenesis/base:latest"
GPUS="auto"        # auto -> --gpus all when the host has NVIDIA GPUs; --no-gpus to force off
DOCKER_SOCK="/var/run/docker.sock"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) IMAGE="$2"; shift 2 ;;
    --gpus)  GPUS="on"; shift ;;
    --no-gpus) GPUS="off"; shift ;;
    --)      shift; break ;;
    -h|--help) sed -n '3,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (did you forget -- before the command?)" >&2; exit 1 ;;
  esac
done

if [[ $# -eq 0 ]]; then
  echo "No command given. Put the command after --, e.g.:" >&2
  echo "  scripts/run-in-sandbox.sh -- python examples/run_meta_agent.py --task '...'" >&2
  exit 1
fi

# --- Pre-flight: Docker must be reachable (Model X refuses to fall back to host) ---
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker CLI not found. Model X runs the agent in a container; install Docker." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon not reachable by this user." >&2
  echo "  Add yourself to the docker group (then re-login):  sudo usermod -aG docker \$USER" >&2
  exit 1
fi
if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "ERROR: image '${IMAGE}' not found. Build it:" >&2
  echo "  docker build -f docker/base/Dockerfile -t autogenesis/base:latest ." >&2
  exit 1
fi

# Secrets: NOT passed via --env-file. `docker --env-file` does not strip quotes,
# so a line like ANTHROPIC_API_BASE='https://...' would arrive with literal quotes
# and break the URL. Instead the whole repo (including .env) is bind-mounted below,
# and the framework's own load_dotenv() reads .env inside the container — it strips
# quotes correctly, matching how a host run behaves.

# GPU: pass --gpus all so GPU training tasks run in the container. "auto" enables it
# when the host actually has NVIDIA GPUs (nvidia-smi present); --no-gpus forces off.
GPU_ARG=()
case "${GPUS}" in
  on)  GPU_ARG=(--gpus all) ;;
  off) GPU_ARG=() ;;
  auto) command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1 && GPU_ARG=(--gpus all) ;;
esac

# Interactive TTY only when we actually have one (so scripted/CI runs still work).
TTY_ARG=()
[[ -t 0 && -t 1 ]] && TTY_ARG=(-it)

echo "Autogenesis — run in sandbox (Model X)"
echo "  image   : ${IMAGE}"
echo "  repo    : ${REPO_ROOT} -> /Autogenesis"
echo "  gpus    : $([[ ${#GPU_ARG[@]} -gt 0 ]] && echo 'all' || echo 'none')"
echo "  command : $*"

exec docker run --rm "${TTY_ARG[@]}" \
  --network host \
  `# docker stop allows 10s by default, then SIGKILLs. That is not enough for a` \
  `# run that tears peer containers down on shutdown (the Gateway destroys the` \
  `# per-session IDE containers), and killing it mid-shutdown orphans them.` \
  --stop-timeout 60 \
  -v "${DOCKER_SOCK}:${DOCKER_SOCK}" \
  -v "${REPO_ROOT}:/Autogenesis" \
  -w /Autogenesis \
  `# Peer containers are created against the HOST Docker daemon, so their bind` \
  `# mounts resolve in the host's mount namespace. Pass the host path we mounted` \
  `# at /Autogenesis so those sources can be translated back (see` \
  `# autogenesis/sandbox/default/base.py:to_host_path).` \
  -e AUTOGENESIS_HOST_ROOT="${REPO_ROOT}" \
  "${GPU_ARG[@]}" \
  "${IMAGE}" \
  "$@"
