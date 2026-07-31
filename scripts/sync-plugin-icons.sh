#!/usr/bin/env bash
# Sync plugin glyphs into the frontend so the palette can render them.
#
# Each plugin keeps its own SVG as the source of truth at
#   autogenesis/plugins/default/<plugin>/resources/icon.svg
# The frontend resolves NodeSpec.icon "plugin:<plugin>" to
#   frontend/src/icons/plugins/<plugin>.svg
# Re-run this after adding or updating any plugin icon.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/autogenesis/plugins/default"
DST="$ROOT/frontend/src/icons/plugins"
mkdir -p "$DST"
n=0
for f in "$SRC"/*/resources/icon.svg; do
  [ -e "$f" ] || continue
  b="$(basename "$(dirname "$(dirname "$f")")")"
  cp "$f" "$DST/$b.svg"
  n=$((n + 1))
done
echo "Synced $n plugin icons -> $DST"
