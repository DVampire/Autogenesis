#!/usr/bin/env bash
set -euo pipefail

# One-shot Autogenesis environment installer.
#
# Sets up everything needed to run the MetaAgent:
#   1. a Python env (conda or uv) on Python 3.11+
#   2. the autogenesis package + dependencies from pyproject.toml
#   3. Node.js / npm  -- required by the frontend/ web UI
#   4. optional extras (browser / chem / sandbox / benchmark)
#   5. the container-sandbox images (built when the sandbox extra is requested)
#   6. an .env template, if one does not exist yet
#   7. a verification pass
#
# It does NOT install the optional per-provider SDKs for the migrated Langflow
# plugins (langchain-openai, jigsawstack, composio, …) — those are lazy and
# installed on demand per plugin. See scripts/install-plugin.sh.
#
# Re-running is safe: existing environments are reused, not recreated.
#
# Usage:
#   bash scripts/install.sh                      # conda env "agentos", core + dev
#   bash scripts/install.sh -n myenv -p 3.12
#   bash scripts/install.sh --extras browser     # + playwright & chromium
#   bash scripts/install.sh --extras sandbox     # + build the container-sandbox images (needs Docker)
#   bash scripts/install.sh --extras all
#   bash scripts/install.sh --uv                 # use uv instead of conda
#   bash scripts/install.sh --no-node            # skip Node.js
#
# Vault is NOT installed here -- it is optional. The framework falls back to
# reading secrets from .env when Vault is unreachable. For central secret
# management see scripts/install_vault.sh and scripts/INSTALL.md.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ENV_NAME="agentos"
PY_VERSION="3.12"
EXTRAS="dev"
USE_UV=0
WITH_NODE=1

usage() {
  sed -n '4,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--name)    ENV_NAME="$2"; shift 2 ;;
    -p|--python)  PY_VERSION="$2"; shift 2 ;;
    -e|--extras)  EXTRAS="$2"; shift 2 ;;
    --uv)         USE_UV=1; shift ;;
    --no-node)    WITH_NODE=0; shift ;;
    -h|--help)    usage ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 1 ;;
  esac
done

# "dev" is always included so pytest is available for the verification pass.
case ",${EXTRAS}," in
  *,dev,*) ;;
  ,,)      EXTRAS="dev" ;;
  *)       EXTRAS="${EXTRAS},dev" ;;
esac

WANT_BROWSER=0
case ",${EXTRAS}," in
  *,browser,*|*,all,*) WANT_BROWSER=1 ;;
esac

WANT_SANDBOX=0
case ",${EXTRAS}," in
  *,sandbox,*|*,all,*) WANT_SANDBOX=1 ;;
esac

STEPS=7
step() { echo; echo "=== [$1/${STEPS}] $2 ==="; }

echo "Autogenesis installer"
echo "  repo    : ${REPO_ROOT}"
echo "  env     : ${ENV_NAME} (python ${PY_VERSION})"
echo "  extras  : ${EXTRAS}"
echo "  backend : $([[ ${USE_UV} -eq 1 ]] && echo uv || echo conda)"

cd "${REPO_ROOT}"

# ---------------------------------------------------------------------------
step 1 "Creating the Python environment"
# ---------------------------------------------------------------------------
if [[ ${USE_UV} -eq 1 ]]; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
  fi
  uv venv --python "${PY_VERSION}" 2>/dev/null || true
  ENV_PREFIX="${REPO_ROOT}/.venv"
else
  if ! command -v conda >/dev/null 2>&1; then
    echo "conda not found on PATH." >&2
    echo "Install Miniconda (https://docs.conda.io/en/latest/miniconda.html)," >&2
    echo "or re-run with --uv to use uv instead." >&2
    exit 1
  fi
  if conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
    echo "conda env '${ENV_NAME}' already exists -- reusing it."
  else
    conda create -n "${ENV_NAME}" "python=${PY_VERSION}" -y
  fi
  ENV_PREFIX="$(conda env list | awk -v n="${ENV_NAME}" '$1==n {print $NF}')"
fi

PY="${ENV_PREFIX}/bin/python"
[[ -x "${PY}" ]] || { echo "Python not found at ${PY}" >&2; exit 1; }
echo "Python: $("${PY}" --version) at ${PY}"

# ---------------------------------------------------------------------------
step 2 "Installing autogenesis and its dependencies"
# ---------------------------------------------------------------------------
# Editable install: the repo stays the source of truth and `import autogenesis`
# works from anywhere. Dependencies come from pyproject.toml.
"${PY}" -m pip install --upgrade pip -q
"${PY}" -m pip install -e ".[${EXTRAS}]"

# ---------------------------------------------------------------------------
step 3 "Installing Node.js / npm"
# ---------------------------------------------------------------------------
# Needed by the trace web UI (autogenesis/trace/ui) and the Vite frontend.
# Without it those UIs are skipped -- agent runs still work.
if [[ ${WITH_NODE} -eq 0 ]]; then
  echo "Skipped (--no-node)."
elif [[ -x "${ENV_PREFIX}/bin/npm" ]]; then
  # npm's shebang is "#!/usr/bin/env node", so the env's bin must be on PATH.
  echo "npm already present: $(PATH="${ENV_PREFIX}/bin:${PATH}" npm --version)"
elif command -v npm >/dev/null 2>&1; then
  echo "Using system npm: $(npm --version)"
elif [[ ${USE_UV} -eq 0 ]]; then
  conda install -n "${ENV_NAME}" -c conda-forge nodejs -y
  echo "Installed: node $("${ENV_PREFIX}/bin/node" --version)"
else
  echo "npm not found. With --uv, install Node.js yourself (e.g. via nvm)."
fi

# ---------------------------------------------------------------------------
step 4 "Installing browser automation (optional)"
# ---------------------------------------------------------------------------
if [[ ${WANT_BROWSER} -eq 1 ]]; then
  # install-deps needs root; without it Chromium still runs on most systems.
  bash "${REPO_ROOT}/scripts/install_playwright.sh" "${PY}" || {
    echo "Playwright setup did not finish cleanly -- browser skills may not work."
  }
else
  echo "Skipped (add --extras browser to enable)."
fi

# ---------------------------------------------------------------------------
step 5 "Building container-sandbox images (optional)"
# ---------------------------------------------------------------------------
# The sandbox extra runs peers (browser / code-interpreter) in isolated
# containers, which need a reachable Docker daemon. When it is reachable we
# also BUILD the two Autogenesis peer images up front, so the first agent run
# doesn't stall building them lazily:
#
#   autogenesis/chrome-vnc:latest        headful Chrome + noVNC live view
#                                         (browser_environment / webapp_testing)
#   autogenesis/code-interpreter:latest  the sandboxed code-interpreter peer
#
# Their opensandbox/* base layers are pulled automatically as the Dockerfile
# FROM, and opensandbox's own helper images (execd / egress) are pulled by the
# sandbox server on first use — so nothing else needs provisioning here. The
# Model X launcher image (autogenesis/base) is built separately; see
# docker/base/README.md and scripts/run-in-sandbox.sh.
build_sandbox_image() {
  local tag="$1" dir="$2"
  if [[ ! -f "${dir}/Dockerfile" ]]; then
    echo "  skip ${tag} (no Dockerfile at ${dir})"
    return
  fi
  if docker image inspect "${tag}" >/dev/null 2>&1; then
    echo "  ok   ${tag} already present -- not rebuilding."
  else
    echo "  build ${tag} from ${dir} (this can take a few minutes)…"
    if docker build -t "${tag}" "${dir}"; then
      echo "  ok   built ${tag}"
    else
      echo "  WARN docker build failed for ${tag} -- that sandbox may not start." >&2
    fi
  fi
}

if [[ ${WANT_SANDBOX} -eq 1 ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker CLI not found -- install Docker Engine to use container sandboxes."
    echo "Without it, only the non-isolated 'host' sandbox works."
  elif ! docker info >/dev/null 2>&1; then
    echo "docker CLI present but the daemon is not reachable by this user."
    echo "Add yourself to the docker group (then re-login):"
    echo "    sudo usermod -aG docker \$USER"
    echo "Until then, only the non-isolated 'host' sandbox works; images not built."
  else
    echo "Docker daemon reachable: $(docker version --format '{{.Server.Version}}' 2>/dev/null)."
    build_sandbox_image "autogenesis/chrome-vnc:latest"       "${REPO_ROOT}/docker/chrome-vnc"
    build_sandbox_image "autogenesis/code-interpreter:latest" "${REPO_ROOT}/docker/code-interpreter"
  fi
else
  echo "Skipped (add --extras sandbox to build the container-sandbox images)."
fi

# ---------------------------------------------------------------------------
step 6 "Checking .env"
# ---------------------------------------------------------------------------
# Secrets are read from Vault when it is configured and reachable, and from
# .env otherwise (see autogenesis/utils/hvac_utils.py).
if [[ -f "${REPO_ROOT}/.env" ]]; then
  echo ".env already exists -- left untouched."
else
  cat > "${REPO_ROOT}/.env" <<'ENVEOF'
# Provider credentials. Fill in the ones you use; unset providers simply
# register no usable models.
#
# The base URL may include a trailing /v1 or omit it -- both work.

ANTHROPIC_API_BASE=''
ANTHROPIC_API_KEY=''

OPENROUTER_API_BASE=''
OPENROUTER_API_KEY=''

GOOGLE_API_BASE='https://generativelanguage.googleapis.com'
GOOGLE_API_KEY=''

OPENAI_API_BASE=''
OPENAI_API_KEY=''

# Optional: central secret management via Vault (scripts/install_vault.sh).
# When these are unset or Vault is unreachable, the values above are used.
# VAULT_ADDR='http://127.0.0.1:8200'
# VAULT_TOKEN=''
# UNSEAL_TOKEN=''
# SECRET_ENGINE_PATH='cubbyhole/env'
ENVEOF
  echo "Created a template .env -- fill in your API keys before running an agent."
fi

# ---------------------------------------------------------------------------
step 7 "Verifying"
# ---------------------------------------------------------------------------
FAILED=0
check() {
  if eval "$2" >/dev/null 2>&1; then
    echo "  ok    $1"
  else
    echo "  FAIL  $1"
    FAILED=1
  fi
}

check "import autogenesis"  "'${PY}' -c 'import autogenesis'"
check "autogenesis CLI"     "'${ENV_PREFIX}/bin/autogenesis' --help"
[[ ${WITH_NODE} -eq 1 ]] && check "npm" "PATH='${ENV_PREFIX}/bin:${PATH}' npm --version"
[[ ${WANT_BROWSER} -eq 1 ]] && check "playwright" "'${PY}' -c 'import playwright'"
[[ ${WANT_SANDBOX} -eq 1 ]] && check "opensandbox import" "'${PY}' -c 'import opensandbox, docker'"
if [[ ${WANT_SANDBOX} -eq 1 ]] && docker info >/dev/null 2>&1; then
  check "chrome-vnc image"       "docker image inspect autogenesis/chrome-vnc:latest"
  check "code-interpreter image" "docker image inspect autogenesis/code-interpreter:latest"
fi

echo
echo "  test suite:"
PATH="${ENV_PREFIX}/bin:${PATH}" "${PY}" -m pytest -q 2>&1 | tail -3 | sed 's/^/    /'

echo
if [[ ${FAILED} -eq 0 ]]; then
  echo "Done. Activate the environment with:"
  if [[ ${USE_UV} -eq 1 ]]; then
    echo "    source .venv/bin/activate"
  else
    echo "    conda activate ${ENV_NAME}"
  fi
  echo
  echo "Then run an agent:"
  echo "    python examples/run_meta_agent.py --task \"...\""
  echo
  echo "Plugins install their third-party SDKs on demand:"
  echo "    scripts/install-plugin.sh --names            # list all plugins"
  echo "    scripts/install-plugin.sh --list <plugin>   # show a plugin's deps"
  echo "    scripts/install-plugin.sh <plugin> [...]    # install a plugin's deps"
  echo "    scripts/install-plugin.sh --all             # install every plugin's deps"
else
  echo "Some checks failed -- see the FAIL lines above." >&2
  exit 1
fi
