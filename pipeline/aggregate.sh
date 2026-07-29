#!/usr/bin/bash -l
#SBATCH -p epyc
#SBATCH --mem=8gb
#SBATCH --cpus-per-task=2
#SBATCH --time=00:30:00
#SBATCH -o logs/aggregate.%j.log
#
# Aggregate every selected dataset independently and refresh the dashboard
# dataset manifest. Normally submitted afterok by submit_benchmark.sh.
set -euo pipefail

BASE_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$BASE_DIR"
CONFIG="${CONFIG:-config/benchmark.toml}"
DATASET_SELECTION="${DATASET_SELECTION:-full}"

if command -v pixi >/dev/null 2>&1 && [[ -f env/benchmark/pixi.toml ]]; then
  PY=(pixi run --manifest-path env/benchmark/pixi.toml python3)
else
  echo "WARN: benchmark pixi env unavailable; using unpinned python3.12" >&2
  PY=(python3.12)
fi

eval "$("${PY[@]}" pipeline/config_env.py --config "$CONFIG" globals)"
mkdir -p logs "$REPORT_ROOT/datasets"

DATASET_ROWS="$(
  "${PY[@]}" pipeline/config_env.py --config "$CONFIG" \
    --dataset "$DATASET_SELECTION" datasets
)"

while IFS=$'\t' read -r dataset label panel_root; do
  [[ -n "$dataset" ]] || continue
  eval "$("${PY[@]}" pipeline/config_env.py --config "$CONFIG" dataset-env "$dataset")"
  echo "[$(date)] aggregating dataset: $dataset ($label)"
  mkdir -p "$DATASET_REPORT_ROOT"

  "${PY[@]}" scoring/combine_reports.py \
    --report-root "$DATASET_REPORT_ROOT" \
    --samples "$DATASET_TRUTH_ROOT/samples.tsv"

  "${PY[@]}" scoring/compare_callers.py \
    --correctness "$DATASET_REPORT_ROOT/correctness.tsv" \
    --outdir "$DATASET_REPORT_ROOT"

  pdf="$DATASET_REPORT_ROOT/benchmark_report.pdf"
  if [[ -f scoring/make_report.R ]]; then
    if command -v pixi >/dev/null 2>&1 && [[ -f env/benchmark/pixi.toml ]]; then
      RUN_R=(pixi run --manifest-path env/benchmark/pixi.toml Rscript)
    else
      command -v module >/dev/null 2>&1 && { module load R || true; }
      RUN_R=(Rscript)
    fi
    if ! "${RUN_R[@]}" scoring/make_report.R "$DATASET_REPORT_ROOT" "$pdf"; then
      echo "WARN: PDF report failed for dataset $dataset" >&2
    fi
  fi
done <<< "$DATASET_ROWS"

# Include every complete dataset report, not only the latest selection, so a
# riceTElib-only refresh does not remove a prior mPing tab from the dashboard.
manifest="$REPORT_ROOT/datasets.tsv"
temporary="${manifest}.tmp.$$"
printf 'dataset\tlabel\treport_dir\n' > "$temporary"
while IFS=$'\t' read -r dataset label panel_root; do
  report_dir="$REPORT_ROOT/datasets/$dataset"
  if [[ -s "$report_dir/correctness.tsv" && -s "$report_dir/precision.tsv" &&
        -s "$report_dir/head_to_head.tsv" && -s "$report_dir/resources.tsv" ]]; then
    printf '%s\t%s\tdatasets/%s\n' "$dataset" "$label" "$dataset" >> "$temporary"
  fi
done < <("${PY[@]}" pipeline/config_env.py --config "$CONFIG" --dataset full datasets)
mv -f "$temporary" "$manifest"

echo "[$(date)] aggregation complete; dashboard manifest: $manifest"
