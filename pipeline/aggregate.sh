#!/usr/bin/bash -l
#SBATCH -p epyc
#SBATCH --mem=8gb
#SBATCH --cpus-per-task=2
#SBATCH --time=00:30:00
#SBATCH -o logs/aggregate.%j.log
#
# relocate-benchmark post-array aggregation.
#
# Runs after ALL array tasks finish (submitted with a SLURM afterok dependency
# by pipeline/submit_benchmark.sh). Combines per-sample reports, computes the
# head-to-head caller comparison, and (best-effort) renders a PDF report.
set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
PY=python3.12

echo "[$(date)] aggregate: starting in $(pwd)"

mkdir -p logs reports

# ---------------------------------------------------------------------------
# 1. Combine per-sample correctness/precision/resources into reports/*.tsv.
# ---------------------------------------------------------------------------
echo "[$(date)] combining per-sample reports"
"$PY" scoring/combine_reports.py \
  --report-root reports \
  --samples truth/samples.tsv

# ---------------------------------------------------------------------------
# 2. Head-to-head caller comparison.
# ---------------------------------------------------------------------------
echo "[$(date)] comparing callers"
"$PY" scoring/compare_callers.py \
  --correctness reports/correctness.tsv \
  --outdir reports

# ---------------------------------------------------------------------------
# 3. Best-effort PDF report (never fails the job).
# ---------------------------------------------------------------------------
PDF="reports/benchmark_report.pdf"
if [[ -f scoring/make_report.R ]]; then
  echo "[$(date)] rendering PDF report (best-effort)"
  BENCH_ENV="env/benchmark/pixi.toml"
  if command -v pixi >/dev/null 2>&1 && [[ -f "$BENCH_ENV" ]]; then
    RUN_R=(pixi run --manifest-path "$BENCH_ENV" Rscript)
  else
    echo "WARN: benchmark pixi env unavailable; using unpinned module R" >&2
    command -v module >/dev/null 2>&1 && { module load R || true; }
    RUN_R=(Rscript)
  fi
  if ! "${RUN_R[@]}" scoring/make_report.R reports "$PDF"; then
    echo "WARN: PDF report step failed" >&2
  fi
else
  echo "[$(date)] note: scoring/make_report.R absent; skipping PDF report"
fi

# ---------------------------------------------------------------------------
# 4. Report produced paths.
# ---------------------------------------------------------------------------
echo "[$(date)] aggregation complete. Reports:"
echo "  reports/correctness.tsv"
echo "  reports/precision.tsv"
echo "  reports/resources.tsv"
echo "  reports/head_to_head.tsv"
if [[ -f "$PDF" ]]; then
  echo "  $PDF"
fi
