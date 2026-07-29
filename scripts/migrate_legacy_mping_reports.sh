#!/usr/bin/bash -l
#
# Migrate the legacy flat-layout mPing reports into the per-dataset layout so
# the dashboard suite exposes mPing alongside riceTElib.
#
# Why this exists: the mPing benchmark predates the multi-dataset migration.
# Its aggregated reports were written to the report ROOT (reports/*.tsv) instead
# of reports/datasets/mping/, and its truth/ and per_sample/ inputs were never
# moved to the per-dataset paths (truth/mping, reports/datasets/mping/per_sample).
# That means combine_reports.py cannot re-aggregate mPing under the new layout,
# but the root TSVs are already the canonical, correct aggregated reports. This
# script copies those TSVs into reports/datasets/mping/ (which the loader and
# aggregate.sh's manifest step expect) and rebuilds reports/datasets.tsv.
#
# Idempotent: safe to rerun. Run from the repository root.
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"
CONFIG="${CONFIG:-config/benchmark.toml}"

if command -v pixi >/dev/null 2>&1 && [[ -f env/benchmark/pixi.toml ]]; then
  PY=(pixi run --manifest-path env/benchmark/pixi.toml python3)
else
  echo "WARN: benchmark pixi env unavailable; using unpinned python3.12" >&2
  PY=(python3.12)
fi

eval "$("${PY[@]}" pipeline/config_env.py --config "$CONFIG" globals)"
REPORT_ROOT="${REPORT_ROOT:-reports}"

REPORTS=(correctness.tsv precision.tsv head_to_head.tsv resources.tsv)
src="$REPORT_ROOT"
dst="$REPORT_ROOT/datasets/mping"

echo "[$(date)] migrating legacy mPing reports: $src/*.tsv -> $dst/"
missing=0
for name in "${REPORTS[@]}"; do
  if [[ ! -s "$src/$name" ]]; then
    echo "ERROR: missing legacy mPing report: $src/$name" >&2
    missing=1
  fi
done
[[ "$missing" -eq 0 ]] || {
  echo "ERROR: legacy mPing reports not found at the report root; nothing to migrate." >&2
  exit 1
}

mkdir -p "$dst"
for name in "${REPORTS[@]}"; do
  cp -f "$src/$name" "$dst/$name"
done
# Carry over the PDF report when present so the dataset dir is self-contained.
[[ -s "$src/benchmark_report.pdf" ]] && cp -f "$src/benchmark_report.pdf" "$dst/benchmark_report.pdf"

# Rebuild the dashboard manifest exactly as aggregate.sh does: list every
# configured dataset whose per-dataset dir now holds the four required reports.
manifest="$REPORT_ROOT/datasets.tsv"
temporary="${manifest}.tmp.$$"
printf 'dataset\tlabel\treport_dir\n' > "$temporary"
while IFS=$'\t' read -r dataset label panel_root; do
  [[ -n "$dataset" ]] || continue
  report_dir="$REPORT_ROOT/datasets/$dataset"
  if [[ -s "$report_dir/correctness.tsv" && -s "$report_dir/precision.tsv" &&
        -s "$report_dir/head_to_head.tsv" && -s "$report_dir/resources.tsv" ]]; then
    printf '%s\t%s\tdatasets/%s\n' "$dataset" "$label" "$dataset" >> "$temporary"
  fi
done < <("${PY[@]}" pipeline/config_env.py --config "$CONFIG" --dataset full datasets)
mv -f "$temporary" "$manifest"

echo "[$(date)] done. dashboard manifest now lists:"
cat "$manifest"
