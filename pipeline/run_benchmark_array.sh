#!/usr/bin/bash -l
#SBATCH -p epyc
#SBATCH --mem=64gb
#SBATCH --cpus-per-task=8
#SBATCH --time=24:00:00
#SBATCH -o logs/benchmark.%A_%a.log
#
# relocate-benchmark SLURM array runner.
#
# One array task = one (caller, sample) pair. The task index maps to a line of
# `config_env.py tasks` (deterministic: callers sorted x manifest order). Each
# task runs the caller adapter under /usr/bin/time -v, normalizes its calls,
# scores them against exported truth, and records resource usage.
#
# Submit via pipeline/submit_benchmark.sh (do not sbatch directly).
set -euo pipefail

# ---------------------------------------------------------------------------
# 0. Repo root + config bridge.
# ---------------------------------------------------------------------------
cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
CONFIG="${CONFIG:-config/benchmark.toml}"
PY=python3.12

echo "[$(date)] benchmark array task starting"
echo "  host    : $(hostname)"
echo "  config  : $CONFIG"

# ---------------------------------------------------------------------------
# 1. Load global env (REFERENCE TE_LIBRARY REPEATMASKER TE_NAME PANEL_ROOT
#    WORK_ROOT THREADS MATCH_WINDOW).
# ---------------------------------------------------------------------------
eval "$("$PY" pipeline/config_env.py --config "$CONFIG" globals)"
THREADS="${SLURM_CPUS_PER_TASK:-$THREADS}"

# ---------------------------------------------------------------------------
# 2. Resolve this task's line.
# ---------------------------------------------------------------------------
TASK_ID="${SLURM_ARRAY_TASK_ID:?SLURM_ARRAY_TASK_ID required}"
LINE="$("$PY" pipeline/config_env.py --config "$CONFIG" tasks | sed -n "$((TASK_ID + 1))p")"
if [[ -z "$LINE" ]]; then
  echo "ERROR: no task for array index $TASK_ID" >&2
  exit 1
fi
IFS=$'\t' read -r CALLER SAMPLE COVERAGE REPLICATE R1 R2 <<< "$LINE"

echo "  task_id : $TASK_ID"
echo "  caller  : $CALLER"
echo "  sample  : $SAMPLE (cov=$COVERAGE rep=$REPLICATE)"
echo "  R1      : $R1"
echo "  R2      : $R2"
echo "  threads : $THREADS"

# ---------------------------------------------------------------------------
# 3. Output layout.
# ---------------------------------------------------------------------------
OUTDIR="$WORK_ROOT/$CALLER/$SAMPLE"
REPORT_DIR="reports/per_sample/$CALLER/$SAMPLE"
RES_DIR="reports/resources/$CALLER"
# NOTE: do NOT pre-create REPORT_DIR; score_calls refuses a non-empty one.
mkdir -p "$RES_DIR" logs

# ---------------------------------------------------------------------------
# 4. Export the caller contract env vars.
# ---------------------------------------------------------------------------
export SAMPLE R1 R2 OUTDIR THREADS
export REFERENCE TE_LIBRARY REPEATMASKER TE_NAME

# Caller-specific extras (RT3_REPO/TSD_PATTERN/RT3_TE_ALIGNER/RT3_GENOME_ALIGNER
# or RT2_ALIGNER/RT2_SIZE/RT2_MISMATCH).
eval "$("$PY" pipeline/config_env.py --config "$CONFIG" caller-env "$CALLER")"
for v in RT3_REPO TSD_PATTERN RT3_TE_ALIGNER RT3_GENOME_ALIGNER \
         RT2_ALIGNER RT2_SIZE RT2_MISMATCH; do
  if [[ -n "${!v+x}" ]]; then
    export "${v?}"
  fi
done

# Resolve the adapter dir from config so several callers (e.g. the RelocaTE3
# aligner variants) can share one adapter. Defaults to callers/<caller>.
ADAPTER="$("$PY" pipeline/config_env.py --config "$CONFIG" adapter "$CALLER")"

# ---------------------------------------------------------------------------
# 5. Run the caller adapter under /usr/bin/time -v.
# ---------------------------------------------------------------------------
TIME_FILE="$RES_DIR/${SAMPLE}.time-v.txt"
echo "[$(date)] running caller adapter: $ADAPTER/run.sh"
/usr/bin/time -v -o "$TIME_FILE" bash "$ADAPTER/run.sh"

# ---------------------------------------------------------------------------
# 6. Normalize (uniform call for every caller).
# ---------------------------------------------------------------------------
echo "[$(date)] normalizing calls"
"$PY" "$ADAPTER/normalize.py" \
  --outdir "$OUTDIR" \
  --sample "$SAMPLE" \
  --te-name "$TE_NAME" \
  --target ALL

# ---------------------------------------------------------------------------
# 7. Score against exported truth.
# ---------------------------------------------------------------------------
echo "[$(date)] scoring calls"
"$PY" scoring/score_calls.py \
  --truth truth/truth.tsv \
  --calls "$OUTDIR/calls.normalized.tsv" \
  --sample "$SAMPLE" \
  --caller "$CALLER" \
  --window "$MATCH_WINDOW" \
  --outdir "$REPORT_DIR"

# ---------------------------------------------------------------------------
# 8. Parse resource usage.
# ---------------------------------------------------------------------------
echo "[$(date)] parsing resource usage"
"$PY" scoring/parse_time_v.py \
  --time-v "$TIME_FILE" \
  --sample "$SAMPLE" \
  --caller "$CALLER" \
  --coverage "$COVERAGE" \
  --replicate "$REPLICATE" \
  --out "$RES_DIR/${SAMPLE}.tsv"

echo "[$(date)] task $TASK_ID complete: $CALLER / $SAMPLE"
