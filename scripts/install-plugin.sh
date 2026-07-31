#!/usr/bin/env bash
# install-plugin.sh — set up a plugin's optional third-party dependencies.
#
# Each plugin declares the pip packages its tools import in the `requirements:`
# field of its manifest
#   autogenesis/plugins/default/<plugin>/PLUGIN.md
# Those libraries are imported lazily, so a plugin registers and shows up on the
# canvas without them; install them here to actually run its tools.
#
# Usage:
#   scripts/install-plugin.sh <plugin> [<plugin> ...]   # install those plugins' deps
#   scripts/install-plugin.sh --all                     # install every plugin's deps
#   scripts/install-plugin.sh --list [<plugin>]         # print deps, install nothing
#   scripts/install-plugin.sh --names                   # list all plugin names
#
# Honors $PIP (default: "pip") so you can use "uv pip", "pip3", etc.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_DIR="$ROOT/autogenesis/plugins/default"
PIP="${PIP:-pip}"

# Read the `requirements: [a, b, c]` list from a plugin's PLUGIN.md → space-separated.
plugin_reqs() {
  local md="$DEFAULT_DIR/$1/PLUGIN.md"
  [ -f "$md" ] || return 0
  grep -m1 -E '^requirements:' "$md" 2>/dev/null \
    | sed -E 's/^requirements:\s*\[//; s/\]\s*$//; s/,/ /g' \
    | tr -s ' '
}

all_plugins() {
  find "$DEFAULT_DIR" -mindepth 1 -maxdepth 1 -type d -exec test -e '{}/PLUGIN.md' ';' -print \
    | xargs -n1 basename | sort
}

[ $# -ge 1 ] || { grep -E '^#( |$)' "$0" | sed -E 's/^# ?//'; exit 1; }

case "$1" in
  --names)
    all_plugins; exit 0 ;;
  --list)
    shift
    targets=("$@"); [ ${#targets[@]} -gt 0 ] || mapfile -t targets < <(all_plugins)
    for b in "${targets[@]}"; do printf '%-18s %s\n' "$b" "$(plugin_reqs "$b")"; done
    exit 0 ;;
  --all)
    mapfile -t targets < <(all_plugins) ;;
  *)
    targets=("$@") ;;
esac

# Collect the union of requirements across the selected plugins.
declare -A seen; pkgs=()
for b in "${targets[@]}"; do
  [ -d "$DEFAULT_DIR/$b" ] || { echo "⚠️  unknown plugin: $b (see --names)"; continue; }
  for p in $(plugin_reqs "$b"); do
    [ -n "${seen[$p]:-}" ] || { seen[$p]=1; pkgs+=("$p"); }
  done
done

if [ ${#pkgs[@]} -eq 0 ]; then
  echo "No third-party requirements for: ${targets[*]} (nothing to install)."
  exit 0
fi

echo "Installing ${#pkgs[@]} package(s) for plugin(s) '${targets[*]}':"
printf '  %s\n' "${pkgs[@]}"
exec $PIP install "${pkgs[@]}"
