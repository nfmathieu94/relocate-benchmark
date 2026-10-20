#!/usr/bin/bash -l
# Frozen-baseline caller adapter (development tier).
#
# Re-scores a caller that is not under development (RelocaTE2) without rerunning
# it: copies <FROZEN_SOURCE_ROOT>/<DATASET>/<FROZEN_SOURCE_CALLER>/<SAMPLE>/
# calls.normalized.tsv into OUTDIR. Scoring then runs as for any caller, so the
# baseline always follows the current scoring policy. This task's resource
# usage measures a file copy, not the caller.
#
# Contract (env vars): DATASET SAMPLE OUTDIR FROZEN_SOURCE_ROOT FROZEN_SOURCE_CALLER
set -euo pipefail

: "${DATASET:?DATASET must be set}"
: "${SAMPLE:?SAMPLE must be set}"
: "${OUTDIR:?OUTDIR must be set}"
: "${FROZEN_SOURCE_ROOT:?FROZEN_SOURCE_ROOT must be set (config source_root)}"
: "${FROZEN_SOURCE_CALLER:?FROZEN_SOURCE_CALLER must be set (config source_caller)}"

SOURCE_DIR="$FROZEN_SOURCE_ROOT/$DATASET/$FROZEN_SOURCE_CALLER/$SAMPLE"
SOURCE_CALLS="$SOURCE_DIR/calls.normalized.tsv"

if [[ -f "$OUTDIR/.run_complete" ]]; then
  echo "[$(date)] frozen copy already complete for '$SAMPLE'; skipping."
  exit 0
fi
if [[ -d "$OUTDIR" ]] && [[ -n "$(ls -A "$OUTDIR" 2>/dev/null)" ]]; then
  echo "ERROR: refusing incomplete non-empty run dir: $OUTDIR" >&2
  exit 1
fi
if [[ ! -f "$SOURCE_DIR/.run_complete" ]]; then
  echo "ERROR: frozen source run is incomplete (no .run_complete): $SOURCE_DIR" >&2
  exit 1
fi
if [[ ! -f "$SOURCE_CALLS" ]]; then
  echo "ERROR: frozen source calls missing: $SOURCE_CALLS" >&2
  exit 1
fi

echo "[$(date)] frozen baseline: $SOURCE_CALLS"
mkdir -p "$OUTDIR"
cp "$SOURCE_CALLS" "$OUTDIR/calls.normalized.tsv.tmp"
mv -f "$OUTDIR/calls.normalized.tsv.tmp" "$OUTDIR/calls.normalized.tsv"
printf 'source\t%s\n' "$SOURCE_CALLS" > "$OUTDIR/frozen_source.tsv"
date > "$OUTDIR/.run_complete"
