#!/usr/bin/env bash
set -euo pipefail

# Install Playwright (Chromium) for a given Python/conda environment.
# Usage: bash install_playwright.sh [PYTHON]
# Default PYTHON: python
#
# Examples:
#   bash install_playwright.sh
#   bash install_playwright.sh /path/to/conda/envs/agentos/bin/python

PYTHON="${1:-python}"

echo "Python: ${PYTHON}"

# ---------------------------------------------------------------------------
# Step 1: Install playwright Python package if not already present
# ---------------------------------------------------------------------------
echo "[1/3] Installing playwright Python package..."
"${PYTHON}" -m pip install --upgrade playwright

# ---------------------------------------------------------------------------
# Step 2: Install Chromium browser binary via playwright
# ---------------------------------------------------------------------------
echo "[2/3] Installing Chromium via playwright..."
"${PYTHON}" -m playwright install chromium

# ---------------------------------------------------------------------------
# Step 3: Install Chromium system dependencies (includes libnspr4, libnss3, etc.)
# ---------------------------------------------------------------------------
echo "[3/3] Installing Chromium system dependencies..."
"${PYTHON}" -m playwright install-deps chromium

echo
echo "Done."
CHROMIUM_PATH=$("${PYTHON}" -c "
import subprocess, sys
result = subprocess.run(
    [sys.executable, '-m', 'playwright', 'show-path', 'chromium'],
    capture_output=True, text=True
)
# playwright show-path prints the browser dir; find the actual binary
import pathlib
browser_dir = result.stdout.strip()
binary = pathlib.Path(browser_dir).parent / 'chrome-linux64' / 'chrome'
if binary.exists():
    print(binary)
else:
    # fallback: search
    for p in pathlib.Path(browser_dir).parent.rglob('chrome'):
        if p.is_file():
            print(p)
            break
" 2>/dev/null || true)

if [[ -n "${CHROMIUM_PATH}" ]]; then
  echo "Chromium binary: ${CHROMIUM_PATH}"
else
  echo "Chromium binary: (run 'python -m playwright show-path chromium' to locate)"
fi
