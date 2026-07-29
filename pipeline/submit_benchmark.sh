#!/usr/bin/bash -l
#
# Export selected truth, prepare shared inputs, submit the canonical task array,
# and optionally submit per-dataset aggregation with an afterok dependency.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SLURM_SUBMIT_DIR:-$SCRIPT_DIR/..}"

if command -v pixi >/dev/null 2>&1 && [[ -f env/benchmark/pixi.toml ]]; then
  PY=(pixi run --manifest-path env/benchmark/pixi.toml python3)
else
  PY=(python3.12)
fi
CONFIG="${CONFIG:-config/benchmark.toml}"

DATASET_SELECTION=""
FILTER_CALLER=""
FILTER_COVERAGE=""
FILTER_SAMPLE=""
FILTER_REPLICATE=""
NO_AGGREGATE=0
SHOW_HELP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dataset)    DATASET_SELECTION="$2"; shift 2 ;;
    --caller)     FILTER_CALLER="$2";     shift 2 ;;
    --coverage)   FILTER_COVERAGE="$2";   shift 2 ;;
    --sample)     FILTER_SAMPLE="$2";     shift 2 ;;
    --replicate)  FILTER_REPLICATE="$2";  shift 2 ;;
    --no-aggregate) NO_AGGREGATE=1; shift ;;
    -h|--help) SHOW_HELP=1; shift ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 1 ;;
  esac
done

print_help() {
  cat <<'EOF'
Usage: bash pipeline/submit_benchmark.sh [options]

Options:
  --dataset <name>     mping, ricetelib, or full (default: config setting)
  --caller <list>      Caller key(s), comma-separated
  --coverage <list>    Coverage value(s), comma-separated
  --sample <list>      Sample name(s), comma-separated
  --replicate <list>   Replicate value(s), comma-separated
  --no-aggregate       Do not submit the dependent aggregation job
  -h, --help           Show this help

Examples:
  bash pipeline/submit_benchmark.sh --dataset ricetelib
  bash pipeline/submit_benchmark.sh --dataset full --coverage 15,30
EOF
}
if (( SHOW_HELP == 1 )); then
  print_help
  exit 0
fi

# Resolve an omitted selection to its concrete configured default so array and
# aggregation jobs receive an explicit, immutable value.
if [[ -z "$DATASET_SELECTION" ]]; then
  DATASET_SELECTION="$(
    "${PY[@]}" pipeline/config_env.py --config "$CONFIG" datasets |
      awk -F '\t' 'NR == 1 {print $1}'
  )"
fi
DATASET_ROWS="$(
  "${PY[@]}" pipeline/config_env.py --config "$CONFIG" \
    --dataset "$DATASET_SELECTION" datasets
)"
if [[ -z "$DATASET_ROWS" ]]; then
  echo "ERROR: no selected datasets" >&2
  exit 1
fi

eval "$("${PY[@]}" pipeline/config_env.py --config "$CONFIG" globals)"
echo "[$(date)] submit_benchmark: config=$CONFIG datasets=$DATASET_SELECTION"

# Export truth independently and prepare deterministic cached caller inputs.
while IFS=$'\t' read -r dataset label panel_root; do
  [[ -n "$dataset" ]] || continue
  eval "$("${PY[@]}" pipeline/config_env.py --config "$CONFIG" dataset-env "$dataset")"
  for input in "$PANEL_ROOT/panel_manifest.tsv" "$PANEL_ROOT/truth_events.tsv" \
               "$REFERENCE" "$TE_LIBRARY_SOURCE"; do
    [[ -s "$input" ]] || { echo "ERROR: required input missing or empty: $input" >&2; exit 1; }
  done
  for reference_index in \
    "${REFERENCE}.fai" "${REFERENCE}.mmi" \
    "${REFERENCE}.amb" "${REFERENCE}.ann" "${REFERENCE}.bwt" \
    "${REFERENCE}.pac" "${REFERENCE}.sa"; do
    [[ -s "$reference_index" ]] || {
      echo "ERROR: required prebuilt reference index missing: $reference_index" >&2
      echo "       Build reference indexes through an HPC job before submission." >&2
      exit 1
    }
  done
  mkdir -p "$(dirname "$TE_LIBRARY")"
  if [[ -s "$TE_LIBRARY" ]] && cmp -s "$TE_LIBRARY_SOURCE" "$TE_LIBRARY"; then
    echo "[$(date)] staged TE library is current: $dataset"
  else
    # Invalidate only derived sidecars beside this cache-owned library. Keeping
    # an old non-empty index after replacing the FASTA would silently corrupt
    # caller results.
    for suffix in \
      .1.bt2 .2.bt2 .3.bt2 .4.bt2 .rev.1.bt2 .rev.2.bt2 \
      .1.bt2l .2.bt2l .3.bt2l .4.bt2l .rev.1.bt2l .rev.2.bt2l \
      .amb .ann .bwt .pac .sa .mmi; do
      index_path="${TE_LIBRARY}${suffix}"
      [[ ! -e "$index_path" ]] || rm -f "$index_path"
    done
    staged_tmp="${TE_LIBRARY}.tmp.$$"
    cp "$TE_LIBRARY_SOURCE" "$staged_tmp"
    mv -f "$staged_tmp" "$TE_LIBRARY"
    echo "[$(date)] staged TE library: $TE_LIBRARY_SOURCE -> $TE_LIBRARY"
  fi
  if [[ -n "$REPEATMASKER_GFF" ]]; then
    "${PY[@]}" pipeline/gff_to_repeatmasker_out.py \
      --input "$REPEATMASKER_GFF" \
      --output "$REPEATMASKER" \
      --force
  fi
  [[ -s "$REPEATMASKER" ]] || {
    echo "ERROR: reference-TE annotation missing or empty: $REPEATMASKER" >&2
    exit 1
  }
  if [[ -f "$DATASET_TRUTH_ROOT/.complete" ]]; then
    echo "[$(date)] truth already exported: $dataset"
  else
    echo "[$(date)] exporting truth: $dataset ($label)"
    "${PY[@]}" scoring/export_truth.py \
      --panel-root "$PANEL_ROOT" \
      --outdir "$DATASET_TRUTH_ROOT"
  fi
done <<< "$DATASET_ROWS"

IDX_ARGS=()
[[ -n "$FILTER_CALLER" ]]    && IDX_ARGS+=(--caller "$FILTER_CALLER")
[[ -n "$FILTER_COVERAGE" ]]  && IDX_ARGS+=(--coverage "$FILTER_COVERAGE")
[[ -n "$FILTER_SAMPLE" ]]    && IDX_ARGS+=(--sample "$FILTER_SAMPLE")
[[ -n "$FILTER_REPLICATE" ]] && IDX_ARGS+=(--replicate "$FILTER_REPLICATE")

if ((${#IDX_ARGS[@]})); then
  ARRAY="$(
    "${PY[@]}" pipeline/config_env.py --config "$CONFIG" \
      --dataset "$DATASET_SELECTION" indices "${IDX_ARGS[@]}"
  )"
  [[ -n "$ARRAY" ]] || { echo "ERROR: no tasks match the filters" >&2; exit 1; }
else
  count="$(
    "${PY[@]}" pipeline/config_env.py --config "$CONFIG" \
      --dataset "$DATASET_SELECTION" count
  )"
  (( count > 0 )) || { echo "ERROR: no benchmark tasks" >&2; exit 1; }
  ARRAY="0-$((count - 1))"
fi
echo "[$(date)] task array: $ARRAY"
mkdir -p logs

_csv_has() {
  local needle="$1" csv="$2" item
  [[ -z "$csv" ]] && return 0
  local IFS=,
  for item in $csv; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}

TE_ALIGNERS=()
while IFS= read -r caller; do
  [[ -n "$caller" ]] || continue
  _csv_has "$caller" "$FILTER_CALLER" || continue
  caller_env="$("${PY[@]}" pipeline/config_env.py --config "$CONFIG" caller-env "$caller")"
  aligner="$(sed -n 's/^RT3_TE_ALIGNER=//p' <<< "$caller_env" | tr -d "'")"
  [[ -z "$aligner" ]] || TE_ALIGNERS+=("$aligner")
done < <("${PY[@]}" pipeline/config_env.py --config "$CONFIG" callers)

if ((${#TE_ALIGNERS[@]})); then
  ADAPTER_DIR="callers/relocate3"
  source callers/relocate3/env.sh
  while IFS=$'\t' read -r dataset label panel_root; do
    eval "$("${PY[@]}" pipeline/config_env.py --config "$CONFIG" dataset-env "$dataset")"
    while IFS= read -r aligner; do
      case "$aligner" in
        bowtie2)
          [[ -s "${TE_LIBRARY}.1.bt2" ]] ||
            bowtie2-build --quiet "$TE_LIBRARY" "$TE_LIBRARY" ;;
        bwa)
          [[ -s "${TE_LIBRARY}.bwt" ]] || bwa index "$TE_LIBRARY" ;;
        minimap2)
          [[ -s "${TE_LIBRARY}.mmi" ]] ||
            minimap2 -d "${TE_LIBRARY}.mmi" "$TE_LIBRARY" ;;
        blat) : ;;
        *) echo "WARN: unknown TE aligner '$aligner'; task will prepare it" >&2 ;;
      esac
    done < <(printf '%s\n' "${TE_ALIGNERS[@]}" | sort -u)
  done <<< "$DATASET_ROWS"
fi

ARRAY_JOB="$(
  sbatch --parsable \
    --array="$ARRAY" \
    --export=ALL,CONFIG="$CONFIG",DATASET_SELECTION="$DATASET_SELECTION" \
    pipeline/run_benchmark_array.sh
)"
echo "[$(date)] submitted array job: $ARRAY_JOB"

if (( NO_AGGREGATE == 0 )); then
  AGG_JOB="$(
    sbatch --parsable \
      --dependency=afterok:"$ARRAY_JOB" \
      --export=ALL,CONFIG="$CONFIG",DATASET_SELECTION="$DATASET_SELECTION" \
      pipeline/aggregate.sh
  )"
  echo "[$(date)] submitted aggregation job: $AGG_JOB (afterok:$ARRAY_JOB)"
else
  echo "[$(date)] aggregation skipped; later run:"
  echo "  sbatch --export=ALL,DATASET_SELECTION=$DATASET_SELECTION pipeline/aggregate.sh"
fi
