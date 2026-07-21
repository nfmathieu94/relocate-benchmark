#!/usr/bin/bash -l
#
# relocate-benchmark: sync the RelocaTE3 dev environment before re-benchmarking.
#
# RelocaTE3 is installed EDITABLE in its pixi env, so pure code edits are already
# live for the next benchmark. This helper mainly re-syncs the pixi env (deps +
# editable install) and, optionally, pulls the latest code and runs RT3's tests.
#
# The RT3 repo path is read from config (config/benchmark.toml, caller relocate3).
set -euo pipefail

# ---------------------------------------------------------------------------
# 0. Repo root.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

PY=python3.12
CONFIG="config/benchmark.toml"

# ---------------------------------------------------------------------------
# 0a. Parse flags.
# ---------------------------------------------------------------------------
DO_PULL=0
DO_TEST=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pull) DO_PULL=1; shift ;;
    --test) DO_TEST=1; shift ;;
    -h|--help)
      cat <<EOF
Usage: bash pipeline/update_relocate3.sh [--pull] [--test]

  --pull   git pull --ff-only in the RT3 repo before syncing
  --test   run the RT3 pixi 'test' task after syncing
EOF
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# 1. Resolve the RT3 repo path from config (sets RT3_REPO, TSD_PATTERN).
# ---------------------------------------------------------------------------
# All relocate3-* aligner variants share one repo; resolve it from the first
# enabled relocate3 caller (the callers list is sorted).
RT3_CALLER="$("$PY" pipeline/config_env.py --config "$CONFIG" callers | grep -m1 '^relocate3')"
eval "$("$PY" pipeline/config_env.py --config "$CONFIG" caller-env "$RT3_CALLER")"

if [[ -z "${RT3_REPO:-}" ]]; then
  echo "ERROR: RT3_REPO not found in config ($CONFIG, a callers.relocate3*.repo)" >&2
  exit 1
fi
if [[ ! -d "$RT3_REPO" ]]; then
  echo "ERROR: RT3_REPO does not exist: $RT3_REPO" >&2
  exit 1
fi
if [[ ! -f "$RT3_REPO/pixi.toml" ]]; then
  echo "ERROR: no pixi.toml in RT3_REPO: $RT3_REPO" >&2
  exit 1
fi

echo "[$(date)] RT3_REPO=$RT3_REPO"

# ---------------------------------------------------------------------------
# 2. Optionally pull the latest code.
# ---------------------------------------------------------------------------
if (( DO_PULL == 1 )); then
  echo "[$(date)] pulling latest RT3 code (git pull --ff-only)"
  git -C "$RT3_REPO" pull --ff-only
fi

# ---------------------------------------------------------------------------
# 3. Always re-sync the pixi env (deps + editable install).
# ---------------------------------------------------------------------------
echo "[$(date)] syncing pixi env (pixi install)"
pixi install --manifest-path "$RT3_REPO/pixi.toml"

# ---------------------------------------------------------------------------
# 4. Optionally run the RT3 test task.
# ---------------------------------------------------------------------------
if (( DO_TEST == 1 )); then
  echo "[$(date)] running RT3 tests (pixi run test)"
  pixi run --manifest-path "$RT3_REPO/pixi.toml" test
fi

# ---------------------------------------------------------------------------
# 5. Report the resolved RT3 git commit for the next benchmark.
# ---------------------------------------------------------------------------
RT3_COMMIT="$(git -C "$RT3_REPO" rev-parse --short HEAD)"
echo "[$(date)] RT3 env synced. Next benchmark will use RelocaTE3 commit: $RT3_COMMIT"
