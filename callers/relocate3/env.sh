#!/usr/bin/bash -l
# Activate the RelocaTE3 dev repo's pixi environment into the current shell so
# that relocaTE3, minimap2, and samtools are on PATH, and ensure bcftools is
# available for the `characterize` step.
#
# This file is meant to be *sourced* by run.sh, not executed directly.
# Required env var:
#   RT3_REPO  path to the RelocaTE3 repo (contains pixi.toml / pyproject.toml)
set -euo pipefail

: "${RT3_REPO:?RT3_REPO must be set (RelocaTE3 repo path)}"

# Prefer the pixi manifest that actually exists in the repo.
if [[ -f "$RT3_REPO/pixi.toml" ]]; then
  RT3_MANIFEST="$RT3_REPO/pixi.toml"
elif [[ -f "$RT3_REPO/pyproject.toml" ]]; then
  RT3_MANIFEST="$RT3_REPO/pyproject.toml"
else
  echo "ERROR: no pixi manifest (pixi.toml/pyproject.toml) under $RT3_REPO" >&2
  exit 1
fi

# The RT3 pixi env does not ship bcftools (which `characterize` needs), so load
# it from a cluster module FIRST — the pixi shell-hook is applied afterwards so
# the pixi env's own tools (relocaTE3/minimap2/samtools) still win on PATH,
# while bcftools (absent from the pixi env) resolves to the module.
if command -v module >/dev/null 2>&1; then
  module load bcftools || true
fi

# Activate the pixi env into the current shell so the tools are on PATH.
if command -v pixi >/dev/null 2>&1; then
  eval "$(pixi shell-hook --manifest-path "$RT3_MANIFEST")"
else
  echo "ERROR: pixi not found on PATH" >&2
  exit 127
fi

for tool in relocaTE3 minimap2 samtools bcftools; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: $tool not available after activating RT3 env ($RT3_MANIFEST)" >&2
    exit 127
  }
done
