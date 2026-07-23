#!/usr/bin/bash -l
# Activate the configured RelocaTE3 development environment.  This is the source
# tree under test, including the variable-length ``--tsd UNK`` inference path.
set -euo pipefail
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_manifest="${RT3_REPO:-}/pixi.toml"

if command -v pixi >/dev/null 2>&1 && [[ -n "${RT3_REPO:-}" ]] && [[ -f "$_manifest" ]]; then
  eval "$(pixi shell-hook --manifest-path "$_manifest")"
else
  echo "WARN: configured RelocaTE3 pixi env unavailable; using frozen benchmark env" >&2
  _manifest="$_here/pixi.toml"
  if command -v pixi >/dev/null 2>&1 && [[ -f "$_manifest" ]]; then
    eval "$(pixi shell-hook --manifest-path "$_manifest")"
  fi
  command -v module >/dev/null 2>&1 && { module load bcftools || true; }
fi

# The RelocaTE3 development pixi manifest intentionally does not bundle
# bcftools.  Use the HPCC module for that external runtime dependency.
RT3_BCFTOOLS="${RT3_BCFTOOLS:-bcftools}"
if ! command -v "$RT3_BCFTOOLS" >/dev/null 2>&1 && command -v module >/dev/null 2>&1; then
  # Some HPCC modulefiles emit a non-zero logger status after updating PATH.
  module load bcftools || true
fi
if ! command -v "$RT3_BCFTOOLS" >/dev/null 2>&1 && [[ -x "$_here/.pixi/envs/default/bin/bcftools" ]]; then
  # Reuse bcftools from the benchmark's frozen runtime; the development pixi
  # manifest deliberately omits it while its module is unavailable here.
  RT3_BCFTOOLS="$_here/.pixi/envs/default/bin/bcftools"
fi
export RT3_BCFTOOLS

for tool in relocaTE3 minimap2 samtools "$RT3_BCFTOOLS"; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: $tool not available after activating RelocaTE3 env" >&2
    exit 127
  }
done
