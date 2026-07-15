#!/usr/bin/bash -l
# Put relocaTE2.py, bwa, and samtools on PATH for the RelocaTE2 caller adapter.
#
# This file is meant to be *sourced* by run.sh, not executed directly.
#
# Resolution order:
#   1. `module load relocate2` (provides relocaTE2.py + the blat aligner).
#   2. `module load samtools`.
#   3. If relocaTE2.py is still not found, fall back to the RelocaTE2 conda env.
set -euo pipefail

# 1+2. Cluster modules (best effort; do not abort if `module` is unavailable).
if command -v module >/dev/null 2>&1; then
  module load relocate2 || true
  module load samtools || true
fi

# 3. Fall back to the conda env if relocaTE2.py did not appear on PATH.
if ! command -v relocaTE2.py >/dev/null 2>&1; then
  if command -v conda >/dev/null 2>&1; then
    conda activate RelocaTE2 || true
  fi
  if ! command -v relocaTE2.py >/dev/null 2>&1; then
    # `conda activate` may be unavailable in non-interactive shells; try the
    # older `source activate` entry point as a last resort.
    source activate RelocaTE2 2>/dev/null || true
  fi
fi

# Verify every required tool is present; exit 127 (command not found) if not.
for tool in relocaTE2.py bwa samtools; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: $tool not available after loading relocate2/samtools modules or the RelocaTE2 conda env" >&2
    exit 127
  }
done
