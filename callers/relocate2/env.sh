#!/usr/bin/bash -l
# Put relocaTE2.py and its bundled aligners (blat, bwa, bowtie2, samtools) on
# PATH for the RelocaTE2 caller adapter. Sourced by run.sh, not executed.
#
# The `relocate2` module prepends its scripts dir (relocaTE2.py) and loads
# miniconda3, but the bundled aligners live in the package's bin/ which is only
# added via a conda env that does NOT activate in a non-interactive batch shell
# (you get "Run 'conda init' before 'conda activate'"). So blat/bwa/samtools go
# missing under sbatch. We therefore add the package bin/ directly, derived from
# relocaTE2.py's resolved path so it tracks the module version automatically.
set -euo pipefail

if command -v module >/dev/null 2>&1; then
  module load relocate2 || true
fi

if command -v relocaTE2.py >/dev/null 2>&1; then
  # .../relocate2/<version>/scripts/relocaTE2.py -> pkg root is two levels up.
  _rt2_pkg="$(dirname "$(dirname "$(command -v relocaTE2.py)")")"
  if [[ -d "$_rt2_pkg/bin" ]]; then
    export PATH="$_rt2_pkg/bin:$PATH"
  fi
fi

# Verify every required tool is present; exit 127 (command not found) if not.
for tool in relocaTE2.py blat bwa samtools; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: $tool not available after loading the relocate2 module." >&2
    echo "       Expected the bundled binaries under <relocate2>/bin (blat/bwa/samtools)." >&2
    exit 127
  }
done
