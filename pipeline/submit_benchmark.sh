#!/usr/bin/bash -l
#
# relocate-benchmark submission orchestrator.
#
# Ensures truth is exported, computes the array size from the config, submits
# the SLURM array, and prints the post-array aggregation commands. Run this from
# the repo root (or anywhere; it relocates itself).
set -euo pipefail

# ---------------------------------------------------------------------------
# 0. Repo root.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SLURM_SUBMIT_DIR:-$SCRIPT_DIR/..}"

PY=python3.12
CONFIG="${CONFIG:-config/benchmark.toml}"

echo "[$(date)] submit_benchmark: config=$CONFIG"

# ---------------------------------------------------------------------------
# 1. Ensure truth is exported (idempotent: skip if truth/.complete present).
# ---------------------------------------------------------------------------
if [[ -f truth/.complete ]]; then
  echo "[$(date)] truth already exported (truth/.complete present); skipping export"
else
  echo "[$(date)] exporting truth from panel"
  eval "$("$PY" pipeline/config_env.py --config "$CONFIG" globals)"
  "$PY" scoring/export_truth.py --panel-root "$PANEL_ROOT" --outdir truth
fi

# ---------------------------------------------------------------------------
# 2. Array size = number of tasks.
# ---------------------------------------------------------------------------
N="$("$PY" pipeline/config_env.py --config "$CONFIG" count)"
if (( N < 1 )); then
  echo "ERROR: no benchmark tasks (count=$N); check enabled callers and manifest" >&2
  exit 1
fi
echo "[$(date)] submitting array of $N task(s) (indices 0-$((N - 1)))"

mkdir -p logs

# ---------------------------------------------------------------------------
# 3. Submit the array. Propagate CONFIG to the tasks.
# ---------------------------------------------------------------------------
JOB_ID="$(sbatch --parsable \
  --array="0-$((N - 1))" \
  --export=ALL,CONFIG="$CONFIG" \
  pipeline/run_benchmark_array.sh)"

echo "[$(date)] submitted SLURM array job: $JOB_ID"

# ---------------------------------------------------------------------------
# 4. Next steps (run after the array finishes).
# ---------------------------------------------------------------------------
cat <<EOF

Array job $JOB_ID submitted ($N tasks).

After ALL array tasks finish, aggregate the results:

  $PY scoring/combine_reports.py --report-root reports --samples truth/samples.tsv
  $PY scoring/compare_callers.py --correctness reports/correctness.tsv --outdir reports

EOF
