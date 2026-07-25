#!/usr/bin/bash -l
# Provision the frozen pixi environments (idempotent). RelocaTE2 is NOT here: it
# is frozen via pinned cluster modules (callers/relocate2/pinned-modules.txt),
# not a pixi env, so it needs no install.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if ! command -v pixi >/dev/null 2>&1; then
  echo "ERROR: pixi not on PATH; required to provision frozen envs." >&2
  exit 1
fi
echo "[$(date)] provisioning frozen pixi environments"
for m in callers/relocate3 callers/relocate3/blat-env env/benchmark; do
  echo "== pixi install: $m =="
  ( cd "$m" && pixi install )
done
# --- RelocaTE2 BioContainer images (pulled, digest-pinned) ---
RT2_IMG_MANIFEST="callers/relocate2/images.txt"
RT2_IMG_DIR="callers/relocate2/images"
if [[ -f "$RT2_IMG_MANIFEST" ]]; then
  if ! command -v apptainer >/dev/null 2>&1; then
    command -v module >/dev/null 2>&1 && module load apptainer >/dev/null 2>&1 || true
  fi
  if command -v apptainer >/dev/null 2>&1; then
    mkdir -p "$RT2_IMG_DIR"
    export APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-/scratch/$USER/apptainer-cache}"
    export APPTAINER_TMPDIR="${APPTAINER_TMPDIR:-/scratch/$USER/apptainer-tmp}"
    mkdir -p "$APPTAINER_CACHEDIR" "$APPTAINER_TMPDIR"
    while read -r _name _ref; do
      [[ -z "$_name" || "$_name" == \#* ]] && continue
      _sif="$RT2_IMG_DIR/$_name.sif"
      if [[ -f "$_sif" ]]; then
        echo "== RT2 image present: $_sif (skip) =="
      else
        echo "== pulling RT2 image: $_name <- $_ref =="
        apptainer pull "$_sif" "$_ref"
      fi
    done < "$RT2_IMG_MANIFEST"
  else
    echo "WARN: apptainer unavailable; skipping RT2 image pulls (env.sh will fall back to modules)" >&2
  fi
fi
echo "[$(date)] done. Pixi envs are under each dir's .pixi/ (gitignored)."
echo "Note: RelocaTE2 uses pinned cluster modules (callers/relocate2/pinned-modules.txt) plus digest-pinned BioContainer images pulled here into callers/relocate2/images/ (gitignored); no pixi install needed."
