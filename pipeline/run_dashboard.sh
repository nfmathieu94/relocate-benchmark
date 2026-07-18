#!/usr/bin/bash -l
# Launch the read-only benchmark dashboard from the frozen benchmark environment.
set -euo pipefail

BASE_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$BASE_DIR"

MANIFEST="env/benchmark/pixi.toml"
if [[ ! -f "$MANIFEST" ]]; then
  echo "ERROR: benchmark Pixi manifest not found: $MANIFEST" >&2
  echo "       Run this command from the relocate-benchmark project root." >&2
  exit 1
fi
if ! command -v pixi >/dev/null 2>&1; then
  echo "ERROR: pixi is required to launch the dashboard." >&2
  exit 127
fi

exec pixi run --manifest-path "$MANIFEST" dashboard "$@"
