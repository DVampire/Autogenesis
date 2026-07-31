#!/usr/bin/env bash
set -euo pipefail

# Ubuntu one-shot installer:
# - Installs build dependencies
# - Installs latest stable Go from go.dev
# - Clones HashiCorp Vault source
# - Builds Vault with `make bootstrap` and `make dev`
# - Installs the compiled vault binary to /usr/local/vault/bin
#
# Tested target: Ubuntu 22.04/24.04
# Supported arch: amd64, arm64

INSTALL_PREFIX="${1:-/usr/local}"
VAULT_DATA_DIR="${INSTALL_PREFIX}/vault/data"
VAULT_CONFIG_DIR="${INSTALL_PREFIX}/vault/config"
VAULT_BIN_DIR="${INSTALL_PREFIX}/vault/bin"
VAULT_LOG="${INSTALL_PREFIX}/vault/vault.log"

echo "Install prefix: ${INSTALL_PREFIX}"
mkdir -p "${INSTALL_PREFIX}"

echo "[1/8] Checking architecture..."
ARCH="$(dpkg --print-architecture)"
case "$ARCH" in
  amd64) GOARCH="amd64" ;;
  arm64) GOARCH="arm64" ;;
  *)
    echo "Unsupported architecture: $ARCH"
    echo "Supported: amd64, arm64"
    exit 1
    ;;
esac

echo "[2/8] Installing dependencies..."
sudo apt-get update
sudo apt-get install -y \
  curl \
  wget \
  git \
  make \
  unzip \
  jq \
  build-essential \
  ca-certificates

echo "[2b/8] Installing Node.js 20.20.2 (via nvm) and pnpm/yarn..."
# Vault's web UI (ember) build pins Node 20.x via package.json `devEngines`.
# A newer Node (e.g. 22.x from nodesource LTS) aborts `make static-dist` /
# `make dev-ui` with `EBADDEVENGINES`. Pin the exact version with nvm so the
# `nvm use` stays active for the build step (7/8) in this same shell.
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [[ ! -s "${NVM_DIR}/nvm.sh" ]]; then
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
fi
# nvm.sh references unset vars; relax `set -u` only while sourcing/using it.
set +u
# shellcheck source=/dev/null
. "${NVM_DIR}/nvm.sh"
nvm install 20.20.2 && nvm use 20.20.2
set -u
# Use corepack (bundled with Node) so the UI build gets the EXACT package
# manager pinned in ui/package.json `packageManager` (pnpm@10.22.0, tested
# against Node 20). Do NOT `npm install -g pnpm`: that pulls pnpm@latest (v11+),
# which requires Node 22.13+ and crashes under Node 20 with
# `node:sqlite` ERR_UNKNOWN_BUILTIN_MODULE during `pnpm i`.
corepack enable
corepack prepare pnpm@10.22.0 --activate
echo "Using Node $(node -v) / pnpm $(pnpm -v)"

echo "[3/8] Fetching latest stable Go version from go.dev..."
GO_JSON_URL="https://go.dev/dl/?include=stable&mode=json"
GO_VERSION="$(curl -fsSL "$GO_JSON_URL" | jq -r '.[0].version')"

if [[ -z "${GO_VERSION}" || "${GO_VERSION}" == "null" ]]; then
  echo "Failed to detect latest stable Go version from ${GO_JSON_URL}"
  exit 1
fi

GO_TARBALL="${GO_VERSION}.linux-${GOARCH}.tar.gz"
GO_URL="https://go.dev/dl/${GO_TARBALL}"

echo "Latest stable Go: ${GO_VERSION}"
echo "Downloading: ${GO_URL}"

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

cd "${TMP_DIR}"
wget -q --show-progress "${GO_URL}"

echo "[4/8] Installing Go to ${INSTALL_PREFIX}/go ..."
sudo rm -rf "${INSTALL_PREFIX}/go"
sudo tar -C "${INSTALL_PREFIX}" -xzf "${GO_TARBALL}"

# Remove existing Go entries before re-adding
sed -i '/# Go/d' "${HOME}/.bashrc"
sed -i '/export GOPATH=/d' "${HOME}/.bashrc"
sed -i '/export PATH=.*go\/bin/d' "${HOME}/.bashrc"

{
  echo ''
  echo '# Go'
  echo "export PATH=\$PATH:${INSTALL_PREFIX}/go/bin"
  echo "export GOPATH=${INSTALL_PREFIX}/go"
} >> "${HOME}/.bashrc"

export PATH="$PATH:${INSTALL_PREFIX}/go/bin"
export GOPATH="${INSTALL_PREFIX}/go"

# Remove existing Vault entries before re-adding
sed -i '/# Vault/d' "${HOME}/.bashrc"
sed -i '/export VAULT_ADDR=/d' "${HOME}/.bashrc"
sed -i "\|export PATH=${VAULT_BIN_DIR}|d" "${HOME}/.bashrc"

{
  echo ''
  echo '# Vault'
  echo "export PATH=${VAULT_BIN_DIR}:\$PATH"
  echo "export VAULT_ADDR='http://127.0.0.1:8200'"
} >> "${HOME}/.bashrc"

echo "[5/8] Verifying Go installation..."
go version
go env GOPATH >/dev/null

echo "[6/8] Cloning Vault source..."
mkdir -p "${GOPATH}/src/hashicorp"
cd "${GOPATH}/src/hashicorp"

if [[ -d vault ]]; then
  echo "Vault source already exists, updating..."
  cd vault
  git fetch --tags --prune
  git pull --ff-only
else
  git clone https://github.com/hashicorp/vault.git
  cd vault
fi

echo "[7/8] Building Vault from source..."
make bootstrap
export NODE_OPTIONS="--max-old-space-size=4096"
make static-dist
make dev-ui

if [[ ! -f "${GOPATH}/src/hashicorp/vault/bin/vault" ]]; then
  echo "Build finished but binary not found at expected path."
  exit 1
fi

echo "[8/8] Installing Vault binary..."
sudo mkdir -p "${VAULT_BIN_DIR}"
sudo install -m 0755 "${GOPATH}/src/hashicorp/vault/bin/vault" "${VAULT_BIN_DIR}/vault"

# setcap is skipped: container environments typically deny file capabilities,
# which causes the binary to be unexecutable. mlock is disabled in vault.hcl instead.

echo "[+] Generating Vault production config..."
sudo mkdir -p "${VAULT_DATA_DIR}"
sudo mkdir -p "${VAULT_CONFIG_DIR}"

sudo tee "${VAULT_CONFIG_DIR}/vault.hcl" > /dev/null <<EOF
ui            = true
disable_mlock = true

storage "file" {
  path = "${VAULT_DATA_DIR}"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

api_addr = "http://127.0.0.1:8200"
EOF

echo "[+] Starting Vault in background..."
sudo mkdir -p "$(dirname "${VAULT_LOG}")"
nohup "${VAULT_BIN_DIR}/vault" server -config="${VAULT_CONFIG_DIR}/vault.hcl" > "${VAULT_LOG}" 2>&1 &
echo "Vault PID: $!"
echo "Logs: ${VAULT_LOG}"

echo
echo "Done."
echo "Go version:    $(go version)"
echo "Vault version: $(vault --version)"
echo
echo "First-time setup:"
echo "  export VAULT_ADDR='http://127.0.0.1:8200'"
echo "  vault operator init"
echo "  vault operator unseal  # run 3 times with different keys"