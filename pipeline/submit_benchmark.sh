#!/usr/bin/bash -l
#
# relocate-benchmark submission orchestrator.
#
# Ensures truth is exported, computes the array spec from the config (optionally
# narrowed by filters), submits the SLURM array, and submits a dependent
# aggregation job that runs automatically once the array finishes. Run this from
# the repo root (or anywhere; it relocates itself).
set -euo pipefail

# ---------------------------------------------------------------------------
# 0. Repo root.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SLURM_SUBMIT_DIR:-$SCRIPT_DIR/..}"

if command -v pixi >/dev/null 2>&1 && [[ -f env/benchmark/pixi.toml ]]; then
  PY=(pixi run --manifest-path env/benchmark/pixi.toml python3)
else
  PY=(python3.12)
fi
CONFIG="${CONFIG:-config/benchmark.toml}"

# ---------------------------------------------------------------------------
# 0a. Parse optional filter flags and options.
# ---------------------------------------------------------------------------
FILTER_CALLER=""
FILTER_COVERAGE=""
FILTER_SAMPLE=""
FILTER_REPLICATE=""
NO_AGGREGATE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --caller)     FILTER_CALLER="$2";    shift 2 ;;
    --coverage)   FILTER_COVERAGE="$2";  shift 2 ;;
    --sample)     FILTER_SAMPLE="$2";    shift 2 ;;
    --replicate)  FILTER_REPLICATE="$2"; shift 2 ;;
    --no-aggregate) NO_AGGREGATE=1;      shift ;;
    -h|--help)    SHOW_HELP=1;           shift ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

print_help() {
  cat <<EOF
Usage: bash pipeline/submit_benchmark.sh [options]

Options:
  --caller <list>      Only run these caller(s)      (comma-separated)
  --coverage <list>    Only run these coverage(s)    (comma-separated)
  --sample <list>      Only run these sample(s)      (comma-separated)
  --replicate <list>   Only run these replicate(s)   (comma-separated)
  --no-aggregate       Skip the automatic dependent aggregation job
  -h, --help           Show this help and exit

Filters narrow the SLURM array to the matching canonical task indices; with no
filters the full array is submitted. Example:

  bash pipeline/submit_benchmark.sh --caller relocate3 --coverage 30

Aggregation now runs automatically after the array (a dependent SLURM job),
unless --no-aggregate is given. If you skip it, aggregate manually with:

  ${PY[*]} scoring/combine_reports.py --report-root reports --samples truth/samples.tsv
  ${PY[*]} scoring/compare_callers.py --correctness reports/correctness.tsv --outdir reports
EOF
}

if [[ "${SHOW_HELP:-0}" == "1" ]]; then
  print_help
  exit 0
fi

echo "[$(date)] submit_benchmark: config=$CONFIG"

# ---------------------------------------------------------------------------
# 1. Ensure truth is exported (idempotent: skip if truth/.complete present).
# ---------------------------------------------------------------------------
if [[ -f truth/.complete ]]; then
  echo "[$(date)] truth already exported (truth/.complete present); skipping export"
else
  echo "[$(date)] exporting truth from panel"
  eval "$("${PY[@]}" pipeline/config_env.py --config "$CONFIG" globals)"
  "${PY[@]}" scoring/export_truth.py --panel-root "$PANEL_ROOT" --outdir truth
fi

# ---------------------------------------------------------------------------
# 2. Compute the array spec.
#    Any filter set -> indices from config_env; otherwise the full 0-(N-1).
# ---------------------------------------------------------------------------
if [[ -n "$FILTER_CALLER" || -n "$FILTER_COVERAGE" || -n "$FILTER_SAMPLE" || -n "$FILTER_REPLICATE" ]]; then
  IDX_ARGS=()
  [[ -n "$FILTER_CALLER" ]]    && IDX_ARGS+=(--caller "$FILTER_CALLER")
  [[ -n "$FILTER_COVERAGE" ]]  && IDX_ARGS+=(--coverage "$FILTER_COVERAGE")
  [[ -n "$FILTER_SAMPLE" ]]    && IDX_ARGS+=(--sample "$FILTER_SAMPLE")
  [[ -n "$FILTER_REPLICATE" ]] && IDX_ARGS+=(--replicate "$FILTER_REPLICATE")

  ARRAY="$("${PY[@]}" pipeline/config_env.py --config "$CONFIG" indices "${IDX_ARGS[@]}")"
  if [[ -z "$ARRAY" ]]; then
    echo "ERROR: no tasks match the given filters; nothing to submit" >&2
    exit 1
  fi
  echo "[$(date)] filtered submission; array indices: $ARRAY"
else
  N="$("${PY[@]}" pipeline/config_env.py --config "$CONFIG" count)"
  if (( N < 1 )); then
    echo "ERROR: no benchmark tasks (count=$N); check enabled callers and manifest" >&2
    exit 1
  fi
  ARRAY="0-$((N - 1))"
  echo "[$(date)] submitting full array of $N task(s) (indices $ARRAY)"
fi

mkdir -p logs

# ---------------------------------------------------------------------------
# 2b. Pre-build shared TE-library aligner indexes (serial), before the array.
#     RelocaTE3 builds its TE-library index INSIDE `relocaTE3 run` with an
#     unlocked check-then-build (RelocaTE3 src/RelocaTE3/aligners.py). When many
#     array tasks share one TE library they race on the same index prefix in the
#     shared input dir and corrupt it (observed: bowtie2 "Index is corrupt ...
#     size 0", then partial index -> ~0% alignment -> empty results). Building
#     each needed index ONCE here makes every task's inline build a no-op,
#     eliminating the race. The TE library is tiny, so this is cheap on the
#     submit host. (Genome indexes are pre-built out-of-band and already present;
#     they are not rebuilt here to avoid heavy compute on the submit node.)
# ---------------------------------------------------------------------------
eval "$("${PY[@]}" pipeline/config_env.py --config "$CONFIG" globals)"

_csv_has() {  # _csv_has <needle> <csv>; true if csv empty (no filter) or contains needle
  local needle="$1" csv="$2" x
  [[ -z "$csv" ]] && return 0
  local IFS=,
  for x in $csv; do [[ "$x" == "$needle" ]] && return 0; done
  return 1
}

# Unique TE-library aligners across enabled RelocaTE3 callers in this submission
# (honoring --caller). Non-RelocaTE3 callers emit no RT3_TE_ALIGNER and are skipped.
TE_ALIGNERS=()
while IFS= read -r caller; do
  [[ -z "$caller" ]] && continue
  _csv_has "$caller" "$FILTER_CALLER" || continue
  cenv="$("${PY[@]}" pipeline/config_env.py --config "$CONFIG" caller-env "$caller")"
  te="$(sed -n 's/^RT3_TE_ALIGNER=//p' <<<"$cenv" | tr -d "'")"
  [[ -n "$te" ]] && TE_ALIGNERS+=("$te")
done < <("${PY[@]}" pipeline/config_env.py --config "$CONFIG" callers)

if ((${#TE_ALIGNERS[@]} > 0)); then
  # Activate the RelocaTE3 env so the pre-build tools match those the tasks use.
  source callers/relocate3/env.sh
  while IFS= read -r aligner; do
    case "$aligner" in
      bowtie2)
        [[ -s "${TE_LIBRARY}.1.bt2" ]] || {
          echo "[$(date)] pre-building bowtie2 index: $TE_LIBRARY"
          bowtie2-build --quiet "$TE_LIBRARY" "$TE_LIBRARY"; } ;;
      bwa)
        [[ -s "${TE_LIBRARY}.bwt" ]] || {
          echo "[$(date)] pre-building bwa index: $TE_LIBRARY"
          bwa index "$TE_LIBRARY"; } ;;
      minimap2)
        [[ -s "${TE_LIBRARY}.mmi" ]] || {
          echo "[$(date)] pre-building minimap2 index: $TE_LIBRARY"
          minimap2 -d "${TE_LIBRARY}.mmi" "$TE_LIBRARY"; } ;;
      blat) : ;;  # blat needs no persistent index
      *) echo "WARN: unknown te-aligner '$aligner'; leaving its index to the task" >&2 ;;
    esac
  done < <(printf '%s\n' "${TE_ALIGNERS[@]}" | sort -u)
fi

# ---------------------------------------------------------------------------
# 3. Submit the array. Propagate CONFIG to the tasks.
# ---------------------------------------------------------------------------
ARRAY_JOB="$(sbatch --parsable \
  --array="$ARRAY" \
  --export=ALL,CONFIG="$CONFIG" \
  pipeline/run_benchmark_array.sh)"

echo "[$(date)] submitted SLURM array job: $ARRAY_JOB"

# ---------------------------------------------------------------------------
# 4. Submit the dependent aggregation job (unless suppressed).
# ---------------------------------------------------------------------------
if (( NO_AGGREGATE == 1 )); then
  cat <<EOF

Array job $ARRAY_JOB submitted (array=$ARRAY).
Aggregation skipped (--no-aggregate). After ALL array tasks finish, run:

  ${PY[*]} scoring/combine_reports.py --report-root reports --samples truth/samples.tsv
  ${PY[*]} scoring/compare_callers.py --correctness reports/correctness.tsv --outdir reports

EOF
else
  AGG_JOB="$(sbatch --parsable \
    --dependency=afterok:"$ARRAY_JOB" \
    --export=ALL,CONFIG="$CONFIG" \
    pipeline/aggregate.sh)"
  echo "[$(date)] submitted dependent aggregation job: $AGG_JOB (afterok:$ARRAY_JOB)"

  cat <<EOF

Array job $ARRAY_JOB submitted (array=$ARRAY).
Aggregation job $AGG_JOB will run automatically after the array succeeds.

EOF
fi
