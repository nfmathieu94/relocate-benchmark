#!/usr/bin/bash -l
# Activate the frozen RelocaTE3 pixi env for the caller adapter (sourced by run.sh).
# The env (callers/relocate3/pixi.toml) pins RelocaTE3 to a git rev and includes
# bcftools, so no `module load bcftools` patch is needed.
set -euo pipefail
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_manifest="$_here/pixi.toml"

if command -v pixi >/dev/null 2>&1 && [[ -f "$_manifest" ]]; then
  eval "$(pixi shell-hook --manifest-path "$_manifest")"
else
  echo "WARN: frozen pixi env unavailable; falling back to UNPINNED environment" >&2
  command -v module >/dev/null 2>&1 && { module load bcftools || true; }
  if [[ -n "${RT3_REPO:-}" ]] && command -v pixi >/dev/null 2>&1 && [[ -f "$RT3_REPO/pixi.toml" ]]; then
    eval "$(pixi shell-hook --manifest-path "$RT3_REPO/pixi.toml")"
  fi
fi

for tool in relocaTE3 minimap2 samtools bcftools; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: $tool not available after activating RelocaTE3 env" >&2
    exit 127
  }
done
