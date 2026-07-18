#!/usr/bin/bash -l
# RelocaTE2 environment for the caller adapter (sourced by run.sh, not executed).
#
# Container-first: expose relocaTE2.py/blat/samtools (from a relocate2
# BioContainer) and bwa (from a bwa 0.7.19 BioContainer) as apptainer-exec shims
# on PATH, so run.sh is unchanged. RelocaTE2 cannot be a pixi env (dead py2.7
# bioconda package), and this cluster cannot build images locally, so we PULL
# digest-pinned BioContainers (see images.txt). Fallback: Phase 1 pinned cluster
# modules (pinned-modules.txt); then error.
set -euo pipefail
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_img_dir="$_here/images"
_relocate2_sif="$_img_dir/relocate2.sif"
_bwa_sif="$_img_dir/bwa.sif"

_setup_container_env() {
  if ! command -v apptainer >/dev/null 2>&1; then
    command -v module >/dev/null 2>&1 && module load apptainer >/dev/null 2>&1 || true
  fi
  command -v apptainer >/dev/null 2>&1 || return 1
  [[ -f "$_relocate2_sif" && -f "$_bwa_sif" ]] || return 1

  export APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-/scratch/$USER/apptainer-cache}"

  # Task-scoped shim bin dir: each tool execs its image.
  _shim_bin="$(mktemp -d "${TMPDIR:-/scratch/$USER}/rt2-shims.XXXXXX")"

  # RelocaTE2's bundled Perl scripts (fastq_split.pl, ...) hardcode
  # `#!/usr/bin/perl`, which the BioContainer lacks (its perl is
  # /usr/local/bin/perl). Bind a wrapper so /usr/bin/perl inside the container
  # runs the container's own perl; without this the fastq split silently
  # produces nothing and relocaTE2.py dies with an IndexError.
  local _perl_wrapper="$_shim_bin/.perl-in-container"
  printf '#!/bin/bash\nexec /usr/local/bin/perl "$@"\n' > "$_perl_wrapper"
  chmod +x "$_perl_wrapper"

  # Bind data + repo + scratch roots (so containers see reference/reads/OUTDIR)
  # plus the perl wrapper; silence the container's locale warnings.
  export APPTAINER_BIND="/bigdata,/rhome,/scratch,$_perl_wrapper:/usr/bin/perl${APPTAINER_BIND:+,$APPTAINER_BIND}"
  export APPTAINERENV_LC_ALL=C

  local t
  for t in relocaTE2.py blat samtools; do
    printf '#!/usr/bin/bash\nexec apptainer exec %q %s "$@"\n' "$_relocate2_sif" "$t" > "$_shim_bin/$t"
    chmod +x "$_shim_bin/$t"
  done
  printf '#!/usr/bin/bash\nexec apptainer exec %q bwa "$@"\n' "$_bwa_sif" > "$_shim_bin/bwa"
  chmod +x "$_shim_bin/bwa"
  export PATH="$_shim_bin:$PATH"
  return 0
}

_setup_module_env() {
  local pins="$_here/pinned-modules.txt"
  command -v module >/dev/null 2>&1 || return 1
  [[ -f "$pins" ]] || return 1
  local r2 bw pkg
  r2="$(grep -E '^[[:space:]]*relocate2/' "$pins" | head -1 | tr -d '[:space:]')"
  bw="$(grep -E '^[[:space:]]*bwa/' "$pins" | head -1 | tr -d '[:space:]')"
  [[ -n "$r2" && -n "$bw" ]] || return 1
  module load "$r2" || return 1
  if command -v relocaTE2.py >/dev/null 2>&1; then
    pkg="$(dirname "$(dirname "$(command -v relocaTE2.py)")")"
    [[ -d "$pkg/bin" ]] && export PATH="$pkg/bin:$PATH"
  fi
  module load "$bw" || return 1
  return 0
}

if _setup_container_env; then
  :
else
  echo "WARN: RT2 container env unavailable; falling back to UNPINNED pinned cluster modules" >&2
  _setup_module_env || {
    echo "ERROR: could not set up a RelocaTE2 environment (no containers, no modules)" >&2
    exit 1
  }
fi

# Verify every required tool is present; exit 127 if not.
for tool in relocaTE2.py blat bwa samtools; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: $tool not available after RelocaTE2 env setup" >&2
    exit 127
  }
done
