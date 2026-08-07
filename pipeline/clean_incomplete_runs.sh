#!/usr/bin/bash -l
#
# Remove caller run directories that have no .run_complete sentinel.
#
# Why this exists: the caller adapters (callers/*/run.sh) deliberately refuse to
# start in a non-empty output directory that lacks .run_complete (exit 1), so a
# task that was cancelled, timed out, or OOM'd leaves behind a directory that
# blocks its own rerun. This clears exactly those, and never touches a completed
# run.
#
# Dry-run by default. Pass --apply to actually delete.
#
# Usage:
#   bash pipeline/clean_incomplete_runs.sh --dataset ricetelib
#   bash pipeline/clean_incomplete_runs.sh --dataset ricetelib --caller relocate3-blat-bwaaln --apply
set -euo pipefail

BASE_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$BASE_DIR"

DATASET=""
CALLER=""
APPLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dataset) DATASET="${2:?--dataset needs a value}"; shift 2 ;;
    --caller)  CALLER="${2:?--caller needs a value}";   shift 2 ;;
    --apply)   APPLY=1; shift ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$DATASET" ]]; then
  echo "ERROR: --dataset is required (e.g. --dataset ricetelib)" >&2
  exit 1
fi

ROOT="runs/$DATASET"
if [[ ! -d "$ROOT" ]]; then
  echo "ERROR: no run root for dataset '$DATASET': $ROOT" >&2
  exit 1
fi

SEARCH_ROOT="$ROOT"
if [[ -n "$CALLER" ]]; then
  SEARCH_ROOT="$ROOT/$CALLER"
  if [[ ! -d "$SEARCH_ROOT" ]]; then
    echo "ERROR: no run dir for caller '$CALLER': $SEARCH_ROOT" >&2
    exit 1
  fi
fi

# Sample dirs live at runs/<dataset>/<caller>/<sample>, so mindepth/maxdepth are
# both relative to the search root and differ depending on whether --caller was
# given.
if [[ -n "$CALLER" ]]; then DEPTH=(-mindepth 1 -maxdepth 1); else DEPTH=(-mindepth 2 -maxdepth 2); fi

mapfile -t INCOMPLETE < <(
  find "$SEARCH_ROOT" "${DEPTH[@]}" -type d \
    '!' -exec test -e '{}/.run_complete' ';' -print | sort
)

if [[ ${#INCOMPLETE[@]} -eq 0 ]]; then
  echo "No incomplete run directories under $SEARCH_ROOT -- nothing to clean."
  exit 0
fi

echo "Incomplete run directories under $SEARCH_ROOT (no .run_complete):"
for d in "${INCOMPLETE[@]}"; do
  printf '  %-62s %s\n' "$d" "$(du -sh "$d" 2>/dev/null | cut -f1)"
done

if [[ "$APPLY" -ne 1 ]]; then
  echo
  echo "Dry run. Re-run with --apply to delete these ${#INCOMPLETE[@]} directories."
  exit 0
fi

# Refuse to delete anything a live job is still writing to, so this can't be run
# out from under a running array.
if squeue -u "$USER" -h -o '%T' 2>/dev/null | grep -q RUNNING; then
  echo
  echo "ERROR: you still have RUNNING jobs. Deleting run dirs now risks removing" >&2
  echo "       output from a live task. Wait for them to finish, then re-run." >&2
  exit 1
fi

echo
for d in "${INCOMPLETE[@]}"; do
  echo "removing $d"
  rm -rf "$d"
done
echo "Removed ${#INCOMPLETE[@]} incomplete run directories."
