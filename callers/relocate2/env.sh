#!/usr/bin/bash -l
# RelocaTE2 environment for the caller adapter (sourced by run.sh, not executed).
#
# RelocaTE2 is a Python-2.7-era tool whose bioconda package (relocate2 2.0.1)
# and dependency closure (python 2.7, samtools 1.3, ncurses 5.9, ...) no longer
# resolve on current conda-forge/bioconda, so it CANNOT be frozen as a pixi env.
# Instead we pin the exact cluster modules that provide a working RT2 stack;
# the versions are the single source of truth in pinned-modules.txt. A portable,
# fully-frozen RelocaTE2 is deferred to the Phase 2 Apptainer image.
#
# The relocate2 module puts relocaTE2.py on PATH, but its bundled aligners
# (blat/samtools) live under the package bin/, which is not activated in a
# non-interactive batch shell. We add that bin/ directly, THEN load a modern bwa
# so `bwa mem` wins over the old bundled bwa 0.6.2 on PATH.
set -euo pipefail
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_pins="$_here/pinned-modules.txt"

if ! command -v module >/dev/null 2>&1; then
  echo "ERROR: 'module' unavailable; RelocaTE2 requires the pinned cluster modules in $_pins" >&2
  exit 1
fi
if [[ ! -f "$_pins" ]]; then
  echo "ERROR: missing pinned-modules manifest: $_pins" >&2
  exit 1
fi

# Read pinned module specs (single source of truth; comments/blank lines ignored).
_relocate2_mod="$(grep -E '^[[:space:]]*relocate2/' "$_pins" | head -1 | tr -d '[:space:]')"
_bwa_mod="$(grep -E '^[[:space:]]*bwa/' "$_pins" | head -1 | tr -d '[:space:]')"
: "${_relocate2_mod:?pinned-modules.txt must list a relocate2/<version> module}"
: "${_bwa_mod:?pinned-modules.txt must list a bwa/<version> module}"

# 1. relocate2 (puts relocaTE2.py on PATH).
module load "$_relocate2_mod" || { echo "ERROR: cannot load pinned module $_relocate2_mod" >&2; exit 1; }

# 2. Add the package bin/ (bundled blat/samtools), derived from relocaTE2.py's
#    resolved path, BEFORE loading the modern bwa so the modern bwa wins.
if command -v relocaTE2.py >/dev/null 2>&1; then
  _rt2_pkg="$(dirname "$(dirname "$(command -v relocaTE2.py)")")"
  [[ -d "$_rt2_pkg/bin" ]] && export PATH="$_rt2_pkg/bin:$PATH"
fi

# 3. Modern bwa for `bwa mem`.
module load "$_bwa_mod" || { echo "ERROR: cannot load pinned module $_bwa_mod" >&2; exit 1; }

# Verify every required tool is present; exit 127 (command not found) if not.
for tool in relocaTE2.py blat bwa samtools; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: $tool not available after loading pinned RelocaTE2 modules ($_relocate2_mod, $_bwa_mod)." >&2
    echo "       Expected relocaTE2.py from $_relocate2_mod and bundled blat/samtools under its bin/." >&2
    exit 127
  }
done
