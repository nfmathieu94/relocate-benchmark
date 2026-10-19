#!/usr/bin/bash -l
# Development-tier RelocaTE3 adapter: the standard adapter in replay mode.
# Reuses a registered full-tier run's TE-search BAMs and genotyping BAM and
# reruns trim, align-genome, find-insertions and characterize from RT3_REPO.
# See docs/plans/2026-10-19-dev-replay-tier-design.md.
set -euo pipefail
: "${RT3_REPLAY_MANIFEST:?replay caller needs replay_manifest in its config table}"
export ADAPTER_DIR="callers/relocate3"
exec bash callers/relocate3/run.sh
